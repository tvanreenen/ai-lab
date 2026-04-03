from __future__ import annotations

from collections.abc import Callable, Sequence
import threading
from typing import Any

from .models import (
    CollapseState,
    CommittedSpan,
    CompactionConfig,
    StageSummary,
    StagedSpan,
    TurnRecord,
)
from .projection import (
    build_projected_summary_request,
    flatten_turns,
    render_turns_for_summary,
)
from .prompts import build_projected_message_text, build_summary_prompt
from .storage import save_state
from .token_estimation import estimate_model_messages


class CollapseStager:
    def __init__(
        self,
        *,
        state_root,
        config: CompactionConfig,
        lock: threading.Lock,
        model_name: str | None,
        load_state: Callable[[], CollapseState],
    ) -> None:
        self.state_root = state_root
        self.config = config
        self.lock = lock
        self.model_name = model_name
        self._load_state = load_state

    def select_next_stage_chunk(
        self,
        turns: Sequence[TurnRecord],
        state: CollapseState,
    ) -> list[TurnRecord]:
        chunks = self._stage_chunks(turns, state)
        return chunks[0] if chunks else []

    def summarize_and_stage_candidate(
        self,
        candidate: Sequence[TurnRecord],
        *,
        summarizer_agent: Any,
    ) -> tuple[StagedSpan | None, int]:
        summary = self._summarize_candidate(
            candidate,
            summarizer_agent=summarizer_agent,
        )
        return self._stage_summary_for_candidate(candidate, summary)

    def commit_staged_spans_until_target(
        self,
        turns: Sequence[TurnRecord],
        state: CollapseState,
        *,
        pending_messages,
        budget,
        build_request_budget: Callable[..., Any],
    ) -> tuple[CollapseState, Any, int]:
        committed_count = 0
        if budget.request_tokens <= self.config.guard_threshold:
            return state, budget, committed_count

        while budget.request_tokens > self.config.target_threshold and state.staged_spans:
            staged = sorted(
                state.staged_spans,
                key=lambda span: (span.staged_at, span.start_turn_id),
            )[0]
            state.staged_spans = [span for span in state.staged_spans if span != staged]
            collapse_id = self._next_collapse_id(state)
            state.committed_spans.append(
                CommittedSpan(
                    collapse_id=collapse_id,
                    start_turn_id=staged.start_turn_id,
                    end_turn_id=staged.end_turn_id,
                    summary_text=staged.summary_text,
                    projected_message_text=build_projected_message_text(
                        staged.summary_text
                    ),
                )
            )
            state.health.committed_from_staging += 1
            committed_count += 1
            budget = build_request_budget(
                turns,
                state,
                pending_messages=pending_messages,
            )

        save_state(self.state_root, state)
        return state, budget, committed_count

    def estimate_span_savings(
        self,
        turns: Sequence[TurnRecord],
        summary_text: str,
    ) -> int:
        raw_tokens = estimate_model_messages(
            flatten_turns(turns),
            model_name=self.model_name,
            calibration_factor=1.0,
        )
        projected_message_tokens = estimate_model_messages(
            [
                build_projected_summary_request(
                    CommittedSpan(
                        collapse_id="probe",
                        start_turn_id="probe-start",
                        end_turn_id="probe-end",
                        summary_text=summary_text,
                        projected_message_text=build_projected_message_text(
                            summary_text
                        ),
                    )
                )
            ],
            model_name=self.model_name,
            calibration_factor=1.0,
        )
        return max(0, raw_tokens - projected_message_tokens)

    def _next_collapse_id(self, state: CollapseState) -> str:
        collapse_id = f"{state.next_collapse_id:016d}"
        state.next_collapse_id += 1
        return collapse_id

    def _span_exists(self, state: CollapseState, start_turn_id: str, end_turn_id: str) -> bool:
        for span in state.staged_spans:
            if span.start_turn_id == start_turn_id and span.end_turn_id == end_turn_id:
                return True
        for span in state.committed_spans:
            if span.start_turn_id == start_turn_id and span.end_turn_id == end_turn_id:
                return True
        return False

    def _stage_chunks(
        self,
        turns: Sequence[TurnRecord],
        state: CollapseState,
    ) -> list[list[TurnRecord]]:
        if len(turns) <= max(self.config.preserve_recent_turns + 1, self.config.min_stage_turns + 1):
            return []

        committed_turn_ids = self._covered_turn_ids(turns, state.committed_spans)
        staged_turn_ids = self._covered_turn_ids(turns, state.staged_spans)

        candidate_end = len(turns) - self.config.preserve_recent_turns
        if candidate_end <= 1:
            return []

        chunks: list[list[TurnRecord]] = []
        index = 1
        while index < candidate_end:
            turn = turns[index]
            if turn.turn_id in committed_turn_ids or turn.turn_id in staged_turn_ids:
                index += 1
                continue

            run: list[TurnRecord] = []
            cursor = index
            while cursor < candidate_end:
                current = turns[cursor]
                if current.turn_id in committed_turn_ids or current.turn_id in staged_turn_ids:
                    break
                run.append(current)
                cursor += 1

            chunk_start = 0
            while chunk_start < len(run):
                chunk = run[chunk_start : chunk_start + self.config.max_stage_turns]
                if len(chunk) >= self.config.min_stage_turns:
                    chunks.append(chunk)
                chunk_start += self.config.max_stage_turns
            index = cursor + 1

        return chunks

    def _summarize_candidate(
        self,
        candidate: Sequence[TurnRecord],
        *,
        summarizer_agent: Any,
    ) -> StageSummary:
        prompt = build_summary_prompt(
            rendered_turns=render_turns_for_summary(candidate),
            turn_count=len(candidate),
        )
        with self.lock:
            state = self._load_state()
            state.health.staging_attempts += 1
            save_state(self.state_root, state)

        try:
            result = summarizer_agent.run_sync(prompt)
            summary_output = result.output
            if isinstance(summary_output, StageSummary):
                return summary_output
            if isinstance(summary_output, dict):
                return StageSummary.model_validate(summary_output)
            raise ValueError(f"Unexpected summary output type: {type(summary_output)!r}")
        except Exception as exc:
            with self.lock:
                state = self._load_state()
                state.health.staging_failures += 1
                state.health.last_error = str(exc)
                save_state(self.state_root, state)
            raise

    def _stage_summary_for_candidate(
        self,
        candidate: Sequence[TurnRecord],
        summary: StageSummary,
    ) -> tuple[StagedSpan | None, int]:
        staged = StagedSpan(
            start_turn_id=candidate[0].turn_id,
            end_turn_id=candidate[-1].turn_id,
            summary_text=summary.summary_text,
            risk=summary.risk,
        )
        expected_savings = self.estimate_span_savings(
            candidate,
            staged.summary_text,
        )

        with self.lock:
            state = self._load_state()
            if self._span_exists(state, staged.start_turn_id, staged.end_turn_id):
                save_state(self.state_root, state)
                return None, 0
            state.staged_spans.append(staged)
            state.health.last_error = None
            save_state(self.state_root, state)

        return staged, expected_savings

    def _covered_turn_ids(
        self,
        turns: Sequence[TurnRecord],
        spans: Sequence[StagedSpan | CommittedSpan],
    ) -> set[str]:
        turn_index = {turn.turn_id: index for index, turn in enumerate(turns)}
        covered: set[str] = set()
        for span in spans:
            start = turn_index.get(span.start_turn_id)
            end = turn_index.get(span.end_turn_id)
            if start is None or end is None or end < start:
                continue
            for turn in turns[start : end + 1]:
                covered.add(turn.turn_id)
        return covered
