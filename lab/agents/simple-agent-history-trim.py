from pydantic_ai import Agent
from dotenv import load_dotenv
import asyncio
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
import logfire
import os
import uuid

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

load_dotenv()

async def keep_12_most_recent_messages(messages: list[ModelMessage]) -> list[ModelMessage]:
    """
    Keep only the 12 most recent messages (10 because this runs before last round gets appended). For most purposes, I've found this method to be sufficient.
    """
    if len(messages) > 10:
        return messages[-10:]
    return messages

agent = Agent(
    'openai:gpt-4o',
    instructions='You are a simple conversational agent with a set of tools.',
    history_processors=[keep_12_most_recent_messages]
)

async def main():
    print(f"Simple Conversational CLI Agent with History Processors (type 'quit' or 'q' to stop)")
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
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"), send_to_logfire='if-token-present')
    logfire.instrument_pydantic_ai()
    with logfire.span(os.path.basename(__file__), attributes={"session_id": str(uuid.uuid4())}):
        asyncio.run(main()) 