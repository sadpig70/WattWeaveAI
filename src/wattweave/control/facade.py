"""W12 — ControlPlane/OrchestrationFacade.

Single entry point: classify → tag → sense → decide → record. Both the
REST API and the CLI route through this class so behavior stays
identical regardless of channel.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..compliance.audit import AuditLog
from ..compliance.tagger import tag_compliance
from ..decision.scheduler import decide_routing
from ..decision.zone_registry import ZoneRegistry
from ..sensing.dc_telemetry import fetch_dc_snapshot
from ..sensing.grid_telemetry import fetch_grid_snapshot
from ..sensing.workload_classifier import classify_workload
from ..types import AuditRecord, RoutingDecision, ScoreWeights


class OrchestrationFacade:
    def __init__(
        self,
        zone_registry: ZoneRegistry,
        weights: ScoreWeights,
        audit_log: AuditLog,
        clock: Callable[[], datetime] | None = None,
    ):
        self.registry = zone_registry
        self.weights = weights
        self.audit = audit_log
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def submit(self, raw_request: dict[str, Any]) -> tuple[RoutingDecision, str]:
        now = self.clock()
        workload = classify_workload(raw_request)
        compliance = tag_compliance(workload)

        zones = self.registry.all()
        regions = self.registry.regions()
        grid_snapshots = {region: fetch_grid_snapshot(region, now) for region in regions}
        dc_snapshots = {z.zone_id: fetch_dc_snapshot(z, now) for z in zones}

        decision = decide_routing(
            workload=workload,
            zones=zones,
            grid_snapshots=grid_snapshots,
            dc_snapshots=dc_snapshots,
            weights=self.weights,
            now=now,
        )

        chosen_region = self._resolve_region(decision)
        record_id = uuid.uuid4().hex
        record = AuditRecord(
            record_id=record_id,
            workload=workload,
            decision=decision,
            compliance=compliance,
            grid_snapshot=grid_snapshots.get(chosen_region) or next(iter(grid_snapshots.values())),
            dc_snapshot=dc_snapshots.get(decision.chosen_zone_id) if decision.chosen_zone_id else None,
            recorded_at=now,
        )
        self.audit.append(record)
        return decision, record_id

    def _resolve_region(self, decision: RoutingDecision) -> str | None:
        if decision.chosen_zone_id is None:
            return None
        zone = self.registry.by_id(decision.chosen_zone_id)
        return zone.region if zone else None


def build_default_facade(audit_path: Path | None = None) -> OrchestrationFacade:
    registry = ZoneRegistry.from_default()
    weights = ScoreWeights()
    audit = AuditLog(audit_path or Path(".pgf/audit.jsonl"))
    return OrchestrationFacade(registry, weights, audit)
