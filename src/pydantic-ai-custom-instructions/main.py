import asyncio
import re
from datetime import date

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

load_dotenv()

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

agent = Agent(
    "openai:gpt-5-nano",
    deps_type=str,
    instructions="Be friendly and helpful.",
)

@agent.instructions
def add_the_users_name(ctx: RunContext[str]) -> str:
    return f"The user's name is {ctx.deps}."


@agent.instructions
def add_the_date() -> str:
    return f"The date is {date.today()}."


async def main():
    """Main entry point for the application."""
    username = "Frank"
    message_history = []

    result = await agent.run("What is my name?", deps=username, message_history=message_history)
    message_history = result.all_messages()

    result = await agent.run("What is the date?", deps=username, message_history=message_history)
    message_history = result.all_messages()

    for i, m in enumerate(message_history, start=1):
        r = re.sub(r'((?:TextPart|UserPromptPart)\([^)]*?content=)([\'"])(.*?)\2', rf"\1\2{GREEN}\3{RESET}\2", repr(m), flags=re.DOTALL)
        print(f"{BLUE}[{i}]{RESET} {r}\n")


if __name__ == "__main__":
    asyncio.run(main())
