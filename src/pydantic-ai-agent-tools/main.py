"""Example agent wiring three tool patterns in one place.

1. **Custom sync tool** — ``calculator``: plain Python on the agent via ``@agent.tool``.
2. **Bundled library tool** — ``duckduckgo_search_tool`` from ``pydantic_ai.common_tools``,
   passed into ``Agent(..., tools=[...])``.
3. **Custom async tool** — ``weather_forecast``: ``httpx`` call to an external HTTP API,
   returning raw JSON text for the model.
"""

import asyncio
import json
import math

import httpx
import numexpr
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool

load_dotenv()

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
_OPEN_METEO_QUERY = {
    "daily": "sunrise,sunset",
    "current": (
        "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
        "wind_gusts_10m,apparent_temperature,pressure_msl"
    ),
    "timezone": "auto",
    "forecast_days": 1,
    "wind_speed_unit": "mph",
    "temperature_unit": "fahrenheit",
    "precipitation_unit": "inch",
}


agent = Agent(
    "openai:gpt-5.4",
    tools=[duckduckgo_search_tool(max_results=5)],
    instructions=(
        "You are a helpful assistant with calculator, DuckDuckGo web search, and Open-Meteo weather "
        "tools. Use a tool when it improves the answer; explain briefly what you did when helpful."
    ),
)


@agent.tool
def calculator(ctx: RunContext[None], expression: str) -> str:
    """Evaluate a single-line mathematical expression (numexpr). Constants: pi, e."""
    try:
        result = numexpr.evaluate(
            expression.strip(),
            global_dict={},
            local_dict={"pi": math.pi, "e": math.e},
        )
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"


@agent.tool
async def weather_forecast(ctx: RunContext[None], latitude: float, longitude: float) -> str:
    """Current conditions and today's sunrise/sunset from Open-Meteo (free, no API key). Use WGS84 latitude and longitude in decimal degrees."""
    params = _OPEN_METEO_QUERY | {"latitude": latitude, "longitude": longitude}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(OPEN_METEO_FORECAST, params=params, timeout=30.0)
            r.raise_for_status()
            data = r.json()
        if (reason := data.get("reason")) is not None:
            return f"Open-Meteo error: {reason}"
        return json.dumps(data, indent=2)
    except httpx.HTTPError as e:
        return f"Weather request failed: {e}"


async def main() -> None:
    await agent.to_cli()


if __name__ == "__main__":
    asyncio.run(main())
