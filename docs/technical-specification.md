# WattWeaveAI — Technical Specification

**Document type**: Software Design Specification (SDS) · v0.1
**Target audience**: engineers, integrators, and reviewers evaluating WattWeaveAI for production adoption or extension
**Last revised**: 2026-05-10
**Authoritative artifacts**: `.pgf/DESIGN-WattWeaveAI.md` (PG/PGF design notation) · `src/wattweave/` (implementation) · `tests/` (acceptance & scenarios)

---

## 1. Executive Summary

WattWeaveAI is the reference implementation of **EnerGrid AI Fabric** — an AI-native control plane that routes AI workloads across data centers, sovereign clouds, and edge zones based on a unified scoring of **cost, carbon, latency, sovereignty, and chip availability**, with regulatory metadata travelling alongside the workload as a first-class scheduling input rather than a post-hoc audit overlay.

The v0.1 scope delivers a fully terrestrial, software-only control plane:

- 4-tier execution path: `classify → tag → sense → decide → record`
- Hard-constraint feasibility filter + four-axis multi-criteria scorer with carbon-priority tie-break
- Append-only JSONL audit log with snapshot-bundled replay
- FastAPI REST surface + argparse CLI, both backed by a single `OrchestrationFacade`
- Deterministic mock connectors (region/zone hour-keyed) so the system behaves reproducibly during testing and demos
- A defined `ExpansionSocket` reservation for smart-city, sovereign-cloud, and orbital extensions in subsequent milestones

The system was designed and verified end-to-end via PG (PPR/Gantree Notation) and PGF (PPR/Gantree Framework). Every architectural commitment in this document is traceable to a node in `.pgf/DESIGN-WattWeaveAI.md` and is asserted by an automated test in `tests/`.

---

## 2. Goals and Non-Goals

### 2.1 Goals (in scope, v0.1)

1. Provide a deterministic, testable engine that selects an execution zone for an incoming AI workload given (a) workload metadata and (b) live-or-mocked grid + data-center telemetry.
2. Make the regulatory profile of the workload (sovereignty, EU AI Act tier, carbon-reporting obligation, audit retention) flow into scheduling input — not be applied afterwards.
3. Produce a replayable audit record per decision that bundles inputs, the decision, and the snapshots that produced it.
4. Expose the same logic via REST and CLI through a single facade.
5. Reserve typed extension points (`ExpansionSocket`) for future zone classes (smart-city, sovereign cloud, orbital) so they plug in without redesign.
6. Demonstrate the **PG Co-evolutionary Property**: AI cognitive functions are present at well-defined boundaries (`AI_` prefix), implemented as deterministic stubs in v0.1, swappable for LLM backends without changes to callers.

### 2.2 Non-Goals (deferred)

| # | Out of scope (v0.1) | Target milestone |
|---|---|---|
| NG-1 | Real OpenADR / wholesale-market grid adapters | v0.2 |
| NG-2 | Real Kubernetes / BMS data-center adapters | v0.2 |
| NG-3 | PQC-signed audit records (ML-DSA) | v0.2 |
| NG-4 | LLM-backed `AI_` functions | v0.2+ |
| NG-5 | Multi-tenant isolation, RBAC, billing | v0.3 |
| NG-6 | Smart-city microgrid producer/consumer pairing | v0.3 |
| NG-7 | Compute-energy market, carbon arbitrage | v0.3 |
| NG-8 | LEO / orbital zone class | v1.0 |
| NG-9 | High availability, sharding, replication | post-MVP |
| NG-10 | Cost forecasting / energy hedging | post-MVP |

WattWeaveAI v0.1 is a **single-process Python control plane** intended to validate the architecture end-to-end and serve as a substrate for the deferred items above.

---

## 3. Glossary

