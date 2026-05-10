"""W15 — Unit tests for each Sensing/Decision/Compliance leaf."""

from datetime import datetime, timezone

import pytest

from wattweave.compliance.tagger import tag_compliance
from wattweave.decision.feasibility import feasible_zones
from wattweave.decision.scheduler import decide_routing
from wattweave.decision.scorer import score_zone
from wattweave.sensing.dc_telemetry import fetch_dc_snapshot
from wattweave.sensing.grid_telemetry import fetch_grid_snapshot
from wattweave.sensing.workload_classifier import (
    AI_estimate_energy_intensity,
    AI_infer_sovereign_class,
    ClassificationError,
    classify_workload,
)
from wattweave.types import (
    DataCenterSnapshot,
    GridSnapshot,
    ScoreWeights,
    Workload,
    Zone,
)

T0 = datetime(2026, 5, 10, 13, 0, tzinfo=timezone.utc)


def _zone(zone_id="z1", region="us-east", sov="us", chips=None, ztype="hyperscale", cap=500.0):
    return Zone(
        zone_id=zone_id,
        zone_type=ztype,
        region=region,
        sovereign_class=sov,
        chip_inventory=chips or {"gpu_h100": 8, "cpu": 64},
        cooling_headroom_kw=1000.0,
        max_carbon_intensity=cap,
    )


def _workload(**overrides):
    base = dict(
        workload_id="wl-x",
        kind="inference",
        latency_class="batch",
        energy_intensity="medium",
        sovereign_class="none",
        estimated_kwh=10.0,
        estimated_minutes=30,
        chip_required="any",
        submitted_at=T0,
        description="",
    )
    base.update(overrides)
    return Workload(**base)


# --- WorkloadClassifier ------------------------------------------------------

def test_classify_minimal_input_uses_defaults():
    wl = classify_workload({"workload_id": "w1"})
    assert wl.workload_id == "w1"
    assert wl.kind == "inference"
    assert wl.latency_class == "batch"
    assert wl.chip_required == "any"
    assert wl.sovereign_class == "none"


def test_classify_rejects_negative_kwh():
    with pytest.raises(ClassificationError):
        classify_workload({"workload_id": "w1", "estimated_kwh": -1.0})


def test_classify_rejects_unknown_enum_value():
    with pytest.raises(ClassificationError):
        classify_workload({"workload_id": "w1", "kind": "ml-magic"})


def test_AI_infer_sovereign_class_eu_keyword():
    assert AI_infer_sovereign_class("EU citizen training run", "training") == "eu"


def test_AI_infer_sovereign_class_health_keyword():
    assert (
        AI_infer_sovereign_class("HIPAA-protected patient inference", "inference")
        == "regulated_health"
    )


def test_AI_estimate_energy_intensity_extreme_for_heavy_training():
    assert AI_estimate_energy_intensity("training", 1000.0, 60) == "extreme"


def test_AI_estimate_energy_intensity_low_for_short_inference():
    assert AI_estimate_energy_intensity("inference", 0.5, 30) == "low"


# --- Telemetry determinism ---------------------------------------------------

def test_grid_snapshot_deterministic_on_same_inputs():
    a = fetch_grid_snapshot("eu-north", T0)
    b = fetch_grid_snapshot("eu-north", T0)
    assert a == b


def test_grid_snapshot_eu_north_is_low_carbon():
    snap = fetch_grid_snapshot("eu-north", T0)
    assert snap.carbon_intensity_g_kwh < 250.0  # nordic baseline ≪ kr/jp


def test_dc_snapshot_chip_available_le_inventory():
    z = _zone(chips={"gpu_h100": 32, "cpu": 100})
    s = fetch_dc_snapshot(z, T0)
    for chip, total in z.chip_inventory.items():
        assert 0 <= s.chip_available[chip] <= total
    assert 0.0 <= s.cooling_utilization <= 1.0


# --- FeasibilityFilter -------------------------------------------------------

def test_feasibility_blocks_sovereign_mismatch():
    wl = _workload(sovereign_class="eu", chip_required="gpu_h100")
    us_zone = _zone(zone_id="us1", sov="us")
    snaps = {us_zone.zone_id: DataCenterSnapshot(
        zone_id=us_zone.zone_id, timestamp=T0, cooling_utilization=0.5,
        chip_available={"gpu_h100": 4, "cpu": 50}, rack_density_pct=70.0,
    )}
    assert feasible_zones(wl, [us_zone], snaps) == []


def test_feasibility_blocks_when_chip_unavailable():
    wl = _workload(sovereign_class="us", chip_required="gpu_h100")
    z = _zone(zone_id="us1", sov="us")
    snaps = {z.zone_id: DataCenterSnapshot(
        zone_id=z.zone_id, timestamp=T0, cooling_utilization=0.4,
        chip_available={"gpu_h100": 0, "cpu": 50}, rack_density_pct=70.0,
    )}
    assert feasible_zones(wl, [z], snaps) == []


