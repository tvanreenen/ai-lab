from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import Any

from pydantic_ai.messages import ModelMessage

from .models import CollapseState, CompactionConfig, RecoveryRunResult, StageRunResult, TurnRecord
from .projection import build_projected_history
from .staging import CollapseStager
from .storage import save_state
from .token_estimation import estimate_model_messages


@dataclass(slots=True)
class RequestBudget:
    projected_messages: list[ModelMessage]
    pending_messages: list[ModelMessage]
    projected_tokens: int
    pending_tokens: int
    request_tokens: int


class CollapseEngine:
    def __init__(
        self,
        *,
        state_root,
        config: CompactionConfig,
        lock: threading.Lock,
        model_name: str | None,
        load_turns: Callable[[], list[TurnRecord]],
        load_state: Callable[[], CollapseState],
    ) -> None:
        self.state_root = state_root
        self.config = config
        self.lock = lock
        self.model_name = model_name
        self._load_turns = load_turns
        self._load_state = load_state
        self._stager = CollapseStager(
            state_root=state_root,
            config=config,
            lock=lock,
            model_name=model_name,
            load_state=load_state,
        )

    def stage_if_needed(self, summarizer_agent: Any) -> StageRunResult:
        staged_count = 0
        estimated_savings_tokens = 0

        with self.lock:
            turns = self._load_turns()
            state = self._load_state()
            budget = self.build_request_budget(turns, state, pending_messages=[])
            self._update_pressure_markers(state, budget)

            if budget.request_tokens < self.config.stage_threshold:
                save_state(self.state_root, state)
                return StageRunResult(
                    status="below-stage-threshold",
                    estimated_request_tokens=budget.request_tokens,
                    target_threshold=self.config.target_threshold,
                )

        while True:
            with self.lock:
                turns = self._load_turns()
                state = self._load_state()
                budget = self.build_request_budget(turns, state, pending_messages=[])
                estimated_after_commit = max(0, budget.request_tokens - estimated_savings_tokens)
                self._update_pressure_markers(state, budget)

                if estimated_after_commit <= self.config.target_threshold:
                    save_state(self.state_root, state)
                    return StageRunResult(
                        status="staged" if staged_count > 0 else "already-within-target",
                        staged_count=staged_count,
                        estimated_savings_tokens=estimated_savings_tokens,
                        estimated_request_tokens=budget.request_tokens,
                        target_threshold=self.config.target_threshold,
                    )

                candidate = self._stager.select_next_stage_chunk(turns, state)
                if not candidate:
                    if staged_count == 0:
                        state.health.empty_stage_runs += 1
                    save_state(self.state_root, state)
                    return StageRunResult(
                        status="no-eligible-span" if staged_count == 0 else "partial-stage",
                        staged_count=staged_count,
                        estimated_savings_tokens=estimated_savings_tokens,
                        estimated_request_tokens=budget.request_tokens,
                        target_threshold=self.config.target_threshold,
                    )

            try:
                staged, expected_savings = self._stager.summarize_and_stage_candidate(
                    candidate,
                    summarizer_agent=summarizer_agent,
                )
            except Exception as exc:
                return StageRunResult(
                    status=f"stage-failed: {exc}",
                    staged_count=staged_count,
                    estimated_savings_tokens=estimated_savings_tokens,
                    estimated_request_tokens=budget.request_tokens,
                    target_threshold=self.config.target_threshold,
                )

            if staged is None:
                continue

            staged_count += 1
            estimated_savings_tokens += expected_savings

    def prepare_request_budget_with_recovery(
        self,
        *,
        pending_messages: list[ModelMessage],
        recovery_summarizer_agent: Any | None = None,
        recovery_notifier: Callable[[str], None] | None = None,
    ) -> tuple[RequestBudget, RecoveryRunResult | None]:
        with self.lock:
            turns = self._load_turns()
            state = self._load_state()
            initial_budget = self.build_request_budget(turns, state, pending_messages=pending_messages)
            state, budget, _ = self._stager.commit_staged_spans_until_target(
                turns,
                state,
                pending_messages=pending_messages,
                budget=initial_budget,
                build_request_budget=self.build_request_budget,
            )
            should_recover = (
                initial_budget.request_tokens > self.config.guard_threshold
                and budget.request_tokens > self.config.target_threshold
                and recovery_summarizer_agent is not None
            )

        if should_recover:
            return self.recover_request_budget(
                pending_messages=pending_messages,
                summarizer_agent=recovery_summarizer_agent,
                notifier=recovery_notifier,
            )

        return budget, None

    def recover_request_budget(
        self,
        *,
        pending_messages: list[ModelMessage],
        summarizer_agent: Any,
        notifier: Callable[[str], None] | None = None,
    ) -> tuple[RequestBudget, RecoveryRunResult]:
        with self.lock:
            turns = self._load_turns()
            state = self._load_state()
            budget = self.build_request_budget(turns, state, pending_messages=pending_messages)
            state.last_recovery = RecoveryRunResult(
                in_progress=True,
                status="running",
                starting_request_tokens=budget.request_tokens,
                ending_request_tokens=budget.request_tokens,
            )
            save_state(self.state_root, state)

        if notifier is not None:
            notifier("Summarizing more of our conversation before continuing...")

        staged_count = 0
        committed_count = 0
        hit_chunk_limit = False
        hit_time_limit = False
        status = "recovered"
        start_time = time.monotonic()

        while True:
            with self.lock:
                turns = self._load_turns()
                state = self._load_state()
                budget = self.build_request_budget(turns, state, pending_messages=pending_messages)
                if budget.request_tokens <= self.config.target_threshold:
                    break
                candidate = self._stager.select_next_stage_chunk(turns, state)

            if staged_count >= self.config.max_emergency_stage_chunks:
                hit_chunk_limit = True
                status = "chunk-limit-reached"
                break

            if (time.monotonic() - start_time) >= self.config.max_emergency_stage_seconds:
                hit_time_limit = True
                status = "time-limit-reached"
                break

            if not candidate:
                status = "no-eligible-span"
                break

            try:
                staged, _ = self._stager.summarize_and_stage_candidate(
                    candidate,
                    summarizer_agent=summarizer_agent,
                )
            except Exception as exc:
                status = f"stage-failed: {exc}"
                break

            if staged is None:
                continue

            staged_count += 1
            with self.lock:
                turns = self._load_turns()
                state = self._load_state()
                budget = self.build_request_budget(turns, state, pending_messages=pending_messages)
                state, budget, committed_now = self._stager.commit_staged_spans_until_target(
                    turns,
                    state,
                    pending_messages=pending_messages,
                    budget=budget,
                    build_request_budget=self.build_request_budget,
                )
            committed_count += committed_now

            if budget.request_tokens <= self.config.target_threshold:
                status = "recovered"
                break

        with self.lock:
            latest_turns = self._load_turns()
            latest_state = self._load_state()
            latest_budget = self.build_request_budget(
                latest_turns,
                latest_state,
                pending_messages=pending_messages,
            )
            latest_state.last_recovery = RecoveryRunResult(
                in_progress=False,
                status=status,
                committed_count=committed_count,
                staged_count=staged_count,
                starting_request_tokens=latest_state.last_recovery.starting_request_tokens,
                ending_request_tokens=latest_budget.request_tokens,
                hit_chunk_limit=hit_chunk_limit,
                hit_time_limit=hit_time_limit,
            )
            save_state(self.state_root, latest_state)
            return latest_budget, latest_state.last_recovery

    def build_request_budget(
        self,
        turns: list[TurnRecord],
        state: CollapseState,
        *,
        pending_messages: list[ModelMessage],
    ) -> RequestBudget:
        projected = build_projected_history(turns, state)
        projected_tokens = estimate_model_messages(
            projected.messages,
            model_name=self.model_name,
            calibration_factor=state.calibration.input_calibration_factor,
        )
        pending_tokens = estimate_model_messages(
            pending_messages,
            model_name=self.model_name,
            calibration_factor=state.calibration.input_calibration_factor,
        )
        return RequestBudget(
            projected_messages=projected.messages,
            pending_messages=pending_messages,
            projected_tokens=projected_tokens,
            pending_tokens=pending_tokens,
            request_tokens=projected_tokens + pending_tokens,
        )

    def _update_pressure_markers(self, state: CollapseState, budget: RequestBudget) -> None:
        state.under_pressure = budget.request_tokens >= self.config.pressure_threshold
        state.last_stage_check_request_tokens = budget.request_tokens
