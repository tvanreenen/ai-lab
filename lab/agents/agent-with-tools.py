from pydantic_ai import Agent, RunContext
from dotenv import load_dotenv
import asyncio
import numexpr
import math
from datetime import datetime
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallPartDelta,
    FinalResultEvent,
)

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

load_dotenv()

agent = Agent(
    'openai:gpt-4o',
    instructions='You are a simple conversational agent with access to a calculator and the current timestamp.'
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
def current_timestamp(ctx: RunContext[None]) -> str:
    """Returns the current date and time as an ISO 8601 string."""
    return datetime.now().isoformat()

async def main():
    print(f"Simple Conversational CLI Agent with Tools (type 'quit' or 'q' to stop)")
    message_history = []
    while True:
        user_input = input(f"{BLUE}You:{RESET} ").strip()
        if user_input.lower() in {"quit", "q"}:
            print("Goodbye!")
            break
        async with agent.iter(user_input, message_history=message_history) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as request_stream:
                        async for event in request_stream:
                            if isinstance(event, PartStartEvent):
                                print(f"{GREEN}Agent:{RESET} ", end='', flush=True)
                            if isinstance(event, PartDeltaEvent):
                                if isinstance(event.delta, TextPartDelta):
                                    print(event.delta.content_delta, end='', flush=True)
                elif Agent.is_call_tools_node(node):
                    async with node.stream(run.ctx) as tool_stream:
                        async for event in tool_stream:
                            if isinstance(event, FunctionToolCallEvent):
                                print(f"Calling tool {event.part.tool_name}...")
            print("")
            message_history = run.result.all_messages()

if __name__ == "__main__":
    asyncio.run(main()) 