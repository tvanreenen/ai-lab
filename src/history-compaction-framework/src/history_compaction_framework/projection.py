from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from .models import CollapseState, CommittedSpan, TurnRecord


@dataclass(slots=True)
class ProjectedHistory:
    messages: list[ModelMessage]
    covered_turn_ids: list[str]


def flatten_turns(turns: Sequence[TurnRecord]) -> list[ModelMessage]:
    from .storage import deserialize_model_messages

    messages: list[ModelMessage] = []
    for turn in turns:
        messages.extend(deserialize_model_messages(turn.messages))
    return messages


def build_projected_history(
    turns: Sequence[TurnRecord],
    state: CollapseState,
) -> ProjectedHistory:
    turn_index = {turn.turn_id: index for index, turn in enumerate(turns)}
    committed = sorted(
        state.committed_spans,
        key=lambda span: (turn_index.get(span.start_turn_id, 10**9), span.committed_at),
    )
    projected: list[ModelMessage] = []
    covered_turn_ids: list[str] = []
    span_by_start = {span.start_turn_id: span for span in committed}

    index = 0
    while index < len(turns):
        turn = turns[index]
        span = span_by_start.get(turn.turn_id)
        if span is None:
            projected.extend(flatten_turns([turn]))
            covered_turn_ids.append(turn.turn_id)
            index += 1
            continue

        end_index = turn_index.get(span.end_turn_id)
        if end_index is None or end_index < index:
            projected.extend(flatten_turns([turn]))
            covered_turn_ids.append(turn.turn_id)
            index += 1
            continue

        projected.append(build_projected_summary_request(span))
        covered_turn_ids.extend(t.turn_id for t in turns[index : end_index + 1])
        index = end_index + 1

    return ProjectedHistory(messages=projected, covered_turn_ids=covered_turn_ids)


def build_projected_summary_request(span: CommittedSpan) -> ModelRequest:
    return ModelRequest(
        parts=[UserPromptPart(content=span.projected_message_text)],
        metadata={
            "synthetic": "collapsed-summary",
            "collapse_id": span.collapse_id,
            "start_turn_id": span.start_turn_id,
            "end_turn_id": span.end_turn_id,
        },
    )


def render_turns(turns: Sequence[TurnRecord]) -> str:
    if not turns:
        return "(no turns recorded)"
    sections = []
    for turn in turns:
        sections.append(f"=== {turn.turn_id} @ {turn.timestamp.isoformat()} ===")
        sections.append(f"[user]\n{turn.user_text}")
        sections.append("[messages]")
        sections.append(json.dumps(turn.messages, indent=2, default=str))
    return "\n\n".join(sections)


def render_projected_messages(messages: Sequence[ModelMessage]) -> str:
    if not messages:
        return "(projected history is empty)"
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        lines.append(f"=== message {index} ===")
        lines.append(type(message).__name__)
        lines.append(json.dumps(message_to_jsonable(message), indent=2, default=str))
    return "\n\n".join(lines)


def message_to_jsonable(message: ModelMessage) -> dict[str, Any]:
    from .storage import serialize_model_messages

    return serialize_model_messages([message])[0]


def render_turns_for_summary(turns: Sequence[TurnRecord]) -> str:
    if not turns:
        return "(no eligible turns)"

    sections: list[str] = []
    for turn in turns:
        sections.append(f"## Turn {turn.turn_id}")
        sections.append(f"Timestamp: {turn.timestamp.isoformat()}")
        sections.append(f"User: {turn.user_text}")
        sections.append("Raw messages:")
        sections.append(json.dumps(turn.messages, indent=2, default=str))
    return "\n\n".join(sections)
