"""W4 — Sensing/GridTelemetry (mock connector).

Synthetic but deterministic grid signals. Replace per-region with real
OpenADR / wholesale-market adapters in production. The function signature
is the contract callers depend on; the body is pluggable.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime

from ..types import GridSnapshot

_REGION_BASE_PRICE = {
    "us-east": 55.0,
    "eu-west": 70.0,
    "eu-north": 35.0,
    "kr-central": 80.0,
    "jp-east": 95.0,
}

_REGION_BASE_CARBON = {
    "us-east": 380.0,
    "eu-west": 250.0,
    "eu-north": 80.0,
    "kr-central": 460.0,
    "jp-east": 420.0,
}


def fetch_grid_snapshot(region: str, now: datetime) -> GridSnapshot:
    seed = _seed(region, now)
    diurnal = math.sin((now.hour / 24.0) * 2 * math.pi)
    base_price = _REGION_BASE_PRICE.get(region, 75.0)
    base_carbon = _REGION_BASE_CARBON.get(region, 400.0)

    price = max(0.0, base_price + 12.0 * diurnal + 4.0 * seed)
    carbon = max(20.0, base_carbon - 60.0 * diurnal + 20.0 * seed)
    renewable_surplus = max(0.0, min(100.0, 50.0 + 30.0 * diurnal + 10.0 * seed))
    grid_stress = max(0.0, min(1.0, 0.45 - 0.25 * diurnal + 0.05 * seed))

    return GridSnapshot(
        region=region,
        timestamp=now,
        power_price_usd_mwh=round(price, 2),
        carbon_intensity_g_kwh=round(carbon, 2),
        renewable_surplus_pct=round(renewable_surplus, 2),
        grid_stress_index=round(grid_stress, 3),
    )


def _seed(region: str, now: datetime) -> float:
    """Return a value in [-1, 1] derived from (region, hour) so the same
    inputs produce the same noise term — required for test determinism.
    """
    bucket = now.replace(minute=0, second=0, microsecond=0).isoformat()
    digest = hashlib.sha256(f"{region}|{bucket}".encode()).digest()
    return (digest[0] / 127.5) - 1.0
