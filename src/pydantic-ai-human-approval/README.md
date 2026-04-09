# pydantic-ai Human Approval

This package demonstrates a more production-like human approval loop built on top of `pydantic-ai` deferred tools.

For simplicity, the demo assumes customer/account identity is already known outside the agent, so the approval payloads focus only on the actionable order or support fields.

It uses:

- one general responder agent
- two approval-required business tools
  - `submit_order(...)`
  - `submit_support_case(...)`
- direct review of validated deferred tool-call arguments

The flow is:

1. Talk naturally with the agent.
2. The agent either answers normally, asks follow-up questions, or decides to call `submit_order` or `submit_support_case`.
3. When the runtime returns `DeferredToolRequests`, inspect the validated tool name and arguments.
4. Choose `yes`, `revise`, or `cancel` at the final tool boundary.

Run it with:

```bash
uv run --package pydantic-ai-human-approval python src/pydantic-ai-human-approval/main.py
```

Environment:

- `OPENAI_API_KEY` is required.
- `APPROVAL_WORKFLOW_MODEL` is optional and defaults to `openai:gpt-5.4`.

Manual smoke scenarios:

- Ask to place an order, confirm the agent asks follow-up questions if needed, then choose `yes` at the final order gate.
- Ask to open a support case, confirm the agent gathers enough detail, then choose `cancel` at the final approval gate.
- Trigger an order or support case, choose `revise`, provide extra information, and confirm the agent continues the conversation or produces a revised tool call.
- Ask a normal informational question and confirm no tool approval flow appears.
- Confirm the approval UI shows the tool name and validated payload for whichever tool is pending.
- Confirm the fake local backend only stores approved orders or support cases.

How to scaffold this into a real app:

- Keep one general responder agent that can answer, clarify, or act.
- Define approval-required tools for the business actions that matter.
- Let humans review the actual validated deferred tool arguments.
- Resume the agent with `DeferredToolResults` after `yes`, `cancel`, or reviewer-requested revision.

Reusability check:

- The generic chat and approval loop lives in [cli_workflow.py](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-human-approval/cli_workflow.py).
- The scenario wiring and agent setup live in [agent.py](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-human-approval/agent.py).
- The order models and fake backend live in [order.py](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-human-approval/tools/order.py).
- The support-case models and fake backend live in [support_case.py](/Users/tim.vanreenen/Code/ai-lab/src/pydantic-ai-human-approval/tools/support_case.py).
- The human reviews raw deferred tool args rather than a separate proposal object.
- The same pattern can be extended by adding more approval-required tools to the same general responder agent.
