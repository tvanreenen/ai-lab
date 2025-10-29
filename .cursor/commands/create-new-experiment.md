# Create New Experiment

Creates a new example/experiment in the `src/` directory with `main.py` and `pyproject.toml` files.

## main.py

```python
import asyncio

from dotenv import load_dotenv

load_dotenv()


async def main():
    """Main entry point for the application."""
    pass

if __name__ == "__main__":
    asyncio.run(main())
```

## pyproject.toml

```yaml
[project]
name = "Title Case Example Name"
version = "0.1.0"
description = "A brief sentence case description"
requires-python = ">=3.13"
dependencies = [
    "python-dotenv>=1.1.0",
]
```
