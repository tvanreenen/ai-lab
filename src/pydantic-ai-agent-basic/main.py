import asyncio

from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

agent = Agent(
    "openai:gpt-5.4",
    instructions="You are a simple conversational agent with nothing more than your foundational knowledge.",
)


async def main() -> None:
    await agent.to_cli()


if __name__ == "__main__":
    asyncio.run(main())
