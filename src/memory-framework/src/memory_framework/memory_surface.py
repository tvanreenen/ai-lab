from __future__ import annotations

from datetime import datetime, timezone

from .memory_scan import MemoryHeader


MAX_SURFACED_MEMORY_LINES = 80
MAX_SURFACED_MEMORY_BYTES = 8_000


def surface_selected_memories(headers: list[MemoryHeader]) -> str:
    if not headers:
        return "(no relevant topic memories surfaced for this turn)"

    blocks: list[str] = []
    for header in headers:
        content = header.file_path.read_text(encoding="utf-8").strip()
        truncated_content, truncated = _truncate_memory_content(content)
        saved_text = datetime.fromtimestamp(
            header.mtime_ms / 1000,
            tz=timezone.utc,
        ).isoformat()
        suffix = ""
        if truncated:
            suffix = (
                "\n\n> This memory file was truncated for the prompt. Use the saved content "
                "here as context, but remember the original file contains more detail."
            )
        blocks.append(
            "\n".join(
                [
                    f"Memory ({saved_text}): {header.filename}",
                    "",
                    truncated_content + suffix,
                ]
            )
        )

    return "\n\n".join(blocks)


def _truncate_memory_content(content: str) -> tuple[str, bool]:
    if not content:
        return "(empty)", False

    lines = content.splitlines()
    truncated = lines[:MAX_SURFACED_MEMORY_LINES]
    text = "\n".join(truncated)
    was_truncated = len(lines) > MAX_SURFACED_MEMORY_LINES

    encoded = text.encode("utf-8")
    if len(encoded) > MAX_SURFACED_MEMORY_BYTES:
        candidate = encoded[:MAX_SURFACED_MEMORY_BYTES]
        cut_at = candidate.rfind(b"\n")
        if cut_at > 0:
            candidate = candidate[:cut_at]
        text = candidate.decode("utf-8", errors="ignore").rstrip()
        was_truncated = True

    return text, was_truncated
