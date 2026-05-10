"""W8 — Decision/MultiCriteriaScorer.

Four-axis normalized scoring (cost / carbon / latency / sovereign).
All sub-scores live in [0, 1] where 1 = better. Composite is a weighted
sum; weights are configured in `ScoreWeights`.
"""

from __future__ import annotations

from ..types import (
    DataCenterSnapshot,
    GridSnapshot,
    LatencyClass,
    ScoreWeights,
    SovereignClass,
    Workload,
    Zone,
    ZoneType,
)


_PRICE_FLOOR_USD = 20.0
_PRICE_CEILING_USD = 250.0
_CARBON_FLOOR = 50.0
_CARBON_CEILING = 800.0


def score_zone(
    workload: Workload,
    zone: Zone,
    grid: GridSnapshot,
    dc: DataCenterSnapshot,
    weights: ScoreWeights,
) -> dict[str, float]:
    cost_score = _normalize_cost(grid.power_price_usd_mwh)
    carbon_score = _normalize_carbon(grid.carbon_intensity_g_kwh, zone.max_carbon_intensity)
    latency_score = _latency_match(workload.latency_class, zone.zone_type)
    sovereign_score = _sovereign_match(workload.sovereign_class, zone.sovereign_class)

    composite = (
        cost_score * weights.cost
        + carbon_score * weights.carbon
        + latency_score * weights.latency
        + sovereign_score * weights.sovereign
    )

    return {
        "cost": round(cost_score, 4),
        "carbon": round(carbon_score, 4),
        "latency": round(latency_score, 4),
        "sovereign": round(sovereign_score, 4),
        "composite": round(composite, 4),
    }


def _normalize_cost(price_usd_mwh: float) -> float:
    if price_usd_mwh <= _PRICE_FLOOR_USD:
        return 1.0
    if price_usd_mwh >= _PRICE_CEILING_USD:
        return 0.0
    span = _PRICE_CEILING_USD - _PRICE_FLOOR_USD
    return 1.0 - (price_usd_mwh - _PRICE_FLOOR_USD) / span


def _normalize_carbon(intensity_g_kwh: float, zone_cap: float) -> float:
    if intensity_g_kwh > zone_cap:
        # Hard policy violation: penalize but don't return negative.
        excess = (intensity_g_kwh - zone_cap) / max(zone_cap, 1.0)
        return max(0.0, 0.2 - 0.2 * min(excess, 1.0))
    if intensity_g_kwh <= _CARBON_FLOOR:
        return 1.0
    if intensity_g_kwh >= _CARBON_CEILING:
        return 0.0
    span = _CARBON_CEILING - _CARBON_FLOOR
    return 1.0 - (intensity_g_kwh - _CARBON_FLOOR) / span


_LATENCY_MATRIX: dict[LatencyClass, dict[ZoneType, float]] = {
    "realtime":    {"edge": 1.0, "smart_city": 0.95, "hyperscale": 0.3, "colocation": 0.4, "sovereign_cloud": 0.5},
    "interactive": {"edge": 0.9, "smart_city": 0.85, "hyperscale": 0.85, "colocation": 0.8, "sovereign_cloud": 0.85},
    "batch":       {"edge": 0.4, "smart_city": 0.4, "hyperscale": 1.0, "colocation": 0.95, "sovereign_cloud": 0.9},
    "deferred":    {"edge": 0.3, "smart_city": 0.3, "hyperscale": 1.0, "colocation": 1.0, "sovereign_cloud": 0.9},
}


def _latency_match(latency: LatencyClass, zone_type: ZoneType) -> float:
    return _LATENCY_MATRIX.get(latency, {}).get(zone_type, 0.5)


def _sovereign_match(workload_class: SovereignClass, zone_class: SovereignClass) -> float:
    if workload_class == "none":
        return 0.7
    if workload_class == zone_class:
        return 1.0
    return 0.0
