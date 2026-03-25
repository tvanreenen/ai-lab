"""Pydantic AI response-style demos split across files (same ``calculator`` name, different behaviors).

Each script is a standalone CLI (``await agent.to_cli()``):

- ``pattern_1.py`` — ``calculator`` tool returns a plain string.
- ``pattern_2.py`` — ``calculator`` returns a structured model plus extra model-facing instructions.
- ``pattern_3.py`` — ``calculator`` **tool** runs a nested sub-agent via ``run()`` (tool return).

Shared math helper: ``_common.py``.

Example::

    uv run --package pydantic-ai-output-basics python \\
        src/pydantic-ai-output-basics/pattern_1.py
"""

import sys

if __name__ == "__main__":
    print(__doc__ or "", end="")
    raise SystemExit(
        print(
            "\nRun pattern_1.py through pattern_3.py (this file is documentation only).",
            file=sys.stderr,
        )
        or 1
    )
