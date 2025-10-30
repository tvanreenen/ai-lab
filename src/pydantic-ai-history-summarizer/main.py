import asyncio
import os
from textwrap import dedent

import logfire
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel

load_dotenv()

# Constants
TOKEN_LIMIT = 5000  # Trigger consolidation when this many tokens are reached
BLUE = "\033[94m"
RESET = "\033[0m"

class DiscussionSubject(BaseModel):
    """A subject or theme that was discussed in the conversation."""
    subject: str = Field(description="Name or title of the subject/topic that was discussed")
    summary: str = Field(
        description=(
            "Detailed, compact summary of how this subject was discussed: key definitions, steps, examples, "
            "decisions, constraints, caveats, and outcomes. Capture granular points without conversational filler."
        ),
    )

class ConversationMemory(BaseModel):
    """Consolidated memory of conversations with the user."""
    user_context: list[str] = Field(description="Personal/professional context about the user (role, background, preferences, needs, motivations, constraints)")
    discussed_subjects: list[DiscussionSubject] = Field(description="Subjects, themes, or topics discussed (concepts, problems solved, questions answered, projects mentioned)")

class AgentDeps(BaseModel):
    """Dependencies for the agent."""
    memory: ConversationMemory = Field(default_factory=lambda: ConversationMemory(user_context=[], discussed_subjects=[]))


# Helper Functions
def calculate_token_usage(messages: list[ModelMessage]) -> tuple[int, float]:
    """Calculate total token usage from ModelResponse messages and percentage of limit."""
    total_tokens = 0

    for message in messages:
        if hasattr(message, "usage") and message.usage:
            usage = message.usage
            total_tokens += usage.input_tokens + usage.output_tokens

    percentage = (total_tokens / TOKEN_LIMIT) * 100
    return total_tokens, percentage

def format_memory_as_markdown(ctx: RunContext[AgentDeps]) -> str:
    """Format conversation memory as markdown for inclusion in instructions."""
    memory = ctx.deps.memory
    if memory is None or (not memory.user_context and not memory.discussed_subjects):
        return ""

    sections = []

    if memory.user_context:
        sections.append("### User Context:")
        sections.extend(f"- {context}" for context in memory.user_context)

    if memory.discussed_subjects:
        sections.append("\n### Discussed Subjects:")
        sections.extend(f"- **{subject.subject}**: {subject.summary}" for subject in memory.discussed_subjects)

    return "\n".join(sections)

# Agent Definitions
memory_consolidator = Agent[AgentDeps, ConversationMemory](
    "openai:gpt-4.1",
    output_type=ConversationMemory,
    deps_type=AgentDeps,
)

# History Processor
async def process_history_for_consolidation(ctx: RunContext[AgentDeps], messages: list[ModelMessage]) -> list[ModelMessage]:
    """Process message history: consolidate memory when token threshold is reached."""
    total_tokens, percentage = calculate_token_usage(messages)

    if total_tokens < TOKEN_LIMIT:
        print(f"\n✅ No consolidation needed ({total_tokens:,} tokens = {percentage:.1f}% of {TOKEN_LIMIT:,} limit)\n")
        return messages

    if messages and any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
        print("\n⚠️  Skipping consolidation (tool return at boundary)\n")
        return messages

    print(f"\n🔄 Consolidator triggered ({total_tokens:,} tokens = {percentage:.1f}% of {TOKEN_LIMIT:,} limit)\n")

    result = await memory_consolidator.run(message_history=messages, deps=ctx.deps)

    # Update ctx.deps.memory with the LLM-rebuilt conversation memory
    # Since ctx.deps is the same object reference as deps passed to run_stream, this automatically updates deps in the main loop
    ctx.deps.memory = result.output

    # Keep only the last message (should be the ModelRequest with the user's prompt)
    return [messages[-1]]

agent = Agent(
    OpenAIResponsesModel("gpt-4.1"),
    deps_type=AgentDeps,
    instructions="You are a simple conversational agent.",
    history_processors=[process_history_for_consolidation],
)

