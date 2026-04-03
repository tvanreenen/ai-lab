from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MAX_INDEX_LINES = 200
DEFAULT_MAX_INDEX_BYTES = 25_000


@dataclass(slots=True)
class EntrypointTruncation:
    content: str
    line_count: int
    byte_count: int
    was_line_truncated: bool
    was_byte_truncated: bool


def _format_file_size(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count} B"
    kib = byte_count / 1024
    if kib < 1024:
        return f"{kib:.1f} KiB"
    mib = kib / 1024
    return f"{mib:.1f} MiB"


def truncate_entrypoint_content(
    raw: str,
    *,
    max_lines: int = DEFAULT_MAX_INDEX_LINES,
    max_bytes: int = DEFAULT_MAX_INDEX_BYTES,
) -> EntrypointTruncation:
    trimmed = raw.strip()
    if not trimmed:
        return EntrypointTruncation(
            content="",
            line_count=0,
            byte_count=0,
            was_line_truncated=False,
            was_byte_truncated=False,
        )

    content_lines = trimmed.splitlines()
    line_count = len(content_lines)
    byte_count = len(trimmed.encode("utf-8"))

    was_line_truncated = line_count > max_lines
    was_byte_truncated = byte_count > max_bytes

    if not was_line_truncated and not was_byte_truncated:
        return EntrypointTruncation(
            content=trimmed,
            line_count=line_count,
            byte_count=byte_count,
            was_line_truncated=False,
            was_byte_truncated=False,
        )

    truncated = "\n".join(content_lines[:max_lines]) if was_line_truncated else trimmed
    truncated_bytes = truncated.encode("utf-8")
    if len(truncated_bytes) > max_bytes:
        candidate = truncated_bytes[:max_bytes]
        cut_at = candidate.rfind(b"\n")
        if cut_at > 0:
            candidate = candidate[:cut_at]
        truncated = candidate.decode("utf-8", errors="ignore").rstrip()

    if was_byte_truncated and not was_line_truncated:
        reason = (
            f"{_format_file_size(byte_count)} "
            f"(limit: {_format_file_size(max_bytes)}) — index entries are too long"
        )
    elif was_line_truncated and not was_byte_truncated:
        reason = f"{line_count} lines (limit: {max_lines})"
    else:
        reason = f"{line_count} lines and {_format_file_size(byte_count)}"

    warning = (
        "\n\n> WARNING: MEMORY.md is "
        f"{reason}. Only part of it was loaded. Keep index entries to one line "
        "under ~200 chars; move detail into topic files."
    )
    return EntrypointTruncation(
        content=truncated + warning,
        line_count=line_count,
        byte_count=byte_count,
        was_line_truncated=was_line_truncated,
        was_byte_truncated=was_byte_truncated,
    )