| Term | Definition |
|---|---|
| **Workload** | A unit of AI work submitted to the control plane (training, inference, fine-tuning, batch evaluation), described by latency class, energy intensity, sovereign class, chip requirement, etc. |
| **Zone** | A candidate execution location: `hyperscale`, `colocation`, `sovereign_cloud`, `edge`, or `smart_city`. Each zone has a region, sovereign class, chip inventory, cooling headroom, and a maximum carbon-intensity policy ceiling. |
| **Sovereign class** | The regulatory bucket for a workload or zone (`none`, `eu`, `us`, `kr`, `jp`, `regulated_health`). Compatibility rules are enforced as hard constraints. |
| **GridSnapshot** | A point-in-time signal vector for one region: power price, carbon intensity, renewable surplus, grid stress index. |
| **DataCenterSnapshot** | A point-in-time signal vector for one zone: cooling utilization, chip availability, rack density. |
| **RoutingDecision** | The output of the scheduler: chosen zone (or `None` if blocked), score breakdown, candidates considered, human-readable reason, and a blocked-reason if applicable. |
| **ComplianceTag** | EU AI Act tier, data-locality requirement, carbon-reporting flag, and audit-retention days, derived from the workload at submission time. |
| **AuditRecord** | An immutable append-only record bundling workload + decision + tag + grid/DC snapshots + timestamps. |
| **OrchestrationFacade** | The single in-process entry point that performs `classify → tag → sense → decide → record`. |
| **ExpansionSocket** | The reserved Gantree subtree (smart-city / sovereign-cloud / orbital) that downstream milestones activate. |
| **PG / PGF** | PPR/Gantree Notation and Framework — the design language and lifecycle this project was authored in. |
| **AI_ function** | A function whose name starts with `AI_`, indicating a cognitive boundary where an LLM may be substituted in future versions. v0.1 implementations are rule-based stubs that honour the same signature. |

---

## 4. Architecture Overview

### 4.1 Layered structure

```
┌─────────────────────────────────────────────────────────────┐
│                       Control Plane                         │
│   ─ FastAPI REST  ─ argparse CLI  ─ OrchestrationFacade     │
└────────────────────────────┬────────────────────────────────┘
                             │
       ┌─────────────────────┴─────────────────────┐
       │                Decision                   │
       │  ZoneRegistry → FeasibilityFilter →       │
       │  MultiCriteriaScorer → SchedulerCore      │
       └─────────────────────┬─────────────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                Sensing                  │
        │  WorkloadClassifier · GridTelemetry ·   │
        │             DataCenterTelemetry         │
        └────────────────────┬────────────────────┘
                             │
       ┌─────────────────────┴─────────────────────┐
       │              Compliance                   │
       │   ComplianceTagger · AuditLog (JSONL)     │
       └─────────────────────┬─────────────────────┘
                             │
       ┌─────────────────────┴─────────────────────┐
       │          Foundation (DomainTypes)         │
       │ Workload · Zone · GridSnapshot ·          │
       │ DataCenterSnapshot · RoutingDecision ·    │
       │ ComplianceTag · AuditRecord · Weights     │
       └───────────────────────────────────────────┘
```

### 4.2 Module map

| Layer | Module | Responsibility |
|---|---|---|
| Foundation | `wattweave.types` | Single source of truth for all dataclasses and `Literal` enumerations |
| Foundation | `wattweave.config` | Load zones from JSON; provide default `ScoreWeights` |
| Sensing | `wattweave.sensing.workload_classifier` | Decode external dict → `Workload`, invoke AI_ stubs for missing fields |
| Sensing | `wattweave.sensing.grid_telemetry` | Deterministic mock OpenADR-style adapter (region, hour) → `GridSnapshot` |
| Sensing | `wattweave.sensing.dc_telemetry` | Deterministic mock BMS / chip-operator adapter → `DataCenterSnapshot` |
| Decision | `wattweave.decision.zone_registry` | Typed accessor over the loaded `Zone` set |
| Decision | `wattweave.decision.feasibility` | Hard-constraint pre-filter (sovereign / chip / cooling) |
| Decision | `wattweave.decision.scorer` | Four-axis normalized score in [0, 1] per zone |
| Decision | `wattweave.decision.scheduler` | Orchestrate filter + score + tie-break + reason |
| Compliance | `wattweave.compliance.tagger` | Derive `ComplianceTag` from workload before scheduling |
| Compliance | `wattweave.compliance.audit` | Append-only JSONL writer + workload-id replay |
| ControlPlane | `wattweave.control.facade` | Single in-process entry: `submit(raw_request) → (decision, record_id)` |
| ControlPlane | `wattweave.control.api` | FastAPI router over the facade |
| ControlPlane | `wattweave.control.cli` | argparse CLI over the facade |

### 4.3 Dependency graph

The directed dependency graph is acyclic and topologically ordered:

```
Foundation/types
    ├─→ Sensing/{classifier, grid, dc}
    ├─→ Decision/{registry, feasibility, scorer, scheduler}
    │       └─ scheduler ← feasibility, scorer
    ├─→ Compliance/{tagger, audit}
    └─→ ControlPlane/{facade}
                ├─→ ControlPlane/api
                └─→ ControlPlane/cli
```

