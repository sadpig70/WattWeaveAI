"""W1 — Foundation/DomainTypes.

Single source of truth for workload, zone, telemetry, decision, and audit
types. All enum-like fields are typed via `Literal` so external input
validation can reuse them without a parallel definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

WorkloadKind = Literal["training", "inference", "fine_tuning", "batch_eval"]
LatencyClass = Literal["realtime", "interactive", "batch", "deferred"]
EnergyIntensity = Literal["low", "medium", "high", "extreme"]
SovereignClass = Literal["none", "eu", "us", "kr", "jp", "regulated_health"]
ChipType = Literal["gpu_h100", "gpu_a100", "gpu_l4", "cpu", "any"]
ZoneType = Literal["hyperscale", "colocation", "sovereign_cloud", "edge", "smart_city"]
EuAiActTier = Literal["minimal", "limited", "high", "unacceptable"]


@dataclass
class Workload:
    workload_id: str
    kind: WorkloadKind
    latency_class: LatencyClass
    energy_intensity: EnergyIntensity
    sovereign_class: SovereignClass
    estimated_kwh: float
    estimated_minutes: int
    chip_required: ChipType
    submitted_at: datetime
    description: str = ""


@dataclass
class Zone:
    zone_id: str
    zone_type: ZoneType
    region: str
    sovereign_class: SovereignClass
    chip_inventory: dict[str, int]
    cooling_headroom_kw: float
    max_carbon_intensity: float


@dataclass
class GridSnapshot:
    region: str
    timestamp: datetime
    power_price_usd_mwh: float
    carbon_intensity_g_kwh: float
    renewable_surplus_pct: float
    grid_stress_index: float


@dataclass
class DataCenterSnapshot:
    zone_id: str
    timestamp: datetime
    cooling_utilization: float
    chip_available: dict[str, int]
    rack_density_pct: float


@dataclass
class RoutingDecision:
    workload_id: str
    chosen_zone_id: Optional[str]
    score_breakdown: dict[str, float]
    candidates_considered: list[str]
    reason: str
    decided_at: datetime
    blocked_reason: Optional[str] = None


@dataclass
class ComplianceTag:
    workload_id: str
    eu_ai_act_tier: Optional[EuAiActTier]
    data_locality_required: Optional[str]
    carbon_reporting_required: bool
    audit_retention_days: int


@dataclass
class AuditRecord:
    record_id: str
    workload: Workload
    decision: RoutingDecision
    compliance: ComplianceTag
    grid_snapshot: GridSnapshot
    dc_snapshot: Optional[DataCenterSnapshot]
    recorded_at: datetime


@dataclass
class ScoreWeights:
    cost: float = 0.25
    carbon: float = 0.30
    latency: float = 0.25
    sovereign: float = 0.20

    def total(self) -> float:
        return self.cost + self.carbon + self.latency + self.sovereign
