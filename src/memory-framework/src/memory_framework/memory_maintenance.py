from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


INDEX_LINE_RE = re.compile(
    r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)\s*(?:—|-)\s*(?P<hook>.+?)\s*$"
)
MAX_INDEX_LINE_LENGTH = 150
SOFT_INDEX_LINE_BUDGET = 180
SOFT_INDEX_BYTE_BUDGET = 20_000
VALID_MEMORY_TYPES = {"user", "feedback", "project", "reference"}
STATE_FILENAME = ".memory-framework-state.json"

DEFAULT_CONSOLIDATION_MIN_HOURS = 6
DEFAULT_CONSOLIDATION_MIN_WRITES = 8
DEFAULT_CONSOLIDATION_MIN_DISTINCT_FILES = 4


@dataclass(slots=True)
class MemoryIndexEntry:
    title: str
    target: str
    hook: str
    raw_line: str
    line_number: int


@dataclass(slots=True)
class MemoryStoreStats:
    index_line_count: int
    index_bytes: int
    topic_file_count: int


@dataclass(slots=True)
class MemoryAudit:
    stats: MemoryStoreStats
    broken_links: list[str] = field(default_factory=list)
    duplicate_targets: list[str] = field(default_factory=list)
    duplicate_lines: list[str] = field(default_factory=list)
    malformed_index_lines: list[str] = field(default_factory=list)
    oversized_index_lines: list[str] = field(default_factory=list)
    orphan_topic_files: list[str] = field(default_factory=list)
    invalid_frontmatter: list[str] = field(default_factory=list)
    exact_duplicate_topic_files: list[list[str]] = field(default_factory=list)

    @property
    def has_soft_pressure(self) -> bool:
        return any(
            [
                self.stats.index_line_count > SOFT_INDEX_LINE_BUDGET,
                self.stats.index_bytes > SOFT_INDEX_BYTE_BUDGET,
                bool(self.broken_links),
                bool(self.malformed_index_lines),
                bool(self.exact_duplicate_topic_files),
            ]
        )


@dataclass(slots=True)
class ConsolidationState:
    last_consolidated_at: float = 0.0
    writes_since_consolidation: int = 0
    touched_topic_files_since_consolidation: list[str] = field(default_factory=list)

    @property
    def distinct_topic_files_touched_since_consolidation(self) -> int:
        return len(set(self.touched_topic_files_since_consolidation))


