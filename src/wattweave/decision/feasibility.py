"""W7 — Decision/FeasibilityFilter.

Hard-constraint pre-filter. Strictly deterministic; no AI_ calls. Any
zone returned MUST be safe to score (it has the chip, room to cool,
sovereign-compatible).
"""

from __future__ import annotations

from ..types import DataCenterSnapshot, SovereignClass, Workload, Zone


_COOLING_HARD_CAP = 0.95


def feasible_zones(
    workload: Workload,
    zones: list[Zone],
    dc_snapshots: dict[str, DataCenterSnapshot],
) -> list[Zone]:
    out: list[Zone] = []
    for zone in zones:
        if not _sovereign_compatible(workload.sovereign_class, zone.sovereign_class):
            continue
        snap = dc_snapshots.get(zone.zone_id)
        if snap is None:
            continue
        if snap.cooling_utilization >= _COOLING_HARD_CAP:
            continue
        if workload.chip_required != "any":
            available = snap.chip_available.get(workload.chip_required, 0)
            if available < 1:
                continue
        out.append(zone)
    return out


def _sovereign_compatible(workload_class: SovereignClass, zone_class: SovereignClass) -> bool:
    if workload_class == "none":
        return True
    if workload_class == "regulated_health":
        # health workloads must land on a zone explicitly cleared for them OR a
        # sovereign cloud the operator has marked as regulated-health-ready.
        return zone_class == "regulated_health"
    return workload_class == zone_class
