"""Pydantic AI agent with one tool: treat a public JSON URL like a **data API** (GET once, cache the body as
pandas), then run DuckDB ``sql()`` on ``my_df`` (replacement scan—see DuckDB's *SQL on Pandas* guide) and
return CSV.

The endpoint below is raw GitHub content; in a real app you would swap it for your own HTTP API that returns
JSON records with the same shape.
"""

from __future__ import annotations

import asyncio
import io

import duckdb
import httpx
import pandas as pd
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

load_dotenv()

# Stand-in for a flights "GET /records" (or similar): returns a JSON array of row objects.
FLIGHTS_DATA_ENDPOINT = (
    "https://raw.githubusercontent.com/vega/vega-datasets/main/data/flights-20k.json"
)

# In-memory materialization of the last successful API-style response (Vega ``flights-20k``).
_flights_dataset: pd.DataFrame | None = None
_fetch_lock = asyncio.Lock()

_MAX_RESULT_ROWS = 500


async def fetch_flights_dataset() -> pd.DataFrame:
    """One-shot HTTP GET + JSON-to-DataFrame parse; cache the result like a session-scoped API client would."""
    global _flights_dataset
    async with _fetch_lock:
        if _flights_dataset is None:
            async with httpx.AsyncClient() as client:
                response = await client.get(FLIGHTS_DATA_ENDPOINT, timeout=60.0)
                response.raise_for_status()
                payload = response.content
            _flights_dataset = await asyncio.to_thread(
                pd.read_json,
                io.BytesIO(payload),
            )
        return _flights_dataset


def _duckdb_sql_on_dataframe_to_csv(flights_table: pd.DataFrame, sql: str) -> str:
    """DuckDB *SQL on Pandas*: bind ``flights_table`` as ``my_df``, run ``sql``, serialize rows to CSV."""
    my_df = flights_table  # noqa: F841 — name must exist for DuckDB replacement scan on ``my_df``.
    try:
        results = duckdb.sql(sql).df()
    except Exception as e:
        return f"SQL error: {e}"

    note = ""
    n = len(results)
    if n > _MAX_RESULT_ROWS:
        note = f"# truncated from {n} to {_MAX_RESULT_ROWS} rows\n"
        results = results.head(_MAX_RESULT_ROWS)
    return note + results.to_csv(index=False)


agent = Agent(
    "openai:gpt-5.4",
    instructions=(
        "You are a helpful assistant. Flight rows come from a remote JSON endpoint (cached after the first "
        "request). Answer questions by calling ``flights_sql`` with DuckDB SQL against ``my_df``. Interpret "
        "the CSV the tool returns; do not invent numbers."
    ),
)


@agent.tool
async def flights_sql(_ctx: RunContext[None], sql: str) -> str:
    """Run DuckDB SQL on ``my_df``, built from the cached flights **API** response (Vega ``flights-20k`` JSON).

    **Columns**

    - ``date`` — departure timestamp string (e.g. ``2001/01/01 00:47``)
    - ``delay`` — arrival delay in minutes (numeric; negative means early)
    - ``distance`` — route distance in miles (numeric)
    - ``origin`` — origin airport IATA code (text)
    - ``destination`` — destination airport IATA code (text)

    Pass a single ``SELECT`` (or DuckDB read of ``my_df``). Result rows are capped; output is CSV text
    (optional leading ``#`` comment if truncated).

    Example: ``SELECT origin, AVG(delay) AS avg_delay FROM my_df GROUP BY 1 ORDER BY 2 DESC LIMIT 10``
    """
    flights_table = await fetch_flights_dataset()
    return await asyncio.to_thread(_duckdb_sql_on_dataframe_to_csv, flights_table, sql)


async def main() -> None:
    await agent.to_cli()


if __name__ == "__main__":
    asyncio.run(main())
