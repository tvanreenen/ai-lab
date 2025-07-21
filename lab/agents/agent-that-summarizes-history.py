from dataclasses import dataclass
from typing import List

from pydantic_ai import Agent, RunContext
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

@dataclass
class AgentContext:
    message_history: List[ModelMessage]

agent = Agent(
    'openai:gpt-4.1',
    instructions='You are a simple conversational agent with access to tools.',
    deps_type=AgentContext
)

@agent.tool
def clear_conversation_history(ctx: RunContext[AgentContext]) -> str:
    """Clear the conversation history and start fresh."""
    ctx.deps.message_history.clear()
    return "Conversation history has been cleared."

memory_consolidator_instructions = """
# Role
- You are a memory consolidator.
# Objective
- Consolidate a list of short term memories into a long term memory.
# Input
- You will be given a segment of a conversation thread between a user and an AI agent. Note that the segment may also include a summary of previous exchanges.
# Output
- Identify and list the essential facts, user preferences, goals, or constraints that you must remember and carry forward as the conversation continues.
- Provide a chronolocial summary of each exchange incorporating both the recent exchanges with any summarary of previous exchanges. Summarize both the the user's request and the response provide by the AI agent.
Refer to the agent as "you" and the user as "the user".
"""

memory_consolidator = Agent(
    'openai:gpt-4.1',
    instructions=memory_consolidator_instructions,
)

async def consolidate_memory(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Let the oldest memories get fuzzier and fuzzier as the resummarization gets more general."""
    if len(messages) > 16:
        oldest_messages = messages[:8]
        summary = await memory_consolidator.run(message_history=oldest_messages)
        return summary.new_messages() + messages[-8:]

    return messages

async def main():
    print(f"Simple Conversational CLI Agent with History Processors (type 'quit' or 'q' to stop)")
    message_history = []
    while True:
        user_input = input(f"{BLUE}You:{RESET} ").strip()
        if user_input.lower() in {"quit", "q"}:
            print("Goodbye!")
            break    
        
        agent_context = AgentContext(message_history=message_history)
        async with agent.run_stream(user_input, message_history=message_history, deps=agent_context) as result:
            print(f"{GREEN}Agent:{RESET} ", end="", flush=True)
            async for chunk in result.stream_text(delta=True):
                print(chunk, end="", flush=True)
            print("")
            message_history = await consolidate_memory(result.all_messages())

if __name__ == "__main__":
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"), send_to_logfire='if-token-present')
    logfire.instrument_pydantic_ai()
    with logfire.span(os.path.basename(__file__), attributes={"session_id": str(uuid.uuid4())}):
        asyncio.run(main()) 