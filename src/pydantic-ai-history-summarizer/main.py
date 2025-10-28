import os
import asyncio
from textwrap import dedent

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ToolReturnPart
import logfire
import uuid

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

load_dotenv()

memory_consolidator = Agent(
    'openai:gpt-4.1',
    instructions=dedent("""
        ## Role  
        You are a memory consolidator.  

        ## Objective  
        Convert short-term conversation segments into a concise long-term memory record.

        ## Input  
        You will receive part of a conversation between a user and an AI agent, possibly including a summary of earlier exchanges.  

        ## Instructions  
        1. Identify essential facts the AI should remember for future conversations.
        2. Summarize exchanges by topic/task/theme, not turn-by-turn.
        3. Start a new numbered topic when the subject, task, or goal changes.
        4. Refer to the AI as "you" and the other party as "the user."
        5. Keep it concise but capture all important details.

        When generating the output, follow this exact Markdown format:

        ```markdown
        # Consolidated Memories from Conversation

        ## Essential Facts to Remember
        - ...

        ## Summary of Topics Discussed or Tasks Performed
        1. [Topic/Task Name]  
            - Main goal: ...  
            - Key information, insights, actions, decisions: ...
        ```
        Output should be plain Markdown without wrapping it in a code block.
    """),
)

async def consolidate_memory(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Let the oldest memories get fuzzier and fuzzier as the resummarization gets more general."""
    consolidation_threshold = 16
    number_of_messages_in_history = len(messages)
    number_of_messages_to_summarize = int(consolidation_threshold / 2)
    number_of_messages_to_keep = number_of_messages_in_history - number_of_messages_to_summarize
    index_of_last_message_to_keep = number_of_messages_in_history - number_of_messages_to_keep
    
    if number_of_messages_in_history <= consolidation_threshold:
        return messages
    
    if (any(isinstance(part, ToolReturnPart) for part in messages[index_of_last_message_to_keep].parts)):
        return messages
    
    result = await memory_consolidator.run(message_history=messages[:number_of_messages_to_summarize])
    return result.new_messages() + messages[-number_of_messages_to_keep:]

agent = Agent(
    'openai:gpt-4.1',
    instructions='You are a simple conversational agent with access to tools.',
    history_processors=[consolidate_memory],
)

async def main():
    print(f"Simple Conversational CLI Agent with History Processors (type 'quit' or 'q' to stop)")
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
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"), send_to_logfire='if-token-present')
    logfire.instrument_pydantic_ai()
    with logfire.span(os.path.basename(os.path.dirname(__file__)), attributes={"session_id": str(uuid.uuid4())}):
        asyncio.run(main()) 