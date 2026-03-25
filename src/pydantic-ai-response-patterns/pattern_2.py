"""Tool ``calculator`` returns structured data plus extra guidance for how the model should answer."""

import asyncio

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from _common import calculate_expression

load_dotenv()


class CalculatorResponse(BaseModel):
    result: str
    supervisor_instructions: str


def calculator(ctx: RunContext[None], expression: str) -> CalculatorResponse:
    """Evaluate an expression; return the value and instructions for how to present it."""
    return CalculatorResponse(
        result=calculate_expression(expression),
        supervisor_instructions="Present the result in an overly scientifically verbose way.",
    )


agent = Agent(
    "openai:gpt-5.4",
    tools=[calculator],
    instructions=(
        "You are a helpful assistant. The calculator tool returns structured fields including "
        "`supervisor_instructions`—follow those instructions when you explain the result."
    ),
)


async def main() -> None:
    await agent.to_cli()


if __name__ == "__main__":
    asyncio.run(main())
