import os
from typing import Annotated, Optional, Literal

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from dotenv import load_dotenv
import asyncio
import numexpr

logfire.configure(
    token=os.getenv("LOGFIRE_WRITE_TOKEN"),
    send_to_logfire='if-token-present',
    service_name=os.path.basename(__file__)
)
logfire.instrument_pydantic_ai()


load_dotenv()

async def calculator(
    _ctx: RunContext,
    expressions: Annotated[
        list[str],
        Field(
            description="A single-line mathematical expression to evaluate. Supports arithmetic operators (+, -, *, /, **, %), mathematical functions (sin, cos, tan, log, exp, sqrt, abs, floor, ceil), and complex expressions.",
        ),
    ],
) -> str:
    """Use this tool for all mathematical calculations instead of attempting to calculate yourself."""
    try:
        results = []
        for i, expression in enumerate(expressions, 1):
            try:
                result = numexpr.evaluate(
                    expression.strip(),
                    global_dict={},  # restrict access to globals
                )
                results.append(f"Expression {i}: {expression} = {result}")
            except Exception as e:
                results.append(f"Expression {i}: {expression} = Error: {str(e)}")

        return "\n".join(results)
    except Exception as e:
        return str(e)

class NextStep(BaseModel):
    done: Annotated[bool, Field(description="Whether or now you full completed the user's request. Try again if not.")]
    reason: str
    action: Optional[Literal["duckduckgo_search_tool", "calculator", "none"]] = "none"
    action_args: Optional[dict] = None
    partial_answer: Optional[str] = None

agent = Agent(
    'openai:gpt-4o',
    instructions=(
            "You are in an iterative loop. Consider the most recent tool result before deciding the next step. "
            "Prefer concrete actions. Only set done=True when the request is fully satisfied."
    ),
    tools=[calculator, duckduckgo_search_tool()],
    output_type=NextStep,
)

async def main():
    message_history = []
    await agent.to_cli(message_history=message_history)

if __name__ == "__main__":
    asyncio.run(main())
