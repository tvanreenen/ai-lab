from __future__ import annotations

from datetime import date


TOPIC_FRONTMATTER_EXAMPLE = """```markdown
---
name: {{memory name}}
description: {{one-line description — used to decide relevance in future conversations, so be specific}}
type: {{user, feedback, project, reference}}
---

{{memory content — for feedback/project types, structure as: rule/fact, then **Why:** and **How to apply:** lines}}
```"""


TYPES_SECTION = """## Types of memory

There are several discrete types of memory that can be stored in this system:

- `user`: facts about the user's role, goals, preferences, responsibilities, and knowledge
- `feedback`: guidance about how the assistant should approach work, including corrections and confirmed successful approaches
- `project`: durable non-derivable context about goals, incidents, constraints, timelines, and ongoing work
- `reference`: pointers to useful external systems or resources outside the repo

For `feedback` and `project` memories, lead with the rule or fact, then include `**Why:**` and `**How to apply:**` lines when possible."""


WHAT_NOT_TO_SAVE = """## What NOT to save in memory

- Code patterns, conventions, architecture, file paths, or project structure — these can be derived by reading the current project state.
- Git history, recent changes, or who-changed-what — git is authoritative.
- Debugging solutions or fix recipes — the fix is in the code; the commit message has the context.
- Anything already documented in project instruction files.
- Ephemeral task details: in-progress work, temporary state, current conversation context.

These exclusions still apply even when the user explicitly asks you to save something."""


MAIN_AGENT_INSTRUCTIONS = f"""You are a helpful assistant with access to a small file-backed memory system.

Use `MEMORY.md` only as an index for orientation. Relevant topic memories for this turn may already be surfaced below as additional context.

You do not have memory-file tools in the main turn. Use the surfaced memory context directly.

Use surfaced memories when they are relevant or when the user explicitly asks what you remember from earlier context.
Treat saved memory as context, not authority. It may be stale.
If a surfaced memory conflicts with current user-provided information, trust the current information.
Do not invent saved memories.
Do not claim you saved something during this turn; only the extraction agent writes memory in this framework.
When answering from memory, be explicit and concise."""


EXTRACTION_AGENT_INSTRUCTIONS = """You maintain durable memories after a completed assistant turn.

You may only work inside the memory directory via the provided tools. Do not investigate the repo, do not run shell commands, and do not verify facts outside the supplied transcript and existing memory files.

When saving a memory:
1. write or update a topic file first
2. update MEMORY.md with a single-line pointer to that topic file

Never store full memory bodies directly inside MEMORY.md."""


CONSOLIDATION_AGENT_INSTRUCTIONS = """You are performing a memory consolidation pass over the memory directory.

Your goal is to tighten and improve the stored memories, not to invent new context from outside the saved memory files.

When pruning or consolidating:
- merge near-duplicates into one canonical topic file where reasonable
- fix contradictions at the source file
- keep MEMORY.md concise and index-only
- preserve valid relative links to topic files"""


def build_main_memory_instructions(index_snippet: str) -> str:
    cleaned = index_snippet.strip()
    if not cleaned:
        return "Current MEMORY.md index:\n\n(no saved memories yet)"
    return f"Current MEMORY.md index snippet:\n\n{cleaned}"


def build_selected_memories_instructions(selected_memories_text: str) -> str:
    cleaned = selected_memories_text.strip()
    if not cleaned:
        return "Relevant surfaced topic memories for this turn:\n\n(none)"
    return f"Relevant surfaced topic memories for this turn:\n\n{cleaned}"


def build_extract_prompt(
    *,
    turn_transcript: str,
    new_message_count: int,
    existing_memories_manifest: str,
) -> str:
    manifest = (
        existing_memories_manifest.strip()
        if existing_memories_manifest.strip()
        else "(no existing memory files yet)"
    )
    return f"""You are now acting as the memory extraction agent. Analyze the most recent ~{new_message_count} messages below and use them to update the persistent memory files.

Available tools: read, search, list, write, and delete for paths inside the memory directory only.

You MUST only use content from the supplied transcript to update memory. Do not verify against the codebase or git.

If the user explicitly asks you to remember something, save it immediately as whichever type fits best. If they ask you to forget something, find and remove the relevant memory entry.

## Existing memory files

{manifest}

Check this list before writing. Update an existing file rather than creating a duplicate.

{TYPES_SECTION}

{WHAT_NOT_TO_SAVE}

## How to save memories

Saving a memory is a two-step process:

**Step 1** — write the memory to its own file using this frontmatter format:

{TOPIC_FRONTMATTER_EXAMPLE}

**Step 2** — add a pointer to that file in `MEMORY.md`. `MEMORY.md` is an index, not a memory — each entry should be one line, under ~150 characters:

`- [Title](topics/file.md) — one-line hook`

- `MEMORY.md` is always loaded into the main agent context with caps — keep it concise
- Keep the `name`, `description`, and `type` fields up to date with the content
- Organize memory semantically by topic, not chronologically
- Update or remove memories that are wrong or outdated
- Do not duplicate: update an existing file when possible

## Recent conversation transcript

{turn_transcript.strip()}
"""


def build_consolidation_prompt(memory_root: str, *, audit_summary: str) -> str:
    return f"""# Memory Consolidation

You are performing a maintenance pass over the memory files at `{memory_root}`.
Today's date is {date.today().isoformat()}.
This directory already exists. Write directly to it; do not waste steps checking or creating it.

## Phase 1 — Orient

- List the memory directory
- Read `MEMORY.md` to understand the current index
- Skim existing topic files so you improve them rather than creating duplicates

## Phase 2 — Consolidate

For each thing worth remembering:

- merge new signal into existing topic files rather than creating near-duplicates
- convert relative dates to absolute dates
- remove contradicted facts from the source file
- keep the topic file frontmatter accurate and aligned with the content

## Phase 3 — Prune and index

Update `MEMORY.md` so it stays under 200 lines and under ~25KB. It is an index, not a dump — one line per entry under ~150 characters:

`- [Title](topics/file.md) — one-line hook`

- remove pointers to stale, wrong, or superseded memories
- shorten verbose lines; detail belongs in topic files
- add pointers for newly important memories
- resolve contradictions between files

{audit_summary.strip()}

Return a brief summary of what you consolidated, updated, or pruned. If nothing changed, say so."""
