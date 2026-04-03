from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MemoryDeps:
    memory_root: Path
    max_index_lines: int = 200
    max_index_bytes: int = 25_000
    index_snippet: str = ""
    selected_memories_text: str = ""
