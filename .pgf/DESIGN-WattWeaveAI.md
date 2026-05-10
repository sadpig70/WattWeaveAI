# DESIGN-WattWeaveAI

> **Project**: WattWeaveAI (= EnerGrid AI Fabric)
> **Concept**: AI-native compute–energy orchestration platform — treats data-center compute, electricity, cooling, sovereignty, and (later) orbital capacity as one programmable resource fabric.
> **Phase**: MVP (2026 terrestrial control-plane). Orbital extension is a deferred socket, not gating.
> **Source docs**: `docs/system_design.md`, `docs/final_idea.md`, `docs/통합보고서.md`

---

## 0. Design Intent (one paragraph)

WattWeaveAI 는 단일 알고리즘 제품이 아니라 **AI 워크로드를 물리적 자원(전력·냉각·칩·주권 정책)에 정렬시키는 control plane** 이다. MVP는 (1) 워크로드를 분류하고, (2) 전력망/데이터센터 텔레메트리를 신호로 받아, (3) 다목적(비용·탄소·지연·주권) 스코어링으로 라우팅 결정을 내리고, (4) 모든 결정에 규제 메타데이터를 결합하여 감사 가능한 레코드로 영구화한다. 본 설계의 acceptance line 은 **"외부 인프라 mock 만으로 end-to-end 라우팅 결정과 감사 트레일이 재현 가능하다"** 이다.

---

## 1. Top-Level Gantree

```text
WattWeaveAI // EnerGrid AI Fabric MVP control plane (in-progress) @v:0.1
    Foundation // 코어 도메인 모델 + 설정 (designing)
        DomainTypes // workload, zone, telemetry, decision, audit 타입 (designing)
        ConfigLoader // 정책/임계값 로딩 (designing)
    Sensing // 외부 신호 수집 (designing)
        WorkloadClassifier // 워크로드 분류 (designing)
        GridTelemetry // 전력망 신호 (mock connector) (designing)
        DataCenterTelemetry // DC 텔레메트리 (mock connector) (designing) @dep:DomainTypes
    Decision // 라우팅 결정 엔진 (designing) @dep:Sensing
        ZoneRegistry // 후보 존(데이터센터/엣지/주권클라우드) 카탈로그 (designing)
        FeasibilityFilter // 하드 제약(주권·전력 가용·칩 가용) 필터링 (designing)
        MultiCriteriaScorer // 비용·탄소·지연·주권 스코어 (designing)
        SchedulerCore // 최종 배치 결정 + 설명 생성 (designing) @dep:FeasibilityFilter,MultiCriteriaScorer
    Compliance // 규제 메타데이터 + 감사 레이어 (designing)
        ComplianceTagger // 워크로드에 규제 태그 부착 (designing) @dep:DomainTypes
        AuditLog // 결정 영구 저장 (JSONL) (designing) @dep:SchedulerCore
    ControlPlane // 외부 인터페이스 (designing) @dep:Decision,Compliance
        OrchestrationFacade // 단일 진입점: classify→sense→decide→record (designing)
        RestApi // FastAPI 엔드포인트 (designing) @dep:OrchestrationFacade
        Cli // 커맨드라인 인터페이스 (designing) @dep:OrchestrationFacade
    ExpansionSocket // 확장 인터페이스 (placeholder, 구현하지 않음) (designing)
        SmartCityHook // 스마트시티 마이크로그리드 (designing)
        SovereignCloudHook // 주권 클라우드 라우팅 (designing)
        OrbitalHook // LEO/궤도 자원 클래스 (designing)
    QualityGate // 테스트 + 검증 (designing) @dep:ControlPlane
        UnitTests // 레이어별 단위 테스트 (designing)
        ScenarioTests // 5개 시나리오 통합 테스트 (designing)
        AcceptanceCheck // acceptance_criteria 자동 검증 (designing) @dep:UnitTests,ScenarioTests
```

> **Depth check**: 모든 노드 ≤ 3 levels. `(decomposed)` 분리 불필요.
> **Dep cycles**: 위상정렬 가능 — Foundation → Sensing → Decision → Compliance → ControlPlane → QualityGate. ExpansionSocket 은 어디에도 의존 안 됨.
> **Parallel candidates**: `Sensing` 내 3개 노드, `Decision`의 `ZoneRegistry`/`FeasibilityFilter`/`MultiCriteriaScorer` 는 `[parallel]` 가능.