def test_feasibility_blocks_when_cooling_saturated():
    wl = _workload(sovereign_class="us")
    z = _zone(zone_id="us1", sov="us")
    snaps = {z.zone_id: DataCenterSnapshot(
        zone_id=z.zone_id, timestamp=T0, cooling_utilization=0.99,
        chip_available={"gpu_h100": 4, "cpu": 50}, rack_density_pct=70.0,
    )}
    assert feasible_zones(wl, [z], snaps) == []


def test_feasibility_passes_clean_zone():
    wl = _workload(sovereign_class="us", chip_required="gpu_h100")
    z = _zone(zone_id="us1", sov="us")
    snaps = {z.zone_id: DataCenterSnapshot(
        zone_id=z.zone_id, timestamp=T0, cooling_utilization=0.4,
        chip_available={"gpu_h100": 4, "cpu": 50}, rack_density_pct=70.0,
    )}
    assert feasible_zones(wl, [z], snaps) == [z]


# --- Scorer ------------------------------------------------------------------

def test_score_subscores_in_unit_interval():
    wl = _workload(sovereign_class="eu")
    z = _zone(sov="eu")
    grid = GridSnapshot("eu-north", T0, 50.0, 100.0, 60.0, 0.2)
    dc = DataCenterSnapshot(z.zone_id, T0, 0.4, {"gpu_h100": 4}, 70.0)
    s = score_zone(wl, z, grid, dc, ScoreWeights())
    for k in ("cost", "carbon", "latency", "sovereign", "composite"):
        assert 0.0 <= s[k] <= 1.0


def test_score_realtime_prefers_edge_over_hyperscale():
    grid = GridSnapshot("eu-west", T0, 60.0, 250.0, 50.0, 0.3)
    edge = _zone(zone_id="e1", ztype="edge", sov="none")
    hyper = _zone(zone_id="h1", ztype="hyperscale", sov="none")
    snap_e = DataCenterSnapshot(edge.zone_id, T0, 0.3, {"gpu_l4": 8}, 60.0)
    snap_h = DataCenterSnapshot(hyper.zone_id, T0, 0.3, {"gpu_l4": 8}, 60.0)
    wl = _workload(latency_class="realtime", chip_required="gpu_l4")
    se = score_zone(wl, edge, grid, snap_e, ScoreWeights())
    sh = score_zone(wl, hyper, grid, snap_h, ScoreWeights())
    assert se["latency"] > sh["latency"]


def test_score_carbon_penalty_when_above_zone_cap():
    z = _zone(cap=200.0)
    grid_clean = GridSnapshot("eu-north", T0, 50.0, 100.0, 60.0, 0.2)
    grid_dirty = GridSnapshot("eu-north", T0, 50.0, 600.0, 10.0, 0.7)
    wl = _workload(sovereign_class="us")
    dc = DataCenterSnapshot(z.zone_id, T0, 0.4, {"gpu_h100": 4}, 70.0)
    clean = score_zone(wl, z, grid_clean, dc, ScoreWeights())
    dirty = score_zone(wl, z, grid_dirty, dc, ScoreWeights())
    assert clean["carbon"] > dirty["carbon"]


# --- Scheduler ---------------------------------------------------------------

def test_decide_blocked_when_no_feasible_zone():
    wl = _workload(sovereign_class="eu")
    us_zone = _zone(sov="us")
    grids = {us_zone.region: GridSnapshot(us_zone.region, T0, 60.0, 380.0, 40.0, 0.4)}
    dcs = {us_zone.zone_id: DataCenterSnapshot(us_zone.zone_id, T0, 0.4, {"gpu_h100": 4}, 70.0)}
    decision = decide_routing(wl, [us_zone], grids, dcs, ScoreWeights(), now=T0)
    assert decision.chosen_zone_id is None
    assert decision.blocked_reason == "no_feasible_zone"


# --- ComplianceTagger --------------------------------------------------------

def test_tag_eu_training_requires_carbon_reporting_when_heavy():
    wl = _workload(
        sovereign_class="eu", kind="training",
        estimated_kwh=200.0, estimated_minutes=120,
    )
    tag = tag_compliance(wl)
    assert tag.data_locality_required == "eu"
    assert tag.carbon_reporting_required is True
    assert tag.eu_ai_act_tier in {"limited", "high", "minimal"}


def test_tag_health_workload_long_retention():
    wl = _workload(sovereign_class="regulated_health")
    tag = tag_compliance(wl)
    assert tag.audit_retention_days >= 365 * 7


def test_tag_low_intensity_inference_no_carbon_report():
    wl = _workload(kind="inference", energy_intensity="low", estimated_kwh=0.5)
    tag = tag_compliance(wl)
    assert tag.carbon_reporting_required is False