All cross-layer calls flow downward. There are no upward references and no circular imports.

---

## 5. Domain Model

All types are defined in `src/wattweave/types.py` as Python `dataclass`es. `Literal` types are used for all enumerated fields so external input validators can reuse them as the single source of truth.

### 5.1 Enumerations

| Type | Values |
|---|---|
| `WorkloadKind` | `training` · `inference` · `fine_tuning` · `batch_eval` |
| `LatencyClass` | `realtime` · `interactive` · `batch` · `deferred` |
| `EnergyIntensity` | `low` · `medium` · `high` · `extreme` |
| `SovereignClass` | `none` · `eu` · `us` · `kr` · `jp` · `regulated_health` |
| `ChipType` | `gpu_h100` · `gpu_a100` · `gpu_l4` · `cpu` · `any` |
| `ZoneType` | `hyperscale` · `colocation` · `sovereign_cloud` · `edge` · `smart_city` |
| `EuAiActTier` | `minimal` · `limited` · `high` · `unacceptable` |

### 5.2 Core records

```text
Workload
  workload_id: str
  kind: WorkloadKind
  latency_class: LatencyClass
  energy_intensity: EnergyIntensity
  sovereign_class: SovereignClass
  estimated_kwh: float                       # >= 0
  estimated_minutes: int                     # >= 0
  chip_required: ChipType
  submitted_at: datetime
  description: str = ""                      # used by AI_ stubs

Zone
  zone_id: str
  zone_type: ZoneType
  region: str                                # iso region code
  sovereign_class: SovereignClass
  chip_inventory: dict[str, int]
  cooling_headroom_kw: float
  max_carbon_intensity: float                # gCO2/kWh policy ceiling

GridSnapshot
  region: str
  timestamp: datetime
  power_price_usd_mwh: float                 # >= 0
  carbon_intensity_g_kwh: float              # bounded [50, 700] in MVP synthesis
  renewable_surplus_pct: float               # [0, 100]
  grid_stress_index: float                   # [0, 1]   1 = congested

DataCenterSnapshot
  zone_id: str
  timestamp: datetime
  cooling_utilization: float                 # [0, 1]
  chip_available: dict[str, int]             # always <= zone.chip_inventory
  rack_density_pct: float

RoutingDecision
  workload_id: str
  chosen_zone_id: Optional[str]              # None if blocked
  score_breakdown: dict[str, float]          # cost, carbon, latency, sovereign, composite
  candidates_considered: list[str]
  reason: str                                # AI_explain_decision output
  decided_at: datetime
  blocked_reason: Optional[str]              # 'no_feasible_zone' | 'missing_telemetry'

ComplianceTag
  workload_id: str
  eu_ai_act_tier: Optional[EuAiActTier]
  data_locality_required: Optional[str]
  carbon_reporting_required: bool
  audit_retention_days: int

AuditRecord
  record_id: str                             # UUIDv4 hex
  workload: Workload
  decision: RoutingDecision
  compliance: ComplianceTag
  grid_snapshot: GridSnapshot
  dc_snapshot: Optional[DataCenterSnapshot]  # None if blocked
  recorded_at: datetime

ScoreWeights
  cost: float = 0.25
  carbon: float = 0.30
  latency: float = 0.25
  sovereign: float = 0.20
  total() == 1.0   (asserted by tests)
```

---

## 6. The Routing Algorithm

The decision pipeline is deterministic given fixed inputs (workload + grid snapshots + DC snapshots + weights + tie-break order). It performs:

```
1. Classify              raw_request -> Workload
2. Tag                   Workload    -> ComplianceTag
3. Sense (parallel-safe) {region: GridSnapshot}, {zone_id: DataCenterSnapshot}
4. Filter feasibility    Workload, Zones, DCSnapshots -> feasible: list[Zone]
5. Score each feasible   Workload, Zone, GridSnap, DCSnap, Weights -> {axis: float}
6. Sort                  by (composite, carbon, cost), all DESC
7. Pick top              -> RoutingDecision
8. Explain               AI_explain_decision -> reason: str
9. Record                AuditRecord -> AuditLog (JSONL append)
```

### 6.1 Feasibility (hard constraints)

A zone qualifies for scoring only if **all** of the following hold:

