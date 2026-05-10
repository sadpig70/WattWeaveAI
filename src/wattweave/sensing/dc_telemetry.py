"""W5 — Sensing/DataCenterTelemetry (mock connector).

Mocks BMS + Kubernetes-style chip availability. Outputs are deterministic
on (zone_id, hour) so scenario tests can pin behavior.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from ..types import DataCenterSnapshot, Zone


def fetch_dc_snapshot(zone: Zone, now: datetime) -> DataCenterSnapshot:
    rng = _seed_unit(zone.zone_id, now)
    cooling_utilization = round(0.40 + rng * 0.40, 3)
    rack_density = round(60.0 + rng * 30.0, 2)

    chip_available: dict[str, int] = {}
    for chip_type, total in zone.chip_inventory.items():
        consumed = int(total * (0.10 + rng * 0.30))
        chip_available[chip_type] = max(0, total - consumed)

    return DataCenterSnapshot(
        zone_id=zone.zone_id,
        timestamp=now,
        cooling_utilization=cooling_utilization,
        chip_available=chip_available,
        rack_density_pct=rack_density,
    )


def _seed_unit(key: str, now: datetime) -> float:
    """Return a value in [0, 1] from a stable hash of (key, hour)."""
    bucket = now.replace(minute=0, second=0, microsecond=0).isoformat()
    digest = hashlib.sha256(f"{key}|{bucket}".encode()).digest()
    return digest[1] / 255.0
