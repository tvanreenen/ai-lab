from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    data: Path
    stage: Path
    artifacts: Path
    output: Path


def get_paths() -> Paths:
    root = Path(__file__).resolve().parent
    data = root / "data"
    stage = data / "stage"
    artifacts = root / "artifacts"
    output = data / "output"
    for p in (data, stage, artifacts, output):
        p.mkdir(parents=True, exist_ok=True)
    return Paths(root=root, data=data, stage=stage, artifacts=artifacts, output=output)


def log_stage(name: str, **kv: object) -> None:
    parts = [f"{k}={v}" for k, v in kv.items()]
    suffix = f" | {' '.join(parts)}" if parts else ""
    print(f"[{name}]{suffix}")
