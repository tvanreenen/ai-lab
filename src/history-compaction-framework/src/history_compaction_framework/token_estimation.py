from __future__ import annotations

import json
import math
from typing import Any, Iterable, Sequence

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse

try:
    import tiktoken
except ImportError:  # pragma: no cover - optional import during partial installs
    tiktoken = None


_ENCODING_CACHE: dict[str, Any] = {}


def get_encoding_for_model(model_name: str | None) -> Any | None:
    if tiktoken is None:
        return None

    key = model_name or "__default__"
    cached = _ENCODING_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        encoding = tiktoken.encoding_for_model(model_name or "gpt-5")
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    _ENCODING_CACHE[key] = encoding
    return encoding


def estimate_text_tokens(text: str, *, model_name: str | None = None) -> int:
    cleaned = text.strip()
    if not cleaned:
        return 0

    encoding = get_encoding_for_model(model_name)
    if encoding is None:
        return max(1, math.ceil(len(cleaned) / 4))
    return max(1, len(encoding.encode(cleaned)))


def estimate_model_messages(
    messages: Sequence[ModelMessage],
    *,
    model_name: str | None = None,
    calibration_factor: float = 1.0,
) -> int:
    total = 0
    for message in messages:
        total += estimate_message_tokens(message, model_name=model_name)
    return int(total * max(1.0, calibration_factor))


def estimate_message_tokens(
    message: ModelMessage,
    *,
    model_name: str | None = None,
) -> int:
    if isinstance(message, ModelRequest):
        parts = message.parts
        instructions = message.instructions or ""
        total = estimate_text_tokens(instructions, model_name=model_name)
        total += sum(
            estimate_part_tokens(part, model_name=model_name) for part in parts
        )
        return total
    if isinstance(message, ModelResponse):
        return sum(
            estimate_part_tokens(part, model_name=model_name)
            for part in message.parts
        )
    return 0


def estimate_part_tokens(part: Any, *, model_name: str | None = None) -> int:
    total = 0
    for chunk in iter_part_text(part):
        total += estimate_text_tokens(chunk, model_name=model_name)
    return total


def iter_part_text(part: Any) -> Iterable[str]:
    content = getattr(part, "content", None)
    if isinstance(content, str):
        yield content
    elif isinstance(content, Sequence) and not isinstance(
        content, (bytes, bytearray, str)
    ):
        for item in content:
            if isinstance(item, str):
                yield item
            elif hasattr(item, "text"):
                text = getattr(item, "text")
                if isinstance(text, str):
                    yield text
            else:
                yield json.dumps(item, default=str, sort_keys=True)

    for attr in ("tool_name", "model_name", "part_kind"):
        value = getattr(part, attr, None)
        if isinstance(value, str):
            yield value

    args = getattr(part, "args", None)
    if args is not None:
        yield json.dumps(args, default=str, sort_keys=True)

    metadata = getattr(part, "metadata", None)
    if metadata:
        yield json.dumps(metadata, default=str, sort_keys=True)