---

## 2. PPR — 도메인 타입 (Foundation/DomainTypes)

```python
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime

# 워크로드: 들어오는 AI 작업 단위
WorkloadKind = Literal["training", "inference", "fine_tuning", "batch_eval"]
LatencyClass = Literal["realtime", "interactive", "batch", "deferred"]
EnergyIntensity = Literal["low", "medium", "high", "extreme"]
SovereignClass = Literal["none", "eu", "us", "kr", "jp", "regulated_health"]

@dataclass
class Workload:
    workload_id: str
    kind: WorkloadKind
    latency_class: LatencyClass
    energy_intensity: EnergyIntensity
    sovereign_class: SovereignClass
    estimated_kwh: float            # 예상 소비 전력
    estimated_minutes: int          # 예상 실행 시간
    chip_required: Literal["gpu_h100", "gpu_a100", "gpu_l4", "cpu", "any"]
    submitted_at: datetime
    # 정성 메타: 자연어 설명. AI_ 함수가 의도 보강 시 사용.
    description: str = ""

# 존: 워크로드를 배치할 후보 위치
ZoneType = Literal["hyperscale", "colocation", "sovereign_cloud", "edge", "smart_city"]

@dataclass
class Zone:
    zone_id: str
    zone_type: ZoneType
    region: str                     # iso country/region code
    sovereign_class: SovereignClass # 이 존이 처리 가능한 sovereign 등급
    chip_inventory: dict[str, int]  # chip_type -> available_count
    cooling_headroom_kw: float
    max_carbon_intensity: float     # gCO2/kWh 상한 (정책)

# 텔레메트리 스냅샷
@dataclass
class GridSnapshot:
    region: str
    timestamp: datetime
    power_price_usd_mwh: float      # 도매 전력 가격
    carbon_intensity_g_kwh: float   # 실시간 탄소 강도
    renewable_surplus_pct: float    # 재생 잉여 비율 [0..100]
    grid_stress_index: float        # [0..1] — 1=혼잡

@dataclass
class DataCenterSnapshot:
    zone_id: str
    timestamp: datetime
    cooling_utilization: float      # [0..1]
    chip_available: dict[str, int]
    rack_density_pct: float

# 결정 + 감사
@dataclass
class RoutingDecision:
    workload_id: str
    chosen_zone_id: Optional[str]   # None = blocked (no feasible zone)
    score_breakdown: dict[str, float]  # cost/carbon/latency/sovereignty 각 점수
    candidates_considered: list[str]
    reason: str                     # AI_explain_decision 출력
    decided_at: datetime
    blocked_reason: Optional[str] = None

@dataclass
class ComplianceTag:
    workload_id: str
    eu_ai_act_tier: Optional[Literal["minimal", "limited", "high", "unacceptable"]]
    data_locality_required: Optional[str]   # iso region
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
```

**acceptance_criteria (Foundation/DomainTypes)**:
- 모든 dataclass 가 import 만으로 사용 가능 (런타임 에러 0)
- Literal 타입은 외부 입력 검증에 재사용 (단일 진실원천)

---

## 3. PPR — Sensing 레이어

### 3.1 WorkloadClassifier

```python
def classify_workload(raw: dict) -> Workload:
    """외부 요청(JSON-like dict) → 정규화된 Workload 인스턴스.

    정밀 분류는 결정론 코드, 모호한 자연어 설명만 AI_ 보강.
    """
    # acceptance_criteria:
    #   - 누락 필드는 합리적 기본값 (e.g., chip_required="any")
    #   - sovereign_class 미지정 시 description 으로 AI_infer_sovereign
    #   - estimated_kwh < 0 거부

    base = _decode_strict_fields(raw)              # 결정론
    if not raw.get("sovereign_class"):
        base["sovereign_class"] = AI_infer_sovereign_class(
            description=raw.get("description", ""),
            kind=base["kind"],
        )
    if not raw.get("energy_intensity"):
        base["energy_intensity"] = AI_estimate_energy_intensity(
            kind=base["kind"],
            estimated_kwh=base["estimated_kwh"],
            estimated_minutes=base["estimated_minutes"],
        )
    return Workload(**base)
```

