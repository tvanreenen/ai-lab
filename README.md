# AI Lab

A personal lab for developing and testing focused patterns, techniques, and subsystems for agent and harness development.

Some projects are small learning exercises; others are more involved framework experiments. They are grounded in practical agent-system concerns, but built here as personal pattern studies and experiments that others can learn from too.

Most examples live under `src/` as standalone workspace packages. A common way to run one is:

```bash
uv run --package <package-name> python src/<folder>/main.py
```

## Index

### PydanticAI Basics

- [src/pydantic-ai-agent-basic](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-agent-basic): smallest possible `pydantic-ai` agent example.
- [src/pydantic-ai-output-basics](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-output-basics): output patterns and structured response basics.
- [src/pydantic-ai-agent-tools](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-agent-tools): tool-using agent with calculator, search, and weather.

### Human-In-The-Loop

- [src/pydantic-ai-human-approval](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-human-approval): CLI deferred-tool approval (orders and support cases).

### Data Analysis

- [src/pydantic-ai-query-dataset](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-query-dataset): agent that answers questions by running DuckDB SQL over a dataset.

### Research Workflows

- [src/pydantic-ai-deep-researcher](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-deep-researcher): graph-driven iterative web researcher that plans, executes, and adapts across multiple cycles.

### History And Memory

- [src/pydantic-ai-history-summarizer](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-history-summarizer): summarize conversation history for reuse.
- [src/pydantic-ai-history-trimmer](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-history-trimmer): trim history while keeping useful context.
- [src/history-compaction-framework](/Users/tim.vanreenen/Code/ai-lab/src/history-compaction-framework): reusable framework for projected history compaction.
- [src/memory-framework](/Users/tim.vanreenen/Code/ai-lab/src/memory-framework): reusable file-backed topic memory framework.

### Observability

- [src/pydantic-ai-logfire](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-logfire): Logfire instrumentation example for `pydantic-ai`.

### MCP

- [src/hello-world-mcp](/Users/tim.vanreenen/Code/ai-lab/src/hello-world-mcp): minimal MCP server example.

### Embeddings And Audio

- [src/embedding-foundations](/Users/tim.vanreenen/Code/ai-lab/src/embedding-foundations): introductory embedding notebook/package scaffold.
- [src/text-to-speech](/Users/tim.vanreenen/Code/ai-lab/src/text-to-speech): text-to-speech example.

### Applied ML Pipelines

- [src/gb-churn](/Users/tim.vanreenen/Code/ai-lab/src/gb-churn): staged synthetic churn pipeline with SQL-style transformations.
- [src/gb-340b](/Users/tim.vanreenen/Code/ai-lab/src/gb-340b): staged synthetic 340B CE audit prioritization pipeline.

## Deeper Notes

### Human-In-The-Loop

This section is about agent flows where the model can chat and clarify normally, but a human must explicitly approve side-effectful tool execution.

Examples:

- [src/pydantic-ai-human-approval](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-human-approval): CLI deferred-tool approval around order and support-case submission.

Focus:

- a chat-first workflow where the agent gathers missing details naturally
- a hard approval gate only at the tool boundary, not at every reply
- direct review of validated deferred tool args from `DeferredToolRequests`
- resuming the same run with `DeferredToolResults` after `yes`, `revise`, or `cancel`

### Data Analysis

[src/pydantic-ai-query-dataset](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-query-dataset) is less about generic agent basics and more about a specific analysis pattern: let the model translate user questions into SQL over a constrained dataset, then answer from the query results.

Examples:

- [src/pydantic-ai-query-dataset](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-query-dataset): natural-language questions answered through DuckDB SQL over a dataset.

Focus:

- natural-language-to-SQL over a known dataset
- agent-guided analysis without giving the model arbitrary code execution
- a useful bridge between general tool use and more structured analytical workflows

### History And Memory

These examples are about managing long-running context, but they do it at different layers: trimming the live conversation, compacting it more systematically, or storing reusable memory outside the immediate transcript.

Examples:

- [src/pydantic-ai-history-summarizer](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-history-summarizer): replace raw prior turns with a compact summary.
- [src/pydantic-ai-history-trimmer](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-history-trimmer): keep recent or important turns while pruning lower-value history.
- [src/history-compaction-framework](/Users/tim.vanreenen/Code/ai-lab/src/history-compaction-framework): reusable framework for projected history compaction.
- [src/memory-framework](/Users/tim.vanreenen/Code/ai-lab/src/memory-framework): file-backed persistent memory outside the live conversation history.

Focus:

- summarize or trim when the problem is mostly token pressure
- use a compaction framework when you want that behavior to be reusable and policy-driven
- use persistent memory when the problem is cross-session recall, not just context window size

### Applied ML Pipelines

These examples are less about agents and more about structured ML workflows with staged, inspectable transformations over tabular data.

Examples:

- [src/gb-churn](/Users/tim.vanreenen/Code/ai-lab/src/gb-churn): staged churn prediction pipeline for a classical tabular business problem.
- [src/gb-340b](/Users/tim.vanreenen/Code/ai-lab/src/gb-340b): staged prioritization pipeline for a synthetic healthcare/compliance-style problem.

Focus:

- examples of non-agent AI work that is still highly practical
- pipelines where SQL-style transformation thinking is part of the design
- a contrast with the `pydantic-ai` examples, which are focused on agent/runtime patterns rather than classical model pipelines
