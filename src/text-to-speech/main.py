# https://www.openai.fm/

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.helpers import LocalAudioPlayer

load_dotenv()

openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Example weather report text
input = """Good morning! Here's your weather update for today.

We're looking at a beautiful day ahead with clear skies and plenty of sunshine. 
Temperatures will be mild, ranging from 18 to 24 degrees Celsius, with a gentle breeze from the northwest.

The UV index will be moderate, so don't forget your sunscreen if you're planning to spend time outdoors. 
Humidity levels will stay comfortable at around 60 percent throughout the day.

For those planning evening activities, the clear conditions will continue into the night, 
with temperatures dropping to a pleasant 15 degrees Celsius.

Perfect weather for outdoor activities, so make the most of this lovely day!"""

# Voice instructions for a weather reporter style
instructions = """Voice Affect:
Professional, clear, and engaging — speak with the confidence and warmth of a trusted weather presenter. 
Maintain a steady, informative tone while keeping the delivery natural and conversational.

Tone:
Friendly and authoritative — like a knowledgeable meteorologist who's excited to share good news. 
Keep the delivery upbeat but not overly dramatic, focusing on clear communication of the forecast.

Pacing:
Steady and measured — allow each piece of information to be clearly understood. 
Use natural pauses between different weather elements to help listeners process the information."""

async def main() -> None:

    async with openai.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="fable",
        input=input,
        instructions=instructions,
        response_format="pcm",
    ) as response:
        await LocalAudioPlayer().play(response)

if __name__ == "__main__":
    asyncio.run(main())
