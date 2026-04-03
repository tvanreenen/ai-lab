# History Compaction Framework TODO

This document tracks follow-up ideas, optimizations, and design questions for the `history-compaction-framework` example.

Use it as a durable backlog for improvements that are worth preserving but not yet implemented. Keep entries concise, implementation-oriented, and easy to scan.

## How to use this file

- Add one section per idea.
- Start with the user-visible or system-level motivation.
- Capture the likely implementation direction, not just the symptom.
- Note risks, tradeoffs, or open questions if they matter.
- Leave completed items here only if the historical note is still useful; otherwise remove them.

## Backlog

### Risk-aware commit prioritization

**Status:** proposed

**Motivation:** The current system stages and commits oldest-first spans without using `risk` to guide which spans are safest to collapse first. That keeps the behavior simple, but it can commit a span that is technically older while a lower-risk candidate exists nearby.

**Potential direction:** Introduce commit prioritization that still respects the broad oldest-first policy but uses risk to choose among eligible staged spans in the same age band. Examples:

- prefer lower-risk staged spans when multiple candidates would recover enough headroom
- deprioritize high-risk spans for automatic commit
- optionally require a stronger budget reason before committing a high-risk span

**Why this is interesting:** This is one of the cleanest ways to improve compaction quality without abandoning the projected-collapse design or adding a heavy fallback path.

### Supplement model risk with heuristic risk

**Status:** proposed

**Motivation:** `risk` is currently whatever the summarizer model returns. That is useful as qualitative metadata, but it is not grounded by any deterministic signals from the transcript itself.

**Potential direction:** Combine the LLM-provided risk score with a local heuristic score derived from span features such as:

- unresolved or conditional language
- dense tool usage or multiple tool results
- recent decisions, constraints, or TODO-like language
- unusually high code, JSON, or stack-trace density
- turns that look like planning, debugging, or ambiguity resolution rather than settled context

**Possible model:** `final_risk = weighted_llm_risk + weighted_heuristic_risk`, with bounded output in `0.0..1.0`.

**Why this is interesting:** It would make risk more stable across model drift, improve explainability, and make later risk-aware commit selection easier to trust.

### Make risk operational, not just diagnostic

**Status:** proposed

**Motivation:** Risk is currently stored and displayed, but it does not affect staging or commit behavior.

**Potential direction:** Once risk is more trustworthy, use it in at least one concrete decision:

- commit lower-risk spans first
- skip auto-commit above a configured risk threshold
- use different summary compression targets for low-risk vs high-risk spans

**Why this is interesting:** It turns risk from an observation into an actual quality-control mechanism.

### Add summary-of-summaries as a second-tier fallback

**Status:** proposed

**Motivation:** Progressive collapse preserves structure well, but it does not remove context growth forever. Over very long sessions, the system can reach a point where most eligible raw turns have already been collapsed, the preserved recent tail is still protected, and the accumulated collapsed placeholders themselves become a large part of the remaining budget.

**Potential direction:** Add a second-tier fallback that operates only after normal staged span commit recovery is exhausted:

- identify older committed spans that are far enough behind the recent working set
- merge them into a denser higher-level summary
- replace multiple committed placeholders with one new committed placeholder
- keep this path explicitly separate from the normal first-tier collapse flow

**Design intent:** This should be a deeper recovery layer for long-lived conversations, not the default compaction strategy. The primary flow should still prefer raw turns first, then ordinary staged collapse, and only fall back to summary-of-summaries when the session is approaching a true summary floor.

**Why this is interesting:** It is the most natural long-term extension of the projected-collapse design because it preserves the same mental model while acknowledging that even collapsed summaries eventually accumulate enough overhead to require another level of compaction.