### 3.2 GridTelemetry (mock connector)

```python
def fetch_grid_snapshot(region: str, now: datetime) -> GridSnapshot:
    """OpenADR/wholesale 시장 API 의 mock.

    실제 배포 시 region 별 어댑터로 대체. MVP 는 결정론적 합성 신호.
    """
    # input: region (iso), now (datetime)
    # process: 시간/지역 기반 합성 곡선 (재생가능 비율은 낮 ↑, 야간 ↓)
    # output: GridSnapshot
    # criteria: power_price >= 0, carbon_intensity ∈ [50, 700], 시드 동일 시 결과 동일
```

### 3.3 DataCenterTelemetry (mock connector)

```python
def fetch_dc_snapshot(zone: Zone, now: datetime) -> DataCenterSnapshot:
    """DC BMS/Kubernetes 메트릭 mock. 칩 가용성 = inventory 에서 무작위 차감(시드 고정)."""
    # criteria:
    #   - chip_available[k] ≤ zone.chip_inventory[k] 항상 성립
    #   - cooling_utilization ∈ [0, 1]
```

**acceptance_criteria (Sensing)**:
- 모든 외부 호출은 mock; 결과는 (region, now)에 대해 결정론적
- 동일 입력 → 동일 출력 (테스트 가능성)

---

## 4. PPR — Decision 레이어

### 4.1 ZoneRegistry

```python
def load_zone_registry(config_path: Path) -> list[Zone]:
    """YAML/JSON config 로 정의된 후보 존 목록 로드. MVP는 6개 fixture zone."""
```

### 4.2 FeasibilityFilter

```python
def feasible_zones(workload: Workload, zones: list[Zone],
                   dc_snapshots: dict[str, DataCenterSnapshot]) -> list[Zone]:
    """하드 제약 통과 존만 반환.

    결정론 — AI_ 미사용. 빠르고 설명 가능해야 함.
    """
    # acceptance_criteria:
    #   - sovereign_class 가 zone.sovereign_class 와 호환되는 존만
    #   - 요구 칩이 dc_snapshot.chip_available 에 존재
    #   - cooling_utilization < 0.95
    #   - 빈 결과 허용 (호출부가 blocked 처리)

    out = []
    for z in zones:
        if not _sovereign_compatible(workload.sovereign_class, z.sovereign_class):
            continue
        snap = dc_snapshots.get(z.zone_id)
        if snap is None or snap.cooling_utilization >= 0.95:
            continue
        if workload.chip_required != "any":
            if snap.chip_available.get(workload.chip_required, 0) < 1:
                continue
        out.append(z)
    return out
```

### 4.3 MultiCriteriaScorer

```python
@dataclass
class ScoreWeights:
    cost: float      = 0.25
    carbon: float    = 0.30
    latency: float   = 0.25
    sovereign: float = 0.20

def score_zone(workload: Workload, zone: Zone,
               grid: GridSnapshot, dc: DataCenterSnapshot,
               weights: ScoreWeights) -> dict[str, float]:
    """존별 4-축 정규화 점수 [0..1]. 1=좋음.

    결정론 + 보조 AI_make_balance 로 가중치 컨텍스트 적응.
    """
    cost_score      = _normalize_cost(grid.power_price_usd_mwh, workload.estimated_kwh)
    carbon_score    = _normalize_carbon(grid.carbon_intensity_g_kwh, zone.max_carbon_intensity)
    latency_score   = _latency_match(workload.latency_class, zone.zone_type)
    sovereign_score = _sovereign_match(workload.sovereign_class, zone.sovereign_class)

    # acceptance_criteria:
    #   - 각 sub-score ∈ [0, 1]
    #   - 가중치 합계 = 1
    #   - latency_class=realtime 일 때 latency_score 가 결정 지배

    composite = (cost_score * weights.cost + carbon_score * weights.carbon
                 + latency_score * weights.latency + sovereign_score * weights.sovereign)
    return {
        "cost": cost_score, "carbon": carbon_score,
        "latency": latency_score, "sovereign": sovereign_score,
        "composite": composite,
    }
```

### 4.4 SchedulerCore — 최종 결정

