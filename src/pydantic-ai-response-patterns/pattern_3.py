"""Tool ``calculator`` calls a nested sub-agent with ``run()`` and returns its reply as the tool result.

The outer model stays in the normal tool loop: one tool call runs the sub-agent, then conversation
can continue using that return value.
"""

import asyncio

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

load_dotenv()

math_explainer = Agent(
    "openai:gpt-5.4",
    instructions=(
        "You are a playful math explainer. When given a calculation, respond with a fun fact or "
        "joke about the result, then show the answer."
    ),
)


async def calculator(_ctx: RunContext[None], expression: str) -> str:
    """Hand off the expression to a sub-agent; return its answer as this tool's result."""
    result = await math_explainer.run(f"Calculate and explain playfully: {expression}")
    out = result.output
    return out if isinstance(out, str) else str(out)


agent = Agent(
    "openai:gpt-5.4",
    tools=[calculator],
    instructions=(
        "You are a helpful assistant. You have a calculator tool that uses a dedicated math "
        "explainer behind the scenes—call it when the user wants a worked or playful explanation."
    ),
)


async def main() -> None:
    await agent.to_cli()


if __name__ == "__main__":
    asyncio.run(main())
