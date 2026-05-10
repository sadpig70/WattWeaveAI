"""W6 — Decision/ZoneRegistry.

Thin wrapper over the config loader that gives the Decision layer a
typed accessor. Kept separate from `config.py` because future versions
will index zones (by region, by chip class) for faster filtering.
"""

from __future__ import annotations

from pathlib import Path

from ..config import load_zones
from ..types import Zone


class ZoneRegistry:
    def __init__(self, zones: list[Zone]):
        self._zones: list[Zone] = list(zones)

    @classmethod
    def from_default(cls) -> "ZoneRegistry":
        return cls(load_zones())

    @classmethod
    def from_file(cls, path: Path) -> "ZoneRegistry":
        return cls(load_zones(path))

    def all(self) -> list[Zone]:
        return list(self._zones)

    def regions(self) -> set[str]:
        return {z.region for z in self._zones}

    def by_id(self, zone_id: str) -> Zone | None:
        for z in self._zones:
            if z.zone_id == zone_id:
                return z
        return None
