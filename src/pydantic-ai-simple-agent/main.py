from pydantic_ai import Agent
from dotenv import load_dotenv
import asyncio

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

load_dotenv()

agent = Agent(
    'openai:gpt-4o',
    instructions='You are a simple conversational agent with a set of tools.'
)

async def main():
    print(f"Simple Conversational CLI Agent with Tools (type 'quit' or 'q' to stop)")
    message_history = []
    while True:
        user_input = input(f"{BLUE}You:{RESET} ").strip()
        if user_input.lower() in {"quit", "q"}:
            print("Goodbye!")
            break
        async with agent.run_stream(user_input, message_history=message_history) as result:
            print(f"{GREEN}Agent:{RESET} ", end="", flush=True)
            async for chunk in result.stream_text(delta=True):
                print(chunk, end="", flush=True)
            print("")
            message_history = result.all_messages()

if __name__ == "__main__":
    asyncio.run(main())
