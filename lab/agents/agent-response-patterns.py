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
from pydantic import BaseModel

BLUE = "\033[94m"
GREEN = "\033[92m"
RESET = "\033[0m"

load_dotenv()

def calculate_expression(expression: str) -> str:
    """Calculate the result of a mathematical expression."""
    try:
        result = numexpr.evaluate(
            expression.strip(),
            global_dict={},  # restrict access to globals
            local_dict={"pi": math.pi, "e": math.e},
        )
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"
    
# Pattern 1: Responds to supervisor with raw response

def calculator_pattern_1(ctx: RunContext[None], expression: str) -> str:
    """Calculator. Call this if the user specifically asks to use pattern 1."""
    return calculate_expression(expression)

# Pattern 2: Responds to supervisor with raw response and instruction on how to respond to user

class Pattern2Response(BaseModel):
    result: str
    supervisor_instructions: str

def calculator_pattern_2(ctx: RunContext[None], expression: str) -> str:
    """Calculator. Call this if the user specifically asks to use pattern 2."""
    response = Pattern2Response(
        result=calculate_expression(expression),
        supervisor_instructions="Present the result in an overly scientificly verbose way."
    )
    return response

# Pattern 3: Self-responds with raw response from function

def calculator_pattern_3(ctx: RunContext[None], expression: str) -> str:
    """Calculator. Call this if the user specifically asks to use pattern 3."""
    print(calculate_expression(expression), end='', flush=True)

# Pattern 4: Self-responds with response from sub-agent

pattern4_agent = Agent(
    'openai:gpt-4o',
    instructions='You are a playful math explainer. When given a calculation, respond with a fun fact or joke about the result, then show the answer.'
)

async def calculator_pattern_4(ctx: RunContext[None], expression: str) -> str:
    """Calculator. Call this if the user specifically asks to use pattern 4."""
    async with pattern4_agent.run_stream(expression) as result:
        async for chunk in result.stream_text(delta=True):
            print(chunk, end='', flush=True)

supervisor = Agent(
    'openai:gpt-4o',
    instructions='''You are a conversational agent that can use tools to fulfill user requests.''',
    tools=[calculator_pattern_1, calculator_pattern_2],
    output_type=[str, calculator_pattern_3, calculator_pattern_4]
)

async def main():
    print(f"Enter a mathematical expression to calculate and a pattern to use (type 'quit' or 'q' to stop)")
    print("Type 'quit' or 'q' to stop\n")
    
    message_history = []
    while True:
        user_input = input(f"{BLUE}You:{RESET} ").strip()
        if user_input.lower() in {"quit", "q"}:
            print("Goodbye!")
            break
            
        async with supervisor.iter(user_input, message_history=message_history) as run:
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