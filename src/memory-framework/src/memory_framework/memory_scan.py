from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


FRONTMATTER_MAX_LINES = 30


@dataclass(slots=True)
class MemoryHeader:
    filename: str
    file_path: Path
    mtime_ms: float
    description: str | None
    memory_type: str | None


def scan_memory_headers(memory_root: Path) -> list[MemoryHeader]:
    if not memory_root.exists():
        return []

    headers: list[MemoryHeader] = []
    for path in sorted(memory_root.rglob("*.md")):
        if path.name == "MEMORY.md":
            continue

        relative = path.relative_to(memory_root).as_posix()
        frontmatter = _read_frontmatter_block(path)
        headers.append(
            MemoryHeader(
                filename=relative,
                file_path=path,
                mtime_ms=path.stat().st_mtime * 1000,
                description=_extract_frontmatter_value(frontmatter, "description"),
                memory_type=_extract_frontmatter_value(frontmatter, "type"),
            )
        )

    headers.sort(key=lambda item: item.mtime_ms, reverse=True)
    return headers


def format_memory_manifest(headers: list[MemoryHeader]) -> str:
    return "\n".join(_format_manifest_line(header) for header in headers)


def _read_frontmatter_block(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    limited = lines[:FRONTMATTER_MAX_LINES]
    if len(limited) >= 2 and limited[0].strip() == "---":
        end_index = next(
            (index for index, line in enumerate(limited[1:], start=1) if line.strip() == "---"),
            None,
        )
        if end_index is not None:
            return "\n".join(limited[1:end_index])
    return "\n".join(limited)


def _extract_frontmatter_value(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _format_manifest_line(header: MemoryHeader) -> str:
    tag = f"[{header.memory_type}] " if header.memory_type else ""
    timestamp = _format_iso_like(header.mtime_ms)
    if header.description:
        return f"- {tag}{header.filename} ({timestamp}): {header.description}"
    return f"- {tag}{header.filename} ({timestamp})"


def _format_iso_like(mtime_ms: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(mtime_ms / 1000, tz=timezone.utc).isoformat()
