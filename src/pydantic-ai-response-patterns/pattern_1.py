"""Tool ``calculator`` returns a plain string; the model relays that raw result."""

import asyncio

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from _common import calculate_expression

load_dotenv()


def calculator(ctx: RunContext[None], expression: str) -> str:
    """Evaluate an expression and return the result as a plain string."""
    return calculate_expression(expression)


agent = Agent(
    "openai:gpt-5.4",
    tools=[calculator],
    instructions=(
        "You are a helpful assistant. You have one calculator tool; it returns a plain string "
        "result—share that result clearly with the user."
    ),
)


async def main() -> None:
    await agent.to_cli()


if __name__ == "__main__":
    asyncio.run(main())