1. **Sovereign compatibility** — `_sovereign_compatible(workload.sovereign_class, zone.sovereign_class)`:
   - `none` workload class accepts any zone
   - `regulated_health` workload class accepts only `regulated_health` zone class
   - All other classes require exact match
2. **Chip availability** — when `workload.chip_required != "any"`, `dc_snapshot.chip_available[chip_required] >= 1`
3. **Cooling headroom** — `dc_snapshot.cooling_utilization < 0.95`

If no zone satisfies all three, the scheduler returns a decision with `chosen_zone_id=None` and `blocked_reason="no_feasible_zone"`.

### 6.2 Multi-criteria scoring

Each feasible zone receives four sub-scores in [0, 1] (1 = better) plus a composite:

| Axis | Computation |
|---|---|
| `cost` | Linear normalization of `grid.power_price_usd_mwh` over the band [USD 20, USD 250] per MWh. Below the floor → 1.0; above the ceiling → 0.0. |
| `carbon` | If `grid.carbon_intensity_g_kwh > zone.max_carbon_intensity` → policy violation, capped at ≤ 0.20. Otherwise linear normalization over [50, 800] g/kWh. |
| `latency` | Static lookup matrix `(LatencyClass × ZoneType) → [0, 1]`. `realtime` favours `edge`/`smart_city`; `batch` favours `hyperscale`/`colocation`. |
| `sovereign` | 1.0 on exact class match, 0.0 on mismatch with explicit class, 0.7 when workload class is `none`. |
| `composite` | `cost·w_cost + carbon·w_carbon + latency·w_latency + sovereign·w_sovereign` with default weights summing to 1.0. |

### 6.3 Tie-break

Sort by `(composite, carbon, cost)` all descending. **Carbon comes before cost** — this is the project's explicit emergent property and is asserted by Scenario A in `tests/test_scenarios.py`.

### 6.4 Reason generation

The chosen zone, its score breakdown, and the top two alternates are passed to `AI_explain_decision()`, which returns a one-paragraph human-readable narrative. In v0.1 this is a deterministic rule-based stub that emits a fixed-shape sentence; the signature is the contract for future LLM substitution.

### 6.5 Worst-case complexity

For `Z` zones and a single workload, the pipeline is `O(Z)` filter + `O(Z)` score + `O(Z log Z)` sort. With the v0.1 seed of 6 zones, end-to-end submission completes well under 5 ms (acceptance budget: 50 ms).

---

## 7. Compliance Model

Compliance is computed *before* scheduling and travels with the workload as a first-class input. This is the central architectural commitment — described in DESIGN §0 and grounded in the source ideation documents — that distinguishes WattWeaveAI from "schedule first, audit later" platforms.

### 7.1 Tag derivation rules

| Workload property | Resulting tag |
|---|---|
| `sovereign_class == "eu"` | `data_locality_required = "eu"`, `eu_ai_act_tier ∈ {minimal, limited, high}` (inferred from kind + description) |
| `sovereign_class == "us" \| "kr" \| "jp"` | `data_locality_required` set to the corresponding region |
| `sovereign_class == "regulated_health"` | `eu_ai_act_tier = "high"`, `audit_retention_days >= 7 × 365` |
| `kind ∈ {training, fine_tuning}` AND `estimated_kwh >= 100` | `carbon_reporting_required = True` |
| `energy_intensity ∈ {high, extreme}` | `carbon_reporting_required = True` |
| Default | `audit_retention_days = 90` |

### 7.2 EU AI Act tier inference

The current heuristic (`_infer_eu_tier`) reads the description for keywords:

- `biometric`, `law enforcement`, `credit scoring` → `high`
- `recommendation`, `content`, `moderation` → `limited`
- `kind ∈ {training, fine_tuning}` → `limited`
- otherwise → `minimal`

This rule set is the v0.1 stub. A milestone-2 expansion will replace it with a structured classifier driven by Annex III categories.

---

## 8. Audit & Replay Model

### 8.1 Storage format

`AuditLog` writes one JSON object per line to `.pgf/audit.jsonl` (configurable via `AuditLog(path=...)`), with the file opened in append-only mode. Each line is `json.dumps(... sort_keys=True)` for canonical byte ordering — important for both diff readability and for milestone-2 PQC signing.

The persisted record includes:

```
{
  "record_id":   "<uuid4 hex>",
  "workload":    {...},
  "decision":    {...},
  "compliance":  {...},
  "grid_snapshot": {...},
  "dc_snapshot":   {...} | null,
  "recorded_at": "<iso8601>"
}
```

