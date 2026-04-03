# Pydantic AI Memory Framework

## TL;DR

- This is a standalone, runnable demonstration of a durable memory subsystem for agents built with PydanticAI.
- It focuses on one subsystem: separating recall, post-turn memory writes, and maintenance from the main conversation turn.
- The pattern matters when an agent needs durable memory without giving the main turn direct write access to the memory store.
- Run it from the package directory with `uv run --env-file .env python -m memory_framework.cli`.

## What This Demonstrates

This example is a standalone runnable demonstration of a memory subsystem inside a larger agent or harness design.

It is meant to teach the pattern, not just the package surface:

- `MEMORY.md` acts as a compact index, not the memory store itself
- durable memories live in topic files with lightweight metadata
- recall is selective and query-driven
- memory writes happen after the main turn through extraction
- cleanup and consolidation are separate maintenance work

## Why This Pattern Exists

A common agent-memory failure mode is to mix everything together: the main turn reads and writes the same memory store, the index grows without bound, and every saved fact gets injected back into the model whether it is relevant or not.

This example demonstrates a more controlled pattern:

- keep a compact index for orientation
- keep durable memory bodies in separate topic files
- surface only selected memories into the main turn
- handle writes after the turn completes
- treat consolidation as maintenance work instead of main-turn logic

That separation keeps the main turn narrower, makes the memory store easier to audit, and gives the memory subsystem room to evolve independently.

## How It Works

On first run, the demo creates:

```text
memory/
  MEMORY.md
  topics/
```

`MEMORY.md` is index-only. Each entry is a single-line pointer to a topic file. Durable memory bodies live in `memory/topics/*.md` with frontmatter describing the memory:

- `name`
- `description`
- `type` in `user | feedback | project | reference`

The runtime flow is:

1. Read and cap the `MEMORY.md` index.
2. Scan memory headers and select only the memories relevant to the current query.
3. Surface the selected topic bodies into the main turn.
4. Run the main agent without memory-file write tools.
5. After the turn completes, run extraction in the background to create, update, or remove topic files and index pointers.
6. Apply index hygiene and schedule best-effort consolidation when activity and timing thresholds justify it.

The important behaviors in this demo are:

- the main turn consumes surfaced memory, not write tools
- the index stays compact because it is not used as the memory body store
- extraction and consolidation are distinct agents with different responsibilities
- maintenance state lives inside the memory root but is reserved for the framework itself

Manual consolidation is still available, but it is mainly a debugging and inspection affordance rather than the normal operating path.

## Run It

From the package directory:

```bash
uv sync
uv run --env-file .env python -m memory_framework.cli
```

Set `OPENAI_API_KEY` in your shell or `.env` before running.

Useful flags:

```bash
uv run --env-file .env python -m memory_framework.cli --memory-root /tmp/framework-memory
uv run --env-file .env python -m memory_framework.cli --model openai:gpt-5.2
uv run --env-file .env python -m memory_framework.cli --consolidate
```

To see the write path in action, tell the assistant something durable that should be remembered or explicitly ask it to remember or forget something. A generic throwaway turn may legitimately produce no new memory files.

## Public Surface

The main reusable entry points are:

- `MemoryDeps` for wiring memory context into agents
- `scan_memory_headers(...)`, `select_relevant_memories(...)`, and `surface_selected_memories(...)` for recall
- `build_main_agent(...)`, `build_extract_agent(...)`, and `build_consolidate_agent(...)` for the three runtime roles

These pieces are enough to embed the memory pattern into another harness without turning the README into package-reference documentation.

## Design Notes

The key design choice in this example is the split between a compact index and separate topic files. The index is optimized for orientation and selection, while the topic files hold the durable content that can grow, merge, or be rewritten over time.

Recall is selective rather than exhaustive. The main turn receives a capped index plus only the topic bodies selected for the current query.

Extraction and consolidation are best-effort background work. This demo demonstrates the subsystem boundaries and maintenance flow, but it does not promise that every turn will create a new memory or that recall will always choose the ideal topic set.

The framework also normalizes malformed or duplicate index lines after writes so the store stays legible as the example evolves.

## Reference Implementation Note

This is a runnable reference implementation of the pattern. It is designed to be studied, adapted, and extended rather than treated as a production-ready drop-in.