```python
def decide_routing(workload: Workload, zones: list[Zone],
                   grid_snapshots: dict[str, GridSnapshot],
                   dc_snapshots: dict[str, DataCenterSnapshot],
                   weights: ScoreWeights) -> RoutingDecision:
    """1) feasibility 필터 → 2) 다축 점수 → 3) 최고 composite 선택 → 4) 자연어 reason."""
    # acceptance_criteria:
    #   - feasible 0개 → chosen_zone_id=None, blocked_reason 명시
    #   - 동점 처리: 탄소 점수 우선 (창발성 강점 #4 반영)
    #   - reason 은 사람이 읽을 수 있어야 함 (AI_explain_decision)

    feasible = feasible_zones(workload, zones, dc_snapshots)
    if not feasible:
        return RoutingDecision(
            workload_id=workload.workload_id, chosen_zone_id=None,
            score_breakdown={}, candidates_considered=[z.zone_id for z in zones],
            reason="No feasible zone (sovereign/chip/cooling 제약 모두 통과 실패).",
            decided_at=now(),
            blocked_reason="no_feasible_zone",
        )

    scored = [
        (z, score_zone(workload, z, grid_snapshots[z.region],
                       dc_snapshots[z.zone_id], weights))
        for z in feasible
    ]
    # 동점 시 carbon 우선, 그 다음 cost
    scored.sort(key=lambda t: (t[1]["composite"], t[1]["carbon"], t[1]["cost"]),
                reverse=True)
    best_zone, best_scores = scored[0]

    reason = AI_explain_decision(workload, best_zone, best_scores,
                                 alternatives=[(z.zone_id, s["composite"])
                                               for z, s in scored[1:3]])
    return RoutingDecision(
        workload_id=workload.workload_id, chosen_zone_id=best_zone.zone_id,
        score_breakdown=best_scores,
        candidates_considered=[z.zone_id for z, _ in scored],
        reason=reason, decided_at=now(),
    )
```

**acceptance_criteria (Decision)**:
- realtime workload 가 batch 친화 zone 으로 가지 않음
- carbon_intensity 가 zone.max_carbon_intensity 초과 region → 점수 패널티 작동
- 모든 결정은 50ms 이내 반환 (mock 기준; AI_ 호출은 stub)

---

## 5. PPR — Compliance 레이어

### 5.1 ComplianceTagger

```python
def tag_compliance(workload: Workload) -> ComplianceTag:
    """sovereign_class + kind → 규제 태그. 결정론 매핑.

    결정 라우팅과 분리 — Compliance 가 결정 후 태그를 입히는 게 아니라,
    결정 입력으로 함께 흐른다 (creative emergence #4 — 메타데이터가 워크로드와 동행).
    """
    # acceptance_criteria:
    #   - sovereign_class="eu" 이면 data_locality_required ∈ {EU 회원국 코드}
    #   - kind="training" 이고 estimated_kwh ≥ 100 이면 carbon_reporting_required=True
    #   - regulated_health → audit_retention_days ≥ 365 * 7
```

### 5.2 AuditLog

```python
class AuditLog:
    """JSONL append-only. 1 record per routing decision.

    핵심 속성: 결정 시점에 보았던 모든 신호(grid/dc snapshot)를 함께 영구화.
    이는 EU AI Act / 에너지 보고 mandate 의 '재현 가능한 결정 트레일' 요건을 만족.
    """
    def __init__(self, path: Path): ...
    def append(self, record: AuditRecord) -> None: ...
    def replay(self, workload_id: str) -> list[AuditRecord]: ...
```

**acceptance_criteria (Compliance)**:
- 한번 기록된 레코드는 변경 불가 (append-only)
- replay(id) 가 동일 결정/스코어를 재구성할 수 있음 (snapshot 동봉으로 자명)

---

## 6. PPR — ControlPlane

### 6.1 OrchestrationFacade