# Agent Instructions
@memory_consolidator.instructions
def consolidator_instructions(ctx: RunContext[AgentDeps]) -> str:
    """Dynamic instructions for memory consolidator agent."""
    return dedent("""\
        ## Role
        You are a memory consolidator.

        ## Objective
        Rebuild and grow the conversation memory by merging existing long-term memory with new conversation segments.

        ## Instructions
        1. **Merge existing and new information**: Review the existing conversation memory and incorporate any new information from the conversation.
        2. **Deduplicate**: Remove duplicate context items and merge similar discussed subjects rather than creating separate entries.
        3. **Grow organically**: Expand existing discussed subjects with new information when appropriate, or create new subjects when the topic significantly changes.
        4. **Refine**: Improve clarity and conciseness of existing user context and discussed subjects when reconsolidating.
        5. **Organize**: Structure the memory logically, grouping related subjects together.
        6. Refer to the AI as "you" and the other party as "the user."
        7. For each discussed subject's `summary`, produce a compact but detailed paragraph capturing: what was asked/explained, definitions, steps, examples, alternatives, constraints, decisions, and outcomes. Prefer dense prose over bullets; avoid conversational filler.

        ## User Context vs Discussed Subjects
        - user_context: Personal/professional context about the user (role, background, preferences, needs, motivations, constraints, etc.)
        - discussed_subjects: Subjects, themes, or topics discussed (specific subjects, problems solved, concepts learned, projects mentioned, etc.)
        - These should NOT overlap - user_context is about WHO the user is, discussed_subjects are about WHAT was discussed

        ## Output Format
        - user_context: Complete, deduplicated list of personal/professional context (merged from existing + new)
        - discussed_subjects: Complete list of subjects/themes discussed (merged, grown, or newly created as needed); each subject must include a detailed `summary` paragraph as described above.
        """)

@agent.instructions
@memory_consolidator.instructions
def include_memory_context(ctx: RunContext[AgentDeps]) -> str:
    """Include conversation memory context in agent instructions."""
    memory_markdown = format_memory_as_markdown(ctx)
    if not memory_markdown:
        return ""
    return f"## Conversation Memory\n{memory_markdown}"

async def main():
    deps = AgentDeps()
    message_history = []

    test_prompts = [
        "Hi, I'm Alex. I'm a high school teacher and I've recently started learning Python to teach my students.",
        "I've covered some basics, but I'm still a bit unsure about how to introduce programming concepts to beginners. Do you have any tips? I prefer hands-on activities over lectures.",
        "We've reached the topic of data structures. Could you explain the core data structures in Python?",
        "My students often get confused between lists and tuples. What is the key difference, and when should each be used? I teach 9th graders mostly, so keep it simple.",
        "I'd like to introduce dictionaries next. Can you show me how to create and use a dictionary in Python? I'm a visual learner, so examples help a lot.",
        "Some of my advanced students are curious about object-oriented programming. What is OOP in Python? I have about 3 students who are really into coding.",
        "Inheritance came up during our last class and I struggled to explain it clearly. Can you provide a simple example? I'm not very technical myself, so I need something I can understand first.",
        "I've heard about decorators in Python but never used them. What are they and how can they be used in teaching? I'm always looking for ways to make my code cleaner.",
        "My students and I are curious about Python's built-in functions. Can you give a brief overview? We have 45-minute class periods, so I need to keep things concise.",
        "Occasionally, we run into errors during coding. What's the best way to handle exceptions in Python with students? I get anxious when things break and the kids are watching.",
        "One final question: Students see both `==` and `is` in code samples online. What's the difference between them in Python? I want to make sure I give them accurate information.",
    ]

    for prompt in test_prompts:
        print(f"\n{BLUE}You:{RESET} {prompt}\n")

        async with agent.run_stream(prompt, deps=deps, message_history=message_history) as result:
            print(f"\n{BLUE}Agent:{RESET} ", end="", flush=True)

            async for chunk in result.stream_text(delta=True):
                print(chunk, end="", flush=True)

            message_history = result.all_messages()

            if message_history:
                total_tokens, percentage = calculate_token_usage(message_history)
                print(f"\n📊 Tokens: {total_tokens:,} ({percentage:.1f}% of {TOKEN_LIMIT:,} limit)")

if __name__ == "__main__":
    logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"), send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()
    with logfire.span(os.path.basename(os.path.dirname(__file__))):
        asyncio.run(main())