### 8.2 Replay semantics

`AuditLog.replay(workload_id) -> list[dict]` returns every record where the embedded workload's id matches, in append order. Because each record carries the snapshots that were visible at decision time, replay is **input-complete**: a third party can reconstruct the input space the scheduler saw and rerun the deterministic decision functions to verify the outcome, without consulting any external system.

This property satisfies the "reproducible decision trail" requirement that EU AI Act facility-tier reporting and US energy-disclosure mandates expect from infrastructure auditability.

### 8.3 Append-only invariant

Test `test_acceptance_audit_is_append_only` asserts that after a second submission, the byte content of the first record's line is unchanged. The interface deliberately exposes no `delete`, `update`, or `compact` method.

### 8.4 Future signing (deferred)

The v0.2 milestone will accept an optional `signer: Callable[[bytes], bytes]` on `AuditLog.append`, producing an ML-DSA signature appended as `signature` field. Existing v0.1 records remain valid; verification of unsigned legacy records is opt-in. The v0.1 interface is shaped so this addition does not break callers.

---

## 9. Control Plane Surfaces

### 9.1 OrchestrationFacade

`facade.submit(raw_request: dict) -> tuple[RoutingDecision, str]`

This is the only function that should be called by surface adapters (REST, CLI, future RPC). It guarantees the five-stage path runs in order and that every successful or blocked decision yields one audit record.

The facade is constructed with explicit dependencies (`ZoneRegistry`, `ScoreWeights`, `AuditLog`, `clock`) — tests freeze the clock to make scenarios deterministic.

