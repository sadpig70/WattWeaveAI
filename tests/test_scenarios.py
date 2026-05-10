"""W16 — Scenario tests covering the 5 flows from DESIGN §7.2.

Each scenario uses the real OrchestrationFacade with a frozen clock so
behavior is deterministic.
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
    audit = AuditLog(tmp_path / "audit.jsonl")
    f = OrchestrationFacade(
        zone_registry=ZoneRegistry.from_default(),
        weights=ScoreWeights(),
        audit_log=audit,
        clock=lambda: T0,
    )
    return f


# -- Scenario A: Carbon-aware routing ----------------------------------------

def test_scenario_A_carbon_aware_routing(facade):
    """An EU-class training run should land in nordic-colo-1 (low carbon)
    rather than the EU hyperscale region."""
    decision, _ = facade.submit({
        "workload_id": "scA-1",
        "kind": "training",
        "latency_class": "batch",
        "sovereign_class": "eu",
        "estimated_kwh": 400.0,
        "estimated_minutes": 240,
        "chip_required": "gpu_h100",
        "description": "EU recommendation model fine-tune",
    })
    assert decision.chosen_zone_id == "nordic-colo-1"
    assert decision.score_breakdown["carbon"] >= 0.85


# -- Scenario B: Sovereign cloud routing -------------------------------------

def test_scenario_B_eu_workload_excludes_us_zones(facade):
    """An EU-class inference must never land in a US-only zone."""
    decision, _ = facade.submit({
        "workload_id": "scB-1",
        "kind": "inference",
        "latency_class": "interactive",
        "sovereign_class": "eu",
        "estimated_kwh": 5.0,
        "estimated_minutes": 10,
        "chip_required": "gpu_l4",
        "description": "EU citizen inference",
    })
    assert decision.chosen_zone_id is not None
    chosen = facade.registry.by_id(decision.chosen_zone_id)
    assert chosen is not None and chosen.sovereign_class == "eu"


# -- Scenario C: Realtime latency protection ---------------------------------

def test_scenario_C_realtime_workload_avoids_pure_hyperscale(facade):
    """A realtime workload should pick an edge / smart_city zone, not a
    bare hyperscale region (latency score discriminates)."""
    decision, _ = facade.submit({
        "workload_id": "scC-1",
        "kind": "inference",
        "latency_class": "realtime",
        "sovereign_class": "kr",
        "estimated_kwh": 0.5,
        "estimated_minutes": 1,
        "chip_required": "gpu_l4",
        "description": "Korean smart-city realtime traffic inference",
    })
    assert decision.chosen_zone_id is not None
    chosen = facade.registry.by_id(decision.chosen_zone_id)
    assert chosen.zone_type in {"edge", "smart_city"}


# -- Scenario D: Feasibility 0 → blocked -------------------------------------

def test_scenario_D_no_feasible_zone_blocks(facade):
    """A workload requesting an unsupported chip on a sovereign class with
    only one matching zone (which doesn't stock the chip) must block."""
    decision, _ = facade.submit({
        "workload_id": "scD-1",
        "kind": "training",
        "latency_class": "batch",
        "sovereign_class": "jp",
        "estimated_kwh": 100.0,
        "estimated_minutes": 60,
        "chip_required": "gpu_h100",   # tokyo-edge only stocks gpu_l4 + cpu
        "description": "JP-only heavy training",
    })
    assert decision.chosen_zone_id is None
    assert decision.blocked_reason == "no_feasible_zone"


# -- Scenario E: Audit replay reproducibility --------------------------------

def test_scenario_E_audit_replay_is_reproducible(facade):
    """Submitting the same workload twice with the same clock must yield
    the same chosen zone and the same composite score."""
    payload = {
        "workload_id": "scE-1",
        "kind": "fine_tuning",
        "latency_class": "batch",
        "sovereign_class": "eu",
        "estimated_kwh": 250.0,
        "estimated_minutes": 180,
        "chip_required": "gpu_a100",
        "description": "Reproducible run",
    }
    d1, _ = facade.submit(payload)

    payload2 = dict(payload)
    payload2["workload_id"] = "scE-2"
    d2, _ = facade.submit(payload2)

    assert d1.chosen_zone_id == d2.chosen_zone_id
    assert d1.score_breakdown == d2.score_breakdown

    # Replay returns at least one record per workload.
    assert len(facade.audit.replay("scE-1")) == 1
    assert len(facade.audit.replay("scE-2")) == 1
