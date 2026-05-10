"""W17 — AcceptanceCheck: programmatic verification of DESIGN-stated
acceptance_criteria. Produces a summary that the verify phase consumes.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from wattweave.compliance.audit import AuditLog
from wattweave.control.facade import OrchestrationFacade
from wattweave.decision.zone_registry import ZoneRegistry
from wattweave.types import ScoreWeights

T0 = datetime(2026, 5, 10, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def facade(tmp_path: Path) -> OrchestrationFacade:
    return OrchestrationFacade(
        zone_registry=ZoneRegistry.from_default(),
        weights=ScoreWeights(),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        clock=lambda: T0,
    )


def test_acceptance_score_weights_sum_to_one():
    w = ScoreWeights()
    assert abs(w.total() - 1.0) < 1e-9


def test_acceptance_facade_exercises_all_five_layers(facade):
    """submit() must invoke classify → tag → sense (grid+dc) → decide →
    record. We verify by checking the audit record has all five
    artifacts populated for a successful routing."""
    decision, record_id = facade.submit({
        "workload_id": "acc-1",
        "kind": "inference",
        "latency_class": "interactive",
        "sovereign_class": "us",
        "estimated_kwh": 5.0,
        "estimated_minutes": 10,
        "chip_required": "gpu_l4",
        "description": "acceptance",
    })
    records = facade.audit.replay("acc-1")
    assert len(records) == 1
    rec = records[0]
    assert rec["record_id"] == record_id
    assert rec["workload"]["workload_id"] == "acc-1"
    assert rec["compliance"]["workload_id"] == "acc-1"
    assert rec["grid_snapshot"] is not None
    assert rec["decision"]["chosen_zone_id"] == decision.chosen_zone_id
    if decision.chosen_zone_id is not None:
        assert rec["dc_snapshot"] is not None


def test_acceptance_decision_under_50ms(facade):
    """Mock-only path: a single decision must complete in well under 50ms."""
    import time

    payload = {
        "workload_id": "acc-perf",
        "kind": "inference",
        "latency_class": "batch",
        "sovereign_class": "none",
        "estimated_kwh": 1.0,
        "estimated_minutes": 5,
        "chip_required": "any",
    }
    start = time.perf_counter()
    facade.submit(payload)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 50.0, f"submit() took {elapsed_ms:.2f}ms (>50ms budget)"


def test_acceptance_audit_is_append_only(tmp_path):
    """Two submits must produce two lines in the JSONL; first line must
    remain unchanged after the second submit."""
    audit_path = tmp_path / "audit.jsonl"
    facade = OrchestrationFacade(
        zone_registry=ZoneRegistry.from_default(),
        weights=ScoreWeights(),
        audit_log=AuditLog(audit_path),
        clock=lambda: T0,
    )

    facade.submit({"workload_id": "a", "kind": "inference", "estimated_kwh": 1.0,
                   "estimated_minutes": 1, "chip_required": "any"})
    line_1 = audit_path.read_text(encoding="utf-8").splitlines()[0]

    facade.submit({"workload_id": "b", "kind": "inference", "estimated_kwh": 1.0,
                   "estimated_minutes": 1, "chip_required": "any"})
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == line_1


def test_acceptance_rest_api_round_trip(tmp_path):
    """FastAPI surface accepts a workload, returns a decision + record id,
    and the audit endpoint replays it."""
    from fastapi.testclient import TestClient

    from wattweave.control.api import create_app

    facade = OrchestrationFacade(
        zone_registry=ZoneRegistry.from_default(),
        weights=ScoreWeights(),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        clock=lambda: T0,
    )
    client = TestClient(create_app(facade))

    health = client.get("/v1/health")
    assert health.status_code == 200

    zones = client.get("/v1/zones")
    assert zones.status_code == 200 and len(zones.json()) >= 1

    resp = client.post("/v1/workloads", json={
        "workload_id": "api-1",
        "kind": "inference",
        "latency_class": "batch",
        "sovereign_class": "us",
        "estimated_kwh": 2.0,
        "estimated_minutes": 5,
        "chip_required": "gpu_l4",
        "description": "api round trip",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["audit_record_id"]
    assert body["decision"]["workload_id"] == "api-1"

    audit = client.get("/v1/workloads/api-1/audit")
    assert audit.status_code == 200
    assert len(audit.json()) == 1
