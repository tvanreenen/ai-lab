from __future__ import annotations

from pathlib import Path
import re

from .memory_maintenance import STATE_FILENAME


def ensure_memory_layout(memory_root: Path) -> None:
    topics_dir = memory_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    index_path = memory_root / "MEMORY.md"
    if not index_path.exists():
        index_path.write_text("", encoding="utf-8")


def resolve_memory_path(memory_root: Path, raw_path: str) -> Path:
    if not raw_path.strip():
        raise ValueError("Path must not be empty.")

    candidate = Path(raw_path)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = (memory_root / candidate).resolve(strict=False)

    root_resolved = memory_root.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes memory root: {raw_path}") from exc
    relative = resolved.relative_to(root_resolved)
    if any(part.startswith(".") for part in relative.parts):
        raise ValueError(f"Path is reserved for framework internals: {raw_path}")
    return resolved


def iter_memory_files(memory_root: Path) -> list[Path]:
    if not memory_root.exists():
        return []
    return sorted(
        path
        for path in memory_root.rglob("*")
        if path.is_file() and path.name != ".gitkeep" and not is_internal_file(path, memory_root)
    )


def is_internal_file(path: Path, memory_root: Path) -> bool:
    try:
        relative = path.relative_to(memory_root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts) or path.name == STATE_FILENAME


def read_index(memory_root: Path) -> str:
    index_path = memory_root / "MEMORY.md"
    if not index_path.exists():
        return ""
    return index_path.read_text(encoding="utf-8")


def snapshot_memory_files(memory_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in iter_memory_files(memory_root):
        relative = path.relative_to(memory_root).as_posix()
        snapshot[relative] = path.read_text(encoding="utf-8")
    return snapshot


def format_memory_manifest(memory_root: Path) -> str:
    files = iter_memory_files(memory_root)
    if not files:
        return ""

    lines: list[str] = []
    for path in files:
        relative = path.relative_to(memory_root).as_posix()
        summary = ""
        if path.suffix == ".md" and path.name != "MEMORY.md":
            summary = extract_frontmatter_description(path)
        if summary:
            lines.append(f"- `{relative}` — {summary}")
        else:
            lines.append(f"- `{relative}`")
    return "\n".join(lines)


def extract_frontmatter_description(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def diff_touched_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    touched: list[str] = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            touched.append(path)
    return touched


def render_memory_tree(memory_root: Path) -> str:
    files = iter_memory_files(memory_root)
    if not files:
        return "(memory directory is empty)"

    sections: list[str] = []
    for path in files:
        relative = path.relative_to(memory_root).as_posix()
        content = path.read_text(encoding="utf-8").strip()
        body = content if content else "(empty)"
        sections.append(f"=== {relative} ===\n{body}")
    return "\n\n".join(sections)