```python
class OrchestrationFacade:
    """단일 진입점. classify → tag → sense → decide → record."""

    def __init__(self, zones, weights, audit_log, clock=now): ...

    def submit(self, raw_request: dict) -> RoutingDecision:
        # acceptance_criteria:
        #   - 5단계 모두 호출됨 (감사 가능성)
        #   - 어떤 단계 실패해도 부분 AuditRecord 남김
        wl       = classify_workload(raw_request)
        tag      = tag_compliance(wl)
        regions  = {z.region for z in self.zones}
        grids    = {r: fetch_grid_snapshot(r, self.clock()) for r in regions}
        dcs      = {z.zone_id: fetch_dc_snapshot(z, self.clock()) for z in self.zones}
        decision = decide_routing(wl, self.zones, grids, dcs, self.weights)
        rec = AuditRecord(
            record_id=_uuid(), workload=wl, decision=decision, compliance=tag,
            grid_snapshot=grids[(self._home_region_for(decision, self.zones)
                                 or next(iter(grids)))],
            dc_snapshot=dcs.get(decision.chosen_zone_id) if decision.chosen_zone_id else None,
            recorded_at=self.clock(),
        )
        self.audit.append(rec)
        return decision
```

### 6.2 RestApi (FastAPI)

```python
# POST /v1/workloads        → 새 워크로드 제출, RoutingDecision 반환
# GET  /v1/workloads/{id}/audit → AuditRecord 리스트
# GET  /v1/zones            → 현재 레지스트리
# GET  /v1/health           → liveness/readiness
```

### 6.3 Cli

```python
# wattweave submit <json-file>      → 한 건 라우팅
# wattweave submit-batch <jsonl>    → 다건 라우팅 + 요약 통계
# wattweave audit <workload-id>     → 감사 기록 출력
# wattweave zones                   → 후보 존 표
```

**acceptance_criteria (ControlPlane)**:
- API 와 CLI 모두 동일 facade 사용 (구현 1, 인터페이스 N — DRY)
- API 200 응답에는 항상 `decision` + `audit_record_id` 포함

---

## 7. PPR — QualityGate

### 7.1 UnitTests
- 각 함수 (`classify_workload`, `feasible_zones`, `score_zone`, `decide_routing`, `tag_compliance`, `AuditLog`) → 입력/경계/실패 케이스

### 7.2 ScenarioTests (5개 — final_idea/통합보고서의 강점·시나리오 반영)

```python
# Scenario A: 데이터센터 에너지 최적화
#   - 동일 워크로드, 다른 region grid → 탄소 낮은 region 선택

# Scenario B: 주권 컴퓨트 라우팅
#   - sovereign_class="eu" → US-only zone 자동 제외

# Scenario C: realtime latency 보호
#   - latency_class="realtime" 워크로드는 batch zone 선택 안 함

# Scenario D: feasibility 0 → blocked
#   - 모든 zone 칩 부족 → chosen=None, blocked_reason 채워짐

# Scenario E: 감사 재현
#   - 동일 워크로드 2회 제출 + 동일 시각/시드 → 동일 결정 + 동일 audit replay
```

### 7.3 AcceptanceCheck

```python
def acceptance_check() -> dict:
    """모든 acceptance_criteria 를 코드로 자동 평가. report.md 에 표로 출력."""
```

**acceptance_criteria (QualityGate)**:
- 모든 단위 테스트 통과
- 5개 시나리오 모두 통과
- AcceptanceCheck 가 `passed=True` 반환

---

## 8. POLICY (실행 정책 기본값)

```yaml
max_verify_cycles: 2
parallelism:
  sensing_layer: parallel
  scoring: parallel
failure_strategy:
  on_node_block: report_and_continue   # blocked 노드는 보고하고 잔여 진행
  on_test_fail: rework_subtree         # 해당 노드 재실행, 최대 2회
verify_perspectives:
  - acceptance
  - quality
  - architecture
artifacts_root: .pgf
audit_log_path: .pgf/audit.jsonl
```

---

## 9. Self-Review Checklist (PG/PGF)

- [x] 모든 노드 ≤ 5 levels (실제 ≤ 3)
- [x] 모든 노드에 status 명시
- [x] 원자 노드 = 15분룰 통과 (모든 leaf 가 단일 함수 단위)
- [x] CamelCase 노드명
- [x] @dep: 의존성 명시 (순환 없음)
- [x] [parallel] 후보 식별
- [x] 복잡 노드 PPR def 작성 (Decision/Compliance/ControlPlane)
- [x] 정확성 필요 곳에 AI_ 미사용 (스코어링/필터링은 결정론)
- [x] AI_ 함수는 모호 영역만 (sovereign 추론, energy_intensity 추정, 결정 설명)
- [x] acceptance_criteria 모든 큰 모듈에 부착