def parse_memory_index(index_text: str) -> tuple[list[MemoryIndexEntry], list[str]]:
    entries: list[MemoryIndexEntry] = []
    malformed: list[str] = []
    for line_number, line in enumerate(index_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        match = INDEX_LINE_RE.match(stripped)
        if not match:
            malformed.append(f"line {line_number}: {stripped}")
            continue
        entries.append(
            MemoryIndexEntry(
                title=match.group("title").strip(),
                target=match.group("target").strip(),
                hook=match.group("hook").strip(),
                raw_line=stripped,
                line_number=line_number,
            )
        )
    return entries, malformed


def normalize_memory_index(
    memory_root: Path,
    *,
    max_lines: int = 200,
    max_bytes: int = 25_000,
    required_targets: list[str] | None = None,
) -> list[str]:
    index_path = memory_root / "MEMORY.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    entries, _ = parse_memory_index(index_text)
    duplicate_map = _build_duplicate_topic_map(memory_root)

    canonical_entries: dict[str, MemoryIndexEntry] = {}
    last_seen_order: dict[str, int] = {}
    for position, entry in enumerate(entries):
        canonical_target = duplicate_map.get(entry.target, entry.target)
        canonical_path = memory_root / canonical_target
        if not canonical_path.exists() or not canonical_path.is_file():
            continue
        normalized = MemoryIndexEntry(
            title=_clean_index_text(entry.title),
            target=canonical_target,
            hook=_clean_index_text(entry.hook),
            raw_line=entry.raw_line,
            line_number=entry.line_number,
        )
        canonical_entries[canonical_target] = normalized
        last_seen_order[canonical_target] = position

    for raw_target in required_targets or []:
        canonical_target = duplicate_map.get(raw_target, raw_target)
        target_path = memory_root / canonical_target
        if not target_path.exists() or not target_path.is_file():
            continue
        if canonical_target not in canonical_entries:
            title, hook = _default_index_metadata(target_path, canonical_target)
            canonical_entries[canonical_target] = MemoryIndexEntry(
                title=title,
                target=canonical_target,
                hook=hook,
                raw_line="",
                line_number=len(entries) + len(canonical_entries),
            )
            last_seen_order[canonical_target] = len(entries) + len(canonical_entries)

    ordered_targets = sorted(last_seen_order, key=last_seen_order.get)
    lines = [
        _format_index_line(
            title=canonical_entries[target].title,
            target=target,
            hook=canonical_entries[target].hook,
        )
        for target in ordered_targets
    ]
    lines = _cap_index_lines(lines, max_lines=max_lines, max_bytes=max_bytes)
    normalized_text = ("\n".join(lines) + "\n") if lines else ""

    if normalized_text != index_text:
        index_path.write_text(normalized_text, encoding="utf-8")
        return ["MEMORY.md"]
    return []


def audit_memory_store(memory_root: Path) -> MemoryAudit:
    index_text = (memory_root / "MEMORY.md").read_text(encoding="utf-8") if (memory_root / "MEMORY.md").exists() else ""
    entries, malformed = parse_memory_index(index_text)
    topic_paths = _iter_topic_files(memory_root)
    topic_relatives = [path.relative_to(memory_root).as_posix() for path in topic_paths]
    duplicate_map = _build_duplicate_topic_map(memory_root)

    duplicate_target_counts: dict[str, int] = {}
    duplicate_line_counts: dict[str, int] = {}
    referenced_targets: set[str] = set()
    broken_links: list[str] = []
    oversized_lines: list[str] = []

    for entry in entries:
        canonical_target = duplicate_map.get(entry.target, entry.target)
        duplicate_target_counts[canonical_target] = duplicate_target_counts.get(canonical_target, 0) + 1
        duplicate_line_counts[entry.raw_line] = duplicate_line_counts.get(entry.raw_line, 0) + 1
        if len(entry.raw_line) > MAX_INDEX_LINE_LENGTH:
            oversized_lines.append(f"line {entry.line_number}: {entry.raw_line}")
        target_path = memory_root / canonical_target
        if target_path.exists() and target_path.is_file():
            referenced_targets.add(canonical_target)
        else:
            broken_links.append(f"line {entry.line_number}: {entry.target}")

    invalid_frontmatter: list[str] = []
    for path in topic_paths:
        metadata, _ = _read_topic_metadata(path)
        missing = [key for key in ("name", "description", "type") if not metadata.get(key)]
        invalid_type = metadata.get("type") not in VALID_MEMORY_TYPES
        if missing or invalid_type:
            details = ", ".join(missing + (["invalid type"] if invalid_type else []))
            invalid_frontmatter.append(f"{path.relative_to(memory_root).as_posix()}: {details}")

    exact_duplicates = _group_exact_duplicate_topics(memory_root)
    orphan_topic_files = sorted(path for path in topic_relatives if duplicate_map.get(path, path) not in referenced_targets)

    stats = MemoryStoreStats(
        index_line_count=len([line for line in index_text.splitlines() if line.strip()]),
        index_bytes=len(index_text.encode("utf-8")),
        topic_file_count=len(topic_paths),
    )
    return MemoryAudit(
        stats=stats,
        broken_links=broken_links,
        duplicate_targets=sorted(
            f"{target} ({count} entries)"
            for target, count in duplicate_target_counts.items()
            if count > 1
        ),
        duplicate_lines=sorted(
            line
            for line, count in duplicate_line_counts.items()
            if count > 1
        ),
        malformed_index_lines=malformed,
        oversized_index_lines=oversized_lines,
        orphan_topic_files=orphan_topic_files,
        invalid_frontmatter=invalid_frontmatter,
        exact_duplicate_topic_files=exact_duplicates,
    )


def format_audit_for_prompt(audit: MemoryAudit) -> str:
    lines = [
        "## Audit findings",
        "",
        f"- index lines: {audit.stats.index_line_count}",
        f"- index bytes: {audit.stats.index_bytes}",
        f"- topic files: {audit.stats.topic_file_count}",
        f"- broken links: {len(audit.broken_links)}",
        f"- duplicate targets: {len(audit.duplicate_targets)}",
        f"- duplicate lines: {len(audit.duplicate_lines)}",
        f"- malformed index lines: {len(audit.malformed_index_lines)}",
        f"- oversized index lines: {len(audit.oversized_index_lines)}",
        f"- orphan topic files: {len(audit.orphan_topic_files)}",
        f"- invalid frontmatter files: {len(audit.invalid_frontmatter)}",
        f"- exact duplicate topic groups: {len(audit.exact_duplicate_topic_files)}",
    ]
    detail_sections = [
        ("Broken links", audit.broken_links),
        ("Duplicate targets", audit.duplicate_targets),
        ("Duplicate literal lines", audit.duplicate_lines),
        ("Malformed index lines", audit.malformed_index_lines),
        ("Oversized index lines", audit.oversized_index_lines),
        ("Orphan topic files", audit.orphan_topic_files),
        ("Invalid frontmatter", audit.invalid_frontmatter),
    ]
    for title, values in detail_sections:
        if not values:
            continue
        lines.extend(["", f"### {title}"])
        lines.extend(f"- {value}" for value in values[:20])
    if audit.exact_duplicate_topic_files:
        lines.extend(["", "### Exact duplicate topic groups"])
        lines.extend(f"- {', '.join(group)}" for group in audit.exact_duplicate_topic_files[:20])
    return "\n".join(lines)


def apply_write_hygiene(memory_root: Path, *, touched_paths: list[str]) -> list[str]:
    changed: set[str] = set()
    changed.update(_normalize_topic_frontmatter(memory_root))
    required_targets = [path for path in touched_paths if path.startswith("topics/") and path.endswith(".md")]
    changed.update(
        normalize_memory_index(
            memory_root,
            required_targets=required_targets,
        )
    )
    return sorted(changed)


def apply_post_consolidation_hygiene(memory_root: Path) -> list[str]:
    changed: set[str] = set()
    changed.update(_normalize_topic_frontmatter(memory_root))
    changed.update(normalize_memory_index(memory_root))
    return sorted(changed)


def record_memory_activity(memory_root: Path, touched_paths: list[str]) -> ConsolidationState:
    relevant = [path for path in touched_paths if _is_memory_artifact(path)]
    state = _load_state(memory_root)
    if relevant:
        state.writes_since_consolidation += 1
        state.touched_topic_files_since_consolidation.extend(
            path for path in relevant if path.startswith("topics/") and path.endswith(".md")
        )
        _save_state(memory_root, state)
    return state


def should_run_consolidation(memory_root: Path, audit: MemoryAudit) -> bool:
    state = _load_state(memory_root)
    hours_since = (datetime.now(tz=timezone.utc).timestamp() - state.last_consolidated_at) / 3600
    time_gate_open = hours_since >= DEFAULT_CONSOLIDATION_MIN_HOURS
    activity_gate_open = (
        state.writes_since_consolidation >= DEFAULT_CONSOLIDATION_MIN_WRITES
        or state.distinct_topic_files_touched_since_consolidation >= DEFAULT_CONSOLIDATION_MIN_DISTINCT_FILES
        or audit.has_soft_pressure
    )
    return time_gate_open and activity_gate_open


def mark_consolidated(memory_root: Path) -> None:
    state = ConsolidationState(
        last_consolidated_at=datetime.now(tz=timezone.utc).timestamp(),
        writes_since_consolidation=0,
        touched_topic_files_since_consolidation=[],
    )
    _save_state(memory_root, state)


def _normalize_topic_frontmatter(memory_root: Path) -> list[str]:
    changed: list[str] = []
    for path in _iter_topic_files(memory_root):
        metadata, body = _read_topic_metadata(path)
        normalized = {
            "name": metadata.get("name") or _derive_name_from_path(path),
            "description": metadata.get("description") or _derive_description(body),
            "type": metadata.get("type") if metadata.get("type") in VALID_MEMORY_TYPES else "reference",
        }
        normalized_text = _render_topic_file(normalized, body)
        current_text = path.read_text(encoding="utf-8")
        if normalized_text != current_text:
            path.write_text(normalized_text, encoding="utf-8")
            changed.append(path.relative_to(memory_root).as_posix())
    return changed


def _iter_topic_files(memory_root: Path) -> list[Path]:
    topics_dir = memory_root / "topics"
    if not topics_dir.exists():
        return []
    return sorted(path for path in topics_dir.rglob("*.md") if path.is_file())


def _build_duplicate_topic_map(memory_root: Path) -> dict[str, str]:
    groups = _group_exact_duplicate_topics(memory_root)
    duplicate_map: dict[str, str] = {}
    for group in groups:
        canonical = sorted(group)[0]
        for filename in group:
            duplicate_map[filename] = canonical
    return duplicate_map


def _group_exact_duplicate_topics(memory_root: Path) -> list[list[str]]:
    buckets: dict[str, list[str]] = {}
    for path in _iter_topic_files(memory_root):
        content = path.read_text(encoding="utf-8")
        normalized = _normalize_topic_body_for_dedup(content)
        buckets.setdefault(normalized, []).append(path.relative_to(memory_root).as_posix())
    return [sorted(group) for group in buckets.values() if len(group) > 1]


def _normalize_topic_body_for_dedup(text: str) -> str:
    metadata, body = _parse_topic_text(text)
    memory_type = metadata.get("type", "reference")
    normalized_body = "\n".join(line.strip() for line in body.strip().splitlines() if line.strip())
    return f"type={memory_type}\n{normalized_body}"


def _read_topic_metadata(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    return _parse_topic_text(text)


def _parse_topic_text(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    body_start = 0
    if len(lines) >= 3 and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body_start = index + 1
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    body = "\n".join(lines[body_start:]).strip()
    return metadata, body


def _render_topic_file(metadata: dict[str, str], body: str) -> str:
    frontmatter_lines = [
        "---",
        f"name: {metadata['name']}",
        f"description: {metadata['description']}",
        f"type: {metadata['type']}",
        "---",
        "",
    ]
    cleaned_body = body.strip()
    if cleaned_body:
        return "\n".join(frontmatter_lines + [cleaned_body, ""])
    return "\n".join(frontmatter_lines)


def _default_index_metadata(path: Path, relative_target: str) -> tuple[str, str]:
    metadata, body = _read_topic_metadata(path)
    title = metadata.get("name") or _derive_name_from_path(path)
    hook = metadata.get("description") or _derive_description(body)
    if not hook:
        hook = relative_target
    return title, hook


def _derive_name_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip().title() or "Memory"


def _derive_description(body: str) -> str:
    for line in body.splitlines():
        cleaned = line.strip().lstrip("-*").strip()
        if cleaned:
            return _clean_index_text(cleaned, limit=110)
    return "Durable memory"


def _clean_index_text(value: str, *, limit: int = 90) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _format_index_line(*, title: str, target: str, hook: str) -> str:
    title_text = _clean_index_text(title, limit=50) or "Memory"
    hook_budget = max(20, MAX_INDEX_LINE_LENGTH - len(f"- [{title_text}]({target}) — "))
    hook_text = _clean_index_text(hook, limit=hook_budget) or target
    return f"- [{title_text}]({target}) — {hook_text}"


def _cap_index_lines(lines: list[str], *, max_lines: int, max_bytes: int) -> list[str]:
    kept = lines[-max_lines:]
    while kept and len(("\n".join(kept) + "\n").encode("utf-8")) > max_bytes:
        kept.pop(0)
    return kept


def _load_state(memory_root: Path) -> ConsolidationState:
    path = memory_root / STATE_FILENAME
    if not path.exists():
        return ConsolidationState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ConsolidationState()
    return ConsolidationState(
        last_consolidated_at=float(payload.get("last_consolidated_at", 0.0) or 0.0),
        writes_since_consolidation=int(payload.get("writes_since_consolidation", 0) or 0),
        touched_topic_files_since_consolidation=[
            str(item)
            for item in payload.get("touched_topic_files_since_consolidation", [])
            if isinstance(item, str)
        ],
    )


def _save_state(memory_root: Path, state: ConsolidationState) -> None:
    path = memory_root / STATE_FILENAME
    payload: dict[str, Any] = asdict(state)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_memory_artifact(path: str) -> bool:
    return path == "MEMORY.md" or path.startswith("topics/")
