from __future__ import annotations

import json

from .engine import RequestBudget
from .models import CollapseState, CompactionConfig


def render_staged_spans(state: CollapseState) -> str:
    if not state.staged_spans:
        return "(no staged spans)"
    return "\n\n".join(
        [
            "\n".join(
                [
                    f"start_turn_id: {span.start_turn_id}",
                    f"end_turn_id: {span.end_turn_id}",
                    f"risk: {span.risk:.2f}",
                    f"staged_at: {span.staged_at.isoformat()}",
                    f"summary_text: {span.summary_text}",
                ]
            )
            for span in state.staged_spans
        ]
    )


def render_committed_spans(state: CollapseState) -> str:
    if not state.committed_spans:
        return "(no committed spans)"
    return "\n\n".join(
        [
            "\n".join(
                [
                    f"collapse_id: {span.collapse_id}",
                    f"start_turn_id: {span.start_turn_id}",
                    f"end_turn_id: {span.end_turn_id}",
                    f"committed_at: {span.committed_at.isoformat()}",
                    f"summary_text: {span.summary_text}",
                ]
            )
            for span in state.committed_spans
        ]
    )


def render_state_json(
    *,
    config: CompactionConfig,
    state: CollapseState,
    budget: RequestBudget,
) -> str:
    payload = {
        "context_window": config.context_window,
        "pressure_threshold": config.pressure_threshold,
        "stage_threshold": config.stage_threshold,
        "target_threshold": config.target_threshold,
        "guard_threshold": config.guard_threshold,
        "fail_threshold": config.fail_threshold,
        "estimated_projected_tokens": budget.projected_tokens,
        "estimated_pending_tokens": budget.pending_tokens,
        "estimated_request_tokens": budget.request_tokens,
        "under_pressure": state.under_pressure,
        "last_stage_check_request_tokens": state.last_stage_check_request_tokens,
        "committed_spans": len(state.committed_spans),
        "staged_spans": len(state.staged_spans),
        "last_recovery": state.last_recovery.model_dump(mode="json"),
        "health": state.health.model_dump(mode="json"),
        "calibration": state.calibration.model_dump(mode="json"),
    }
    return json.dumps(payload, indent=2)
