from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage

from .diagnostics import (
    render_committed_spans,
    render_staged_spans,
    render_state_json,
)
from .engine import CollapseEngine, RequestBudget
from .models import (
    CalibrationStats,
    CollapseState,
    CompactionConfig,
    RecoveryRunResult,
    StageRunResult,
    TurnRecord,
)
from .projection import (
    ProjectedHistory,
    build_projected_history,
    flatten_turns,
    render_projected_messages,
    render_turns,
)
from .storage import (
    append_turn,
    ensure_layout,
    load_state,
    load_turns,
    reset_state_root,
    save_state,
    serialize_model_messages,
)
from .token_estimation import estimate_model_messages

CALIBRATION_ALPHA = 0.2
MIN_INPUT_CALIBRATION_FACTOR = 0.7
MAX_INPUT_CALIBRATION_FACTOR = 1.3


class ProjectedHistoryOverflowError(RuntimeError):
    def __init__(self, *, estimated_tokens: int, threshold: int) -> None:
        super().__init__(
            f"Projected history still exceeds the configured context window "
            f"({estimated_tokens} > {threshold}) after recovery attempts."
        )
        self.estimated_tokens = estimated_tokens
        self.threshold = threshold


class HistoryCompactionManager:
    def __init__(
        self,
        state_root: Path,
        *,
        config: CompactionConfig | None = None,
        lock: threading.Lock | None = None,
        model_name: str | None = None,
    ) -> None:
        self.state_root = state_root.resolve()
        self.config = config or CompactionConfig()
        self.lock = lock or threading.Lock()
        self.model_name = model_name
        self._recovery_summarizer_agent: Any | None = None
        self._recovery_notifier: Callable[[str], None] | None = None
        ensure_layout(self.state_root)
        self._engine = CollapseEngine(
            state_root=self.state_root,
            config=self.config,
            lock=self.lock,
            model_name=self.model_name,
            load_turns=self.load_turns,
            load_state=self.load_state,
        )

    def build_history_processor(
        self,
    ) -> Callable[[RunContext[Any] | list[ModelMessage], list[ModelMessage] | None], list[ModelMessage]]:
        def processor(
            maybe_ctx: RunContext[Any] | list[ModelMessage],
            maybe_messages: list[ModelMessage] | None = None,
        ) -> list[ModelMessage]:
            if maybe_messages is None:
                incoming = list(maybe_ctx)  # type: ignore[arg-type]
            else:
                incoming = list(maybe_messages)
            return self.project_request_messages(incoming)

        return processor

    def configure_recovery(
        self,
        *,
        summarizer_agent: Any | None = None,
        notifier: Callable[[str], None] | None = None,
    ) -> None:
        self._recovery_summarizer_agent = summarizer_agent
        self._recovery_notifier = notifier

    def load_turns(self) -> list[TurnRecord]:
        return load_turns(self.state_root)

    def load_state(self) -> CollapseState:
        return load_state(self.state_root)

    def clear_state(self) -> None:
        with self.lock:
            reset_state_root(self.state_root)

    def raw_message_history(self) -> list[ModelMessage]:
        return flatten_turns(self.load_turns())

    def preview_projected_history(self) -> ProjectedHistory:
        return build_projected_history(self.load_turns(), self.load_state())

    def prepare_projected_history_for_run(
        self,
        *,
        pending_messages: Sequence[ModelMessage] | None = None,
    ) -> list[ModelMessage]:
        budget, _ = self._prepare_request_budget_with_recovery(
            pending_messages=list(pending_messages or []),
        )
        self._raise_if_request_exceeds_fail_threshold(budget)
        return budget.projected_messages

    def project_request_messages(self, incoming: Sequence[ModelMessage]) -> list[ModelMessage]:
        with self.lock:
            turns = self.load_turns()
            raw = flatten_turns(turns)
            pending = self._pending_suffix(raw, list(incoming))
        budget, _ = self._prepare_request_budget_with_recovery(pending_messages=pending)
        self._raise_if_request_exceeds_fail_threshold(budget)
        return budget.projected_messages + budget.pending_messages

    def record_turn(
        self,
        user_text: str,
        new_messages: Sequence[ModelMessage],
        *,
        estimated_request_input_tokens: int | None = None,
        actual_input_tokens: int | None = None,
        actual_output_tokens: int | None = None,
        request_count: int | None = None,
    ) -> TurnRecord:
        with self.lock:
            state = self.load_state()
            estimated_turn_payload_tokens = estimate_model_messages(
                list(new_messages),
                model_name=self.model_name,
                calibration_factor=1.0,
            )
            record = TurnRecord(
                turn_id=f"turn-{uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                user_text=user_text,
                messages=serialize_model_messages(new_messages),
                estimated_turn_payload_tokens=estimated_turn_payload_tokens,
                actual_input_tokens=actual_input_tokens,
                actual_output_tokens=actual_output_tokens,
                request_count=request_count,
            )
            append_turn(self.state_root, record)
            if (
                actual_input_tokens is not None
                and estimated_request_input_tokens is not None
                and estimated_request_input_tokens > 0
                and (request_count is None or request_count == 1)
            ):
                state.calibration = self._update_calibration(
                    state.calibration,
                    estimated_request_input_tokens=estimated_request_input_tokens,
                    actual_input_tokens=actual_input_tokens,
                    actual_output_tokens=actual_output_tokens,
                    request_count=request_count,
                )
                save_state(self.state_root, state)
            return record

    def stage_if_needed(self, summarizer_agent: Any) -> StageRunResult:
        return self._engine.stage_if_needed(summarizer_agent)

    def recover_request_budget(
        self,
        *,
        pending_messages: list[ModelMessage],
    ) -> tuple[RequestBudget, RecoveryRunResult]:
        if self._recovery_summarizer_agent is None:
            raise RuntimeError("Recovery summarizer is not configured.")
        return self._engine.recover_request_budget(
            pending_messages=pending_messages,
            summarizer_agent=self._recovery_summarizer_agent,
            notifier=self._recovery_notifier,
        )

    def render_raw_history(self) -> str:
        return render_turns(self.load_turns())

    def render_projected_history(self) -> str:
        projected = self.preview_projected_history()
        return render_projected_messages(projected.messages)

    def render_staged_spans(self) -> str:
        return render_staged_spans(self.load_state())

    def render_committed_spans(self) -> str:
        return render_committed_spans(self.load_state())

    def render_state(self) -> str:
        state = self.load_state()
        turns = self.load_turns()
        budget = self._engine.build_request_budget(turns, state, pending_messages=[])
        return render_state_json(
            config=self.config,
            state=state,
            budget=budget,
        )

    def _prepare_request_budget_with_recovery(
        self,
        *,
        pending_messages: list[ModelMessage],
    ) -> tuple[RequestBudget, RecoveryRunResult | None]:
        return self._engine.prepare_request_budget_with_recovery(
            pending_messages=pending_messages,
            recovery_summarizer_agent=self._recovery_summarizer_agent,
            recovery_notifier=self._recovery_notifier,
        )

    def _pending_suffix(
        self,
        raw_messages: Sequence[ModelMessage],
        incoming: Sequence[ModelMessage],
    ) -> list[ModelMessage]:
        raw_len = len(raw_messages)
        if raw_len == 0:
            return list(incoming)
        if len(incoming) >= raw_len and self._message_slices_equal(incoming[:raw_len], raw_messages):
            return list(incoming[raw_len:])
        if incoming and not self._message_slices_equal(incoming, raw_messages):
            return [incoming[-1]]
        return []

    def _message_slices_equal(
        self,
        left: Sequence[ModelMessage],
        right: Sequence[ModelMessage],
    ) -> bool:
        if len(left) != len(right):
            return False
        return serialize_model_messages(left) == serialize_model_messages(right)

    def _update_calibration(
        self,
        calibration: CalibrationStats,
        *,
        estimated_request_input_tokens: int,
        actual_input_tokens: int,
        actual_output_tokens: int | None,
        request_count: int | None,
    ) -> CalibrationStats:
        observed_ratio = actual_input_tokens / estimated_request_input_tokens
        previous_samples = calibration.samples
        next_samples = previous_samples + 1
        if previous_samples == 0:
            smoothed_ratio = observed_ratio
        else:
            smoothed_ratio = (
                (1.0 - CALIBRATION_ALPHA) * calibration.input_calibration_factor
            ) + (CALIBRATION_ALPHA * observed_ratio)
        bounded_ratio = min(
            MAX_INPUT_CALIBRATION_FACTOR,
            max(MIN_INPUT_CALIBRATION_FACTOR, smoothed_ratio),
        )
        return CalibrationStats(
            samples=next_samples,
            input_calibration_factor=bounded_ratio,
            last_estimated_request_input_tokens=estimated_request_input_tokens,
            last_actual_input_tokens=actual_input_tokens,
            last_actual_output_tokens=actual_output_tokens,
            last_request_count=request_count,
        )

    def _raise_if_request_exceeds_fail_threshold(self, budget: RequestBudget) -> None:
        if budget.request_tokens > self.config.fail_threshold:
            raise ProjectedHistoryOverflowError(
                estimated_tokens=budget.request_tokens,
                threshold=self.config.fail_threshold,
            )
