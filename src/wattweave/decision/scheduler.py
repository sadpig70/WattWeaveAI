"""W9 — Decision/SchedulerCore.

Combines feasibility filter + multi-criteria scorer into a routing
decision. Tie-break order is **carbon, then cost** — emergent property
asked for in DESIGN §4.4 (matches the document's `creative emergence`
strength: carbon-aware behavior dominates ties).
"""

from __future__ import annotations

from datetime import datetime

from ..types import (
    DataCenterSnapshot,
    GridSnapshot,
    RoutingDecision,
    ScoreWeights,
    Workload,
    Zone,
)
from .feasibility import feasible_zones
from .scorer import score_zone


def decide_routing(
    workload: Workload,
    zones: list[Zone],
    grid_snapshots: dict[str, GridSnapshot],
    dc_snapshots: dict[str, DataCenterSnapshot],
    weights: ScoreWeights,
    now: datetime,
) -> RoutingDecision:
    feasible = feasible_zones(workload, zones, dc_snapshots)
    if not feasible:
        return RoutingDecision(
            workload_id=workload.workload_id,
            chosen_zone_id=None,
            score_breakdown={},
            candidates_considered=[z.zone_id for z in zones],
            reason=(
                "No feasible zone — workload could not satisfy sovereign / chip / "
                "cooling hard constraints across the registry."
            ),
            decided_at=now,
            blocked_reason="no_feasible_zone",
        )

    scored: list[tuple[Zone, dict[str, float]]] = []
    for zone in feasible:
        grid = grid_snapshots.get(zone.region)
        snap = dc_snapshots.get(zone.zone_id)
        if grid is None or snap is None:
            continue
        scored.append((zone, score_zone(workload, zone, grid, snap, weights)))

    if not scored:
        return RoutingDecision(
            workload_id=workload.workload_id,
            chosen_zone_id=None,
            score_breakdown={},
            candidates_considered=[z.zone_id for z in feasible],
            reason="Feasible zones present but telemetry snapshots missing.",
            decided_at=now,
            blocked_reason="missing_telemetry",
        )

    scored.sort(
        key=lambda t: (t[1]["composite"], t[1]["carbon"], t[1]["cost"]),
        reverse=True,
    )
    best_zone, best_scores = scored[0]
    alternatives = [(z.zone_id, s["composite"]) for z, s in scored[1:3]]
    reason = AI_explain_decision(workload, best_zone, best_scores, alternatives)

    return RoutingDecision(
        workload_id=workload.workload_id,
        chosen_zone_id=best_zone.zone_id,
        score_breakdown=best_scores,
        candidates_considered=[z.zone_id for z, _ in scored],
        reason=reason,
        decided_at=now,
    )


def AI_explain_decision(
    workload: Workload,
    chosen_zone: Zone,
    scores: dict[str, float],
    alternatives: list[tuple[str, float]],
) -> str:
    """Rule-based stub. Returns a one-paragraph human-readable reason.

    Future: replace with LLM call. Signature is the contract.
    """
    parts = [
        f"Workload {workload.workload_id} ({workload.kind}/{workload.latency_class}) "
        f"routed to zone {chosen_zone.zone_id} ({chosen_zone.zone_type}, {chosen_zone.region}).",
        (
            f"Composite score {scores['composite']:.3f} "
            f"[cost={scores['cost']:.2f}, carbon={scores['carbon']:.2f}, "
            f"latency={scores['latency']:.2f}, sovereign={scores['sovereign']:.2f}]."
        ),
    ]
    if scores["carbon"] >= 0.85:
        parts.append("Carbon score dominant — routing favors low-intensity grid.")
    if workload.sovereign_class != "none":
        parts.append(
            f"Sovereign class '{workload.sovereign_class}' satisfied by zone class "
            f"'{chosen_zone.sovereign_class}'."
        )
    if alternatives:
        alt = ", ".join(f"{zid}={score:.3f}" for zid, score in alternatives)
        parts.append(f"Top alternates: {alt}.")
    return " ".join(parts)
