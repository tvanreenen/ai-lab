# Pydantic AI History Compaction Framework

## TL;DR

- This is a standalone, runnable demonstration of projected-history compaction for agents built with PydanticAI.
- It focuses on one subsystem: keeping long-running conversations inside a context budget without rewriting canonical history.
- The pattern matters when an agent needs durable conversational continuity but the provider-facing request must stay compact.
- Run it from the package directory with `uv run --env-file .env python -m history_compaction_framework`.

## What This Demonstrates

This example is a standalone runnable demonstration of an agent-context management subsystem inside a larger harness design.

It is meant to teach the pattern, not just expose a package API:

- canonical history stays raw and append-only
- projected history is the provider-facing view
- staging is prepared asynchronously in the background
- commit and recovery are driven by request-budget pressure
- the main conversation loop can stay within a context window without mutating source history

## Why This Pattern Exists

Long-running agents accumulate more context than a provider request can safely carry. A common failure mode is to treat compaction as in-place transcript rewriting, which makes debugging and recovery harder because the system loses its source record.

This example demonstrates a different approach:

- raw history remains the source of truth
- compaction only changes the projected request view
- background work prepares summaries before they are needed
- request-time recovery can commit or stage more history when pressure gets too high

That separation makes the system easier to inspect, reason about, and adapt to different storage backends later.

## How It Works

The demo stores two things under `state/`:

```text
state/
  history.jsonl
  collapse_state.json
```

`history.jsonl` is the canonical append-only turn log. `collapse_state.json` stores committed spans, staged spans, health counters, and token-calibration metadata.

At runtime, the compaction flow is:

1. Load raw turns and collapse state.
2. Build a projected provider-facing history from raw turns plus committed spans.
3. Budget the next request against that projected view plus the pending user message.
4. If pressure is high enough, commit already-staged spans or perform bounded synchronous recovery.
5. After the main turn completes, append the raw turn to canonical history and queue background staging work.

The important behaviors in this demo are:

- raw history is never rewritten after compaction
- staged spans stay out of band until committed
- committed spans replace whole-turn ranges in the projected view
- staging is asynchronous, but recovery is bounded and request-driven
- local preflight only fails when the estimated request stays beyond the configured fail threshold

The interactive REPL includes a few observability commands so the pattern is easy to inspect while running:

- `/raw` shows canonical history
- `/projected` shows the current provider-facing projection
- `/staged` shows staged spans waiting to be committed
- `/committed` shows committed spans already applied
- `/state` shows thresholds, estimates, and health counters
- `/clear` wipes both raw history and collapse state

## Run It

From the package directory:

```bash
uv sync
uv run --env-file .env python -m history_compaction_framework
```

Set `OPENAI_API_KEY` in your shell or `.env` before running.

Useful flags:

```bash
uv run --env-file .env python -m history_compaction_framework --state-root /tmp/history-compaction-demo
uv run --env-file .env python -m history_compaction_framework --model openai:gpt-5.2 --summary-model openai:gpt-5.2
uv run --env-file .env python -m history_compaction_framework --context-window 4000
uv run --env-file .env python -m history_compaction_framework --context-window 32000
```

The demo defaults to a smaller `context_window` of `4000` so staging and commit behavior are easier to trigger manually. The library default remains `32000` unless you pass your own `CompactionConfig`.

## Public Surface

The main reusable entry points are:

- `HistoryCompactionManager` for raw-history storage, projection, budgeting, and turn recording
- `CompactedSession` for a batteries-included runnable loop
- `build_history_processor()` when you want the manager to project raw history into provider-facing request history

One valid integration path is the history-processor path:

```python
from pathlib import Path

from pydantic_ai import Agent

from history_compaction_framework import HistoryCompactionManager

manager = HistoryCompactionManager(Path("./state"))
agent = Agent(
    "openai:gpt-5.2",
    instructions="Be a helpful assistant.",
    history_processors=[manager.build_history_processor()],
)

raw_history = manager.raw_message_history()
result = agent.run_sync("Continue the conversation", message_history=raw_history)
manager.record_turn("Continue the conversation", result.new_messages())
```

## Design Notes

The threshold values in this example are design choices for the demonstration, not fixed doctrine:

- pressure threshold: 80% of the configured context window
- stage threshold: 88%
- target threshold: 90%
- guard threshold: 95%
- fail threshold: 105%

The first completed turn stays raw so the projected history continues to include the original instructions-bearing request when later runs reuse message history.

Compaction operates on whole turns rather than arbitrary message indices. That avoids splitting tool-request and tool-response pairs across a synthetic summary boundary.

Request budgeting uses local `tiktoken` estimates, then calibrates future estimates against actual provider-reported token usage recorded after completed turns.

## Reference Implementation Note

This is a runnable reference implementation of the pattern. It is designed to be studied, adapted, and extended rather than treated as a production-ready drop-in.
