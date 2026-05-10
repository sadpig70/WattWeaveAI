"""W2 — Foundation/ConfigLoader.

Loads zone registry and policy weights from JSON files. Defaults are
embedded so the system runs even with no config file present (useful
for tests and demos).
"""

from __future__ import annotations

import json
from pathlib import Path

from .types import ScoreWeights, Zone

DEFAULT_ZONES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "zones.json"


def load_zones(path: Path | None = None) -> list[Zone]:
    target = Path(path) if path else DEFAULT_ZONES_PATH
    if not target.exists():
        raise FileNotFoundError(f"Zone registry not found: {target}")
    raw = json.loads(target.read_text(encoding="utf-8"))
    return [Zone(**entry) for entry in raw]


def default_weights() -> ScoreWeights:
    return ScoreWeights()
