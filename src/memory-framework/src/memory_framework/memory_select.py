from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from .memory_scan import MemoryHeader, format_memory_manifest


MAX_SELECTED_MEMORIES = 5


SELECT_MEMORIES_SYSTEM_PROMPT = """You are selecting memory files that will clearly help answer a user's current query.

You will be given the user's query and a manifest of available memory files with filenames and descriptions.

Return up to 5 filenames that will clearly be useful for the current query.
- Be selective and discerning.
- If you are unsure, do not include the memory.
- Prefer returning an empty list over weak matches.
- Return only filenames from the provided manifest."""


@dataclass(slots=True)
class MemorySelectionResult:
    selected_filenames: list[str]


def select_relevant_memories(
    *,
    model: str,
    query: str,
    headers: list[MemoryHeader],
    already_surfaced: set[str],
) -> list[MemoryHeader]:
    available = [header for header in headers if header.filename not in already_surfaced]
    if not available:
        return []

    agent = Agent(
        model,
        instructions=SELECT_MEMORIES_SYSTEM_PROMPT,
        output_type=MemorySelectionResult,
    )
    manifest = format_memory_manifest(available)
    result = agent.run_sync(
        f"Query: {query}\n\nAvailable memories:\n{manifest}"
    )

    valid_filenames = {header.filename for header in available}
    selected = []
    seen: set[str] = set()
    for filename in result.output.selected_filenames:
        if filename in valid_filenames and filename not in seen:
            selected.append(filename)
            seen.add(filename)
        if len(selected) >= MAX_SELECTED_MEMORIES:
            break

    by_filename = {header.filename: header for header in available}
    return [by_filename[filename] for filename in selected]
