from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Sequence, cast

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from .models import CollapseState, TurnRecord


HISTORY_FILENAME = "history.jsonl"
STATE_FILENAME = "collapse_state.json"


def ensure_layout(state_root: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    history_path = state_root / HISTORY_FILENAME
    if not history_path.exists():
        history_path.write_text("", encoding="utf-8")
    state_path = state_root / STATE_FILENAME
    if not state_path.exists():
        state_path.write_text(
            json.dumps(CollapseState().model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )


def history_path(state_root: Path) -> Path:
    return state_root / HISTORY_FILENAME


def collapse_state_path(state_root: Path) -> Path:
    return state_root / STATE_FILENAME


def serialize_model_messages(messages: Sequence[ModelMessage]) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        ModelMessagesTypeAdapter.dump_python(list(messages), mode="json"),
    )


def deserialize_model_messages(payload: list[dict[str, Any]]) -> list[ModelMessage]:
    return list(ModelMessagesTypeAdapter.validate_python(payload))


def append_turn(state_root: Path, record: TurnRecord) -> None:
    ensure_layout(state_root)
    with history_path(state_root).open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json())
        handle.write("\n")


def load_turns(state_root: Path) -> list[TurnRecord]:
    ensure_layout(state_root)
    records: list[TurnRecord] = []
    with history_path(state_root).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            records.append(TurnRecord.model_validate_json(stripped))
    return records


def load_state(state_root: Path) -> CollapseState:
    ensure_layout(state_root)
    raw = collapse_state_path(state_root).read_text(encoding="utf-8").strip()
    if not raw:
        return CollapseState()
    return CollapseState.model_validate_json(raw)


def save_state(state_root: Path, state: CollapseState) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    path = collapse_state_path(state_root)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def reset_state_root(state_root: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    history_path(state_root).write_text("", encoding="utf-8")
    save_state(state_root, CollapseState())
