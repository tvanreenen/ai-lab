# pydantic-ai Deep Researcher

This package demonstrates a graph-driven research loop built with `pydantic-ai` and `pydantic-graph`.

The agent works in cycles:

1. Propose a flexible research plan.
2. Execute one meaningful step at a time.
3. Adapt the plan when new information changes the approach.
4. Stop when the answer is complete or the cycle budget is exhausted.

It uses:

- a structured `AgentResponse` output model for each run
- DuckDuckGo search as the external research tool
- a small graph with `AgentRun` and `Decide` nodes
- Rich panels to show per-cycle progress in the terminal

Run it with:

```bash
uv run --package pydantic-ai-deep-researcher python src/pydantic-ai-deep-researcher/main.py "Compare the best lightweight Python workflow engines for agent orchestration"
```

Environment:

- `OPENAI_API_KEY` is required.
- `DEEP_RESEARCHER_MODEL` is optional and defaults to `openai:gpt-5.4`.

Useful flags:

- `--model openai:gpt-5.4`
- `--budget 10`

Manual smoke scenarios:

- Ask for a topic that needs web research and confirm the agent creates an initial plan before iterating.
- Confirm completed plan items remain visible as the plan adapts.
- Use a small budget like `--budget 2` and confirm the final answer notes the budget limit.
- Ask for a topic with changing information and confirm the agent uses the search tool instead of answering from prior knowledge alone.
