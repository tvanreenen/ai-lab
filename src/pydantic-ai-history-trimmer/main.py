import asyncio
import math
import os
import uuid
from datetime import UTC, datetime

import logfire
import numexpr
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ToolReturnPart

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

load_dotenv()

async def message_at_index_contains_tool_return_parts(messages: list[ModelMessage], index: int) -> bool:
    """Check if the message at index in message history contains ToolReturnParts."""
    return any(isinstance(part, ToolReturnPart) for part in messages[index].parts)

async def keep_recent_messages(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Take in the full message history and trim down to only the most recent messages."""
    number_of_messages = len(messages)
    number_of_messages_to_keep = 5
    if number_of_messages <= number_of_messages_to_keep:
        return messages
    if (await message_at_index_contains_tool_return_parts(messages, number_of_messages - number_of_messages_to_keep)):
        return messages
    return messages[-number_of_messages_to_keep:]

agent = Agent(
    "openai:gpt-4o",
    instructions="You are a simple conversational agent with a set of tools.",
    history_processors=[keep_recent_messages],
)

@agent.tool
def calculator(ctx: RunContext[None], expression: str) -> str:
    """A calculator tool for both the user and LLM to calculate single line mathematical expressions."""
    try:
        result = numexpr.evaluate(
            expression.strip(),
            global_dict={},  # restrict access to globals
            local_dict={"pi": math.pi, "e": math.e},
        )
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"

@agent.tool
def check_datetime(ctx: RunContext[None]) -> str:
    """Check the current UTC date and time."""
    return datetime.now(UTC).isoformat()

async def main():
    full_message_history = []
    while True:
        user_input = input(f"{BLUE}You:{RESET} ").strip()
        if user_input.lower() in {"quit", "q"}:
            print("Goodbye!")
            break
        async with agent.run_stream(user_input, message_history=full_message_history) as result:
            print(f"{GREEN}Agent:{RESET} ", end="", flush=True)
            async for chunk in result.stream_text(delta=True):
                print(chunk, end="", flush=True)
            print("")
            full_message_history = result.all_messages()

if __name__ == "__main__":
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"), send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
    with logfire.span(os.path.basename(os.path.dirname(__file__)), attributes={"session_id": str(uuid.uuid4())}):
        asyncio.run(main())
