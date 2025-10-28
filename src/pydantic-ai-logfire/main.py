#!/usr/bin/env python3
import asyncio
import time
from typing import Optional
import logfire
from logfire.experimental.annotations import record_feedback
from pydantic_ai import Agent
from logfire.propagate import get_context

import os
from dotenv import load_dotenv

load_dotenv()

logfire.configure(
    token=os.getenv("LOGFIRE_WRITE_TOKEN"),
    send_to_logfire='if-token-present',
    service_name=os.path.basename(__file__)
)
logfire.instrument_pydantic_ai()

agent = Agent('openai:gpt-4o-mini', instructions='You are a helpful AI assistant. Provide concise, accurate responses.')

original_run = agent.run

async def patched_run(*args, **kwargs):
    """Patched run that captures trace context for feedback."""
    print('patched_run')
    result = await original_run(*args, **kwargs)
    logfire_context = get_context()
    record_feedback(logfire_context.get('traceparent'), 'helpfulness', 1.0, comment='very helpful, i love it!')
    return result
    
agent.run = patched_run

async def main():
    await agent.to_cli()

if __name__ == "__main__":
    asyncio.run(main())
