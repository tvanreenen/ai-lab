from __future__ import annotations

from pydantic_ai import RunContext

from .deps import MemoryDeps
from .store import iter_memory_files, resolve_memory_path


def list_memory_files(ctx: RunContext[MemoryDeps]) -> str:
    """List files currently stored under the memory directory."""
    files = iter_memory_files(ctx.deps.memory_root)
    if not files:
        return "(no memory files yet)"
    return "\n".join(path.relative_to(ctx.deps.memory_root).as_posix() for path in files)


def read_memory_file(ctx: RunContext[MemoryDeps], path: str) -> str:
    """Read a memory file by relative path inside the memory directory."""
    resolved = resolve_memory_path(ctx.deps.memory_root, path)
    if not resolved.exists() or not resolved.is_file():
        return f"Memory file does not exist: {path}"
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Could not read memory file {path}: {exc}"


def grep_memory(ctx: RunContext[MemoryDeps], query: str) -> str:
    """Search for a plain-text query across memory files and return matching lines."""
    needle = query.strip()
    if not needle:
        raise ValueError("Search query must not be empty.")

    matches: list[str] = []
    lowered = needle.lower()
    for path in iter_memory_files(ctx.deps.memory_root):
        relative = path.relative_to(ctx.deps.memory_root).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if lowered in line.lower():
                matches.append(f"{relative}:{line_number}: {line}")
                if len(matches) >= 20:
                    return "\n".join(matches)
    return "\n".join(matches) if matches else "(no matches)"


def write_memory_file(ctx: RunContext[MemoryDeps], path: str, content: str) -> str:
    """Write a memory file by relative path inside the memory directory."""
    resolved = resolve_memory_path(ctx.deps.memory_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"Could not write memory file {path}: {exc}"
    return f"Wrote {resolved.relative_to(ctx.deps.memory_root).as_posix()}"


def delete_memory_file(ctx: RunContext[MemoryDeps], path: str) -> str:
    """Delete a memory file by relative path inside the memory directory."""
    resolved = resolve_memory_path(ctx.deps.memory_root, path)
    if resolved.name == "MEMORY.md":
        raise ValueError("Deleting MEMORY.md is not allowed.")
    if not resolved.exists() or not resolved.is_file():
        return f"Memory file does not exist: {path}"
    try:
        resolved.unlink()
    except OSError as exc:
        return f"Could not delete memory file {path}: {exc}"
    return f"Deleted {resolved.relative_to(ctx.deps.memory_root).as_posix()}"