### 9.2 REST API

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/v1/health` | Liveness/readiness probe |
| `GET`  | `/v1/zones` | Active zone registry |
| `POST` | `/v1/workloads` | Submit a workload, receive `{decision, audit_record_id}` |
| `GET`  | `/v1/workloads/{id}/audit` | Replay all audit records for a workload id |

Validation errors during classification surface as HTTP 400 with the underlying message in `detail`. Routing failures (no feasible zone) return HTTP 200 with `decision.chosen_zone_id = null` and a populated `blocked_reason`.

### 9.3 CLI

| Subcommand | Action |
|---|---|
| `wattweave zones` | Print the zone registry as JSON |
| `wattweave submit <file>` | Route a single JSON workload, print `{decision, audit_record_id}` |
| `wattweave submit-batch <jsonl>` | Route many workloads, print `{routed, blocked}` summary |
| `wattweave audit <workload_id>` | Print all audit records for an id |

Both surfaces share `OrchestrationFacade`. There is no logic duplicated between them; the CLI cannot compute a different routing decision than the API for the same input.

---

## 10. Determinism and Testing Strategy

### 10.1 Why determinism

Routing decisions feed audit trails that must be reconstructable. If two submissions of the same workload at the same wall-clock time could produce different decisions, the audit would not be replayable.

The MVP achieves determinism via three mechanisms:

1. **Frozen clock injection** — `OrchestrationFacade(clock=lambda: datetime(...))` lets tests pin time.
2. **Hour-bucketed seed** — `grid_telemetry._seed(region, now)` and `dc_telemetry._seed_unit(zone_id, now)` derive their noise from `sha256(f"{key}|{now.replace(minute=0, second=0, microsecond=0).isoformat()}")`, so identical (region, hour) pairs always produce identical snapshots.
3. **Pure decision functions** — `feasible_zones`, `score_zone`, `decide_routing` have no hidden state; given identical inputs they always produce identical outputs.

### 10.2 Test pyramid

| Level | File | Count | Purpose |
|---|---|---|---|
| Unit | `tests/test_units.py` | 24 | One narrow assertion per leaf function (classifier, telemetry, feasibility, scorer, scheduler, tagger). |
| Scenario | `tests/test_scenarios.py` | 5 | End-to-end through `OrchestrationFacade` covering carbon-aware routing, sovereign isolation, realtime protection, blocked-on-infeasibility, and audit replay. |
| Acceptance | `tests/test_acceptance.py` | 5 | DESIGN-stated criteria (weights sum, 5-layer execution, < 50 ms budget, append-only, REST round-trip). |
| **Total** | | **31** | All passing in approximately 0.5–1.0 seconds on a single core. |

### 10.3 The five scenarios in detail

| # | Name | Setup | Asserted behaviour |
|---|---|---|---|
| A | Carbon-aware routing | EU/training/batch + h100 + 400 kWh | Picks `nordic-colo-1` (eu-north) over `eu-west-hyper-1` because eu-north has lower carbon intensity, even though both are EU-compatible. |
| B | Sovereign isolation | EU/inference, any chip | Chosen zone's `sovereign_class == "eu"`, never US. |
| C | Realtime protection | KR/inference/realtime + l4 chip | Chosen zone's type ∈ {`edge`, `smart_city`}. |
| D | Blocked on infeasibility | JP/training/h100 (tokyo-edge has no h100) | `chosen_zone_id = None`, `blocked_reason = "no_feasible_zone"`. |
| E | Audit replay | Two submissions of the same payload at frozen clock | Identical `chosen_zone_id` and identical `score_breakdown`; replay returns one record per workload id. |

---

## 11. AI_ Functions and the Co-evolutionary Property

PG explicitly distinguishes deterministic computation from cognitive boundaries. WattWeaveAI uses this boundary three times:

| Function | File | v0.1 Implementation | Future binding |
|---|---|---|---|
| `AI_infer_sovereign_class` | `sensing/workload_classifier.py` | Keyword-based heuristic over `description` | Replace with a multi-jurisdictional regulatory classifier |
| `AI_estimate_energy_intensity` | `sensing/workload_classifier.py` | Threshold over `kWh / minutes × 60` | Replace with a model trained on historical utilisation telemetry |
| `AI_explain_decision` | `decision/scheduler.py` | Templated string assembled from score breakdown | Replace with an LLM that consults workload context, zone history, and operator policies |

The signatures are the contract. Replacing the body in any of the three does not require any change in callers — this is the **PG Co-evolutionary Property** in concrete form: the design improves as the AI runtime improves, without source-level intervention.

A consequence: tests that depend on `AI_*` outputs use the deterministic stubs deliberately. When LLM bindings land, those tests will be marked as `@pytest.mark.deterministic_stub_only` and a parallel set of contract tests will assert structural properties (length bounds, field presence) rather than exact strings.

---

## 12. Operational Considerations

### 12.1 Configuration

| Knob | Source | Default |
|---|---|---|
| Zone registry | `config/zones.json` (loadable via `ZoneRegistry.from_file(...)`) | 6 seed zones across us-east, eu-west, eu-north, kr-central, jp-east |
| Score weights | `ScoreWeights()` constructor | `(0.25, 0.30, 0.25, 0.20)` summing to 1.0 |
| Audit log path | `AuditLog(path=...)` | `.pgf/audit.jsonl` |
| Clock | `OrchestrationFacade(clock=...)` | `lambda: datetime.now(timezone.utc)` |

### 12.2 Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Invalid request fields | `ClassificationError` raised by classifier | API returns 400 with the message; nothing written to audit log |
| Zone registry missing | `FileNotFoundError` at construction | Facade fails to construct; loud crash, no silent fallback |
| Telemetry snapshot missing for a feasible zone | Detected before scoring | Decision returns `blocked_reason="missing_telemetry"` with the candidates considered |
| Audit log path unwritable | `OSError` on append | Bubbles to caller; v0.1 does not buffer-and-retry |

### 12.3 Performance

A single submission against the seed registry completes in well under 5 ms on commodity hardware. The 50 ms acceptance budget gives headroom for real connector latency. There is no shared mutable state between submissions; horizontal scaling is straightforward.

### 12.4 Observability (current state)

v0.1 emits no metrics. Every submission produces an audit line — that is the operational signal. Milestone 2 will add structured logging (decision latency, blocked-reason histograms, score-axis distribution) and an `OpenTelemetry` exporter.

### 12.5 Security posture (current state)

- No authentication on the REST surface in v0.1 — operator must front it with an authenticating reverse proxy.
- Audit log is append-only at the application layer; tamper resistance is delegated to filesystem ACLs in v0.1 and to PQC signatures in v0.2.
- No secrets are read from the environment; future connector bindings should read region credentials via the platform secret manager.

---

## 13. Extension Points (`ExpansionSocket`)

The DESIGN node `ExpansionSocket` enumerates three reserved children, each corresponding to a future zone class:

```text
ExpansionSocket  // (designing — placeholder, intentionally unimplemented)
    SmartCityHook       // microgrid producer/consumer — v0.3
    SovereignCloudHook  // jurisdiction-aware policy DSL — v0.2/v0.3
    OrbitalHook         // LEO / space-based-solar zone class — v1.0
```

Activating any of these is a matter of:

1. Adding the new `ZoneType` literal in `types.py`.
2. Extending the `_LATENCY_MATRIX` in `scorer.py` with a row for the new type.
3. Adding new entries to `config/zones.json` (or a new file).
4. (Optionally) adding a real connector under `sensing/` if the new class needs telemetry beyond the existing grid+DC pair.

No change is required in `feasibility.py`, `scheduler.py`, `compliance/*`, `control/*`, `audit.py`, or any test that does not specifically assert on the new type. This is the architectural payoff of routing through enumerated types and a single facade.

---

## 14. Roadmap

```
v0.1 (released)        Terrestrial control plane MVP
                        ─ 6 seed zones, mock connectors, REST + CLI
                        ─ 31 tests, 26 acceptance criteria, all passing

v0.2 (planned 2026 Q3) PQC-signed audit (ML-DSA)
                        Real OpenADR grid adapter (per region)
                        Real Kubernetes / chip-operator DC adapter
                        Sovereign policy DSL (YAML-driven, replaces
                          hardcoded EU AI Act inference)
                        Structured logging + OpenTelemetry export
                        First LLM-backed AI_ function (explain_decision)

v0.3 (planned 2027)    SmartCityHook activation
                        ComputeEnergyMarket (capacity bids, carbon arbitrage)
                        Multi-tenant isolation + RBAC
                        Federated control-plane peering (cross-operator)

v1.0 (planned 2028+)   OrbitalHook (LEO + space-based-solar)
                        Insurance / capital-market interfaces
                          (SystemicRiskScore, ComplianceEvidenceLayer)
                        Cross-domain incident propagation modelling
```

Each milestone activates one child of the v0.1 `ExpansionSocket` plus one or two cross-cutting capabilities. The milestone order is constrained by the upstream-bottleneck principle: PQC + real connectors before market features; market features before orbital.

---

## 15. References

| Type | Source |
|---|---|
| Design (canonical) | [`.pgf/DESIGN-WattWeaveAI.md`](../.pgf/DESIGN-WattWeaveAI.md) |
| Pre-implementation review | [`.pgf/REVIEW-WattWeaveAI.md`](../.pgf/REVIEW-WattWeaveAI.md) |
| Execution plan | [`.pgf/WORKPLAN-WattWeaveAI.md`](../.pgf/WORKPLAN-WattWeaveAI.md) |
| Per-node state | [`.pgf/status-WattWeaveAI.json`](../.pgf/status-WattWeaveAI.json) |
| Cross-verification | [`.pgf/VERIFY-WattWeaveAI.md`](../.pgf/VERIFY-WattWeaveAI.md) |
| Final report | [`.pgf/REPORT-WattWeaveAI.md`](../.pgf/REPORT-WattWeaveAI.md) |
| Project README | [`../README.md`](../README.md) |
| PG notation | The PG skill loaded by the project's design tooling |
| PGF lifecycle | The PGF skill (v2.5) used to drive design → review → plan → execute → verify → report |
| Original ideation (archived) | `_legacy/` (8-agent multi-evaluation that selected the EnerGrid AI Fabric concept) |

---

## 16. Appendix A — Acceptance Criteria Index

| ID | Module | Criterion | Test |
|---|---|---|---|
| AC-F-1 | Foundation/types | All dataclasses importable without runtime error | implicit (every test imports) |
| AC-F-2 | Foundation/types | Literal types reused as input validators | `test_classify_rejects_unknown_enum_value` |
| AC-S-1 | Sensing/classifier | Missing fields → reasonable defaults | `test_classify_minimal_input_uses_defaults` |
| AC-S-2 | Sensing/classifier | `estimated_kwh < 0` rejected | `test_classify_rejects_negative_kwh` |
| AC-S-3 | Sensing/classifier | Missing sovereign → AI_infer | `test_AI_infer_sovereign_class_*` |
| AC-S-4 | Sensing/classifier | Missing intensity → AI_estimate | `test_AI_estimate_energy_intensity_*` |
| AC-S-5 | Sensing/grid | Deterministic on (region, hour) | `test_grid_snapshot_deterministic_on_same_inputs` |
| AC-S-6 | Sensing/grid | eu-north baseline carbon < 250 g/kWh | `test_grid_snapshot_eu_north_is_low_carbon` |
| AC-S-7 | Sensing/dc | `chip_available[c] ≤ inventory[c]` | `test_dc_snapshot_chip_available_le_inventory` |
| AC-D-1 | Decision/feasibility | Sovereign mismatch blocked | `test_feasibility_blocks_sovereign_mismatch` |
| AC-D-2 | Decision/feasibility | No chip → blocked | `test_feasibility_blocks_when_chip_unavailable` |
| AC-D-3 | Decision/feasibility | cooling ≥ 0.95 → blocked | `test_feasibility_blocks_when_cooling_saturated` |
| AC-D-4 | Decision/feasibility | Clean zone passes | `test_feasibility_passes_clean_zone` |
| AC-D-5 | Decision/scorer | Sub-scores ∈ [0, 1] | `test_score_subscores_in_unit_interval` |
| AC-D-6 | Decision/scorer | Realtime favours edge over hyperscale | `test_score_realtime_prefers_edge_over_hyperscale` |
| AC-D-7 | Decision/scorer | Carbon penalty when above zone cap | `test_score_carbon_penalty_when_above_zone_cap` |
| AC-D-8 | Decision/scheduler | Blocked when no feasible zone | `test_decide_blocked_when_no_feasible_zone` |
| AC-D-9 | Decision/scheduler | Tie-break = carbon then cost | Scenario A (carbon-aware routing) |
| AC-C-1 | Compliance/tagger | EU + heavy training → carbon reporting | `test_tag_eu_training_requires_carbon_reporting_when_heavy` |
| AC-C-2 | Compliance/tagger | Health → ≥ 7-year retention | `test_tag_health_workload_long_retention` |
| AC-C-3 | Compliance/tagger | Low-intensity inference → no carbon report | `test_tag_low_intensity_inference_no_carbon_report` |
| AC-W-1 | Foundation | Weights sum to 1.0 | `test_acceptance_score_weights_sum_to_one` |
| AC-CP-1 | ControlPlane/facade | submit() exercises all 5 layers | `test_acceptance_facade_exercises_all_five_layers` |
| AC-CP-2 | ControlPlane/facade | Decision < 50 ms | `test_acceptance_decision_under_50ms` |
| AC-CP-3 | Compliance/audit | Append-only | `test_acceptance_audit_is_append_only` |
| AC-CP-4 | ControlPlane/api | REST round-trip works | `test_acceptance_rest_api_round_trip` |

**Total: 26 explicit criteria, 100% covered by the 31-test suite.**

---

## 17. Appendix B — Worked Example

Submission (frozen clock `2026-05-10T13:00Z`):

```json
{
  "workload_id": "demo-1",
  "kind": "training",
  "latency_class": "batch",
  "sovereign_class": "eu",
  "estimated_kwh": 400.0,
  "estimated_minutes": 240,
  "chip_required": "gpu_h100",
  "description": "EU recommendation model fine-tune"
}
```

Pipeline trace:

1. **Classify** → `Workload(kind=training, latency=batch, sovereign=eu, intensity=high (rate ≈ 100 kWh/h, > 20 threshold), chip=gpu_h100)`
2. **Tag** → `ComplianceTag(eu_ai_act_tier=limited, locality=eu, carbon_reporting=true (kWh ≥ 100), retention=90)`
3. **Sense** → grid snapshots for {us-east, eu-west, eu-north, kr-central, jp-east}; DC snapshots for all 6 zones.
4. **Filter** → only EU-class zones with h100 in inventory and cooling < 0.95: `{eu-west-hyper-1, nordic-colo-1}`.
5. **Score**:
   - `eu-west-hyper-1`: composite ≈ 0.853 (decent cost, mid carbon, batch-friendly latency, sovereign match)
   - `nordic-colo-1`: composite ≈ 0.965 (good cost, very low carbon, good latency, sovereign match)
6. **Sort** → `[nordic-colo-1, eu-west-hyper-1]`
7. **Pick** → `nordic-colo-1`
8. **Explain** → "Workload demo-1 (training/batch) routed to zone nordic-colo-1 (colocation, eu-north). Composite score 0.965 [cost=0.96, carbon=0.96, latency=0.95, sovereign=1.00]. Carbon score dominant — routing favors low-intensity grid. Sovereign class 'eu' satisfied by zone class 'eu'. Top alternates: eu-west-hyper-1=0.853."
9. **Record** → one line written to `.pgf/audit.jsonl` bundling all of the above.

This is the canonical Scenario A in the test suite — and the empirical demonstration of the system's central claim: **carbon awareness is structural, not optional.**
