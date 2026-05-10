# WORKPLAN-WattWeaveAI

> Source: `.pgf/DESIGN-WattWeaveAI.md` (review passed iteration 1/2)
> Format: PGF WORKPLAN — execute order = top-down + @dep respected.

## POLICY

```yaml
project: WattWeaveAI
language: python
runtime: ">=3.10"
deps:
  - fastapi
  - pytest
artifacts_root: .pgf
audit_log_path: .pgf/audit.jsonl
max_verify_cycles: 2
parallelism:
  sensing_connectors: serial   # 본 실행기 한 명. 동시성 가치 < 추적 단순성.
  scoring: serial
failure_strategy:
  on_test_fail: rework_subtree
  on_node_block: report_and_continue
ai_function_strategy: stub_with_rules   # MVP: 결정론적 룰 stub
```

## Execution Order (topological)

```text
W1. Foundation/DomainTypes        (atomic, ≤15min)
W2. Foundation/ConfigLoader       (atomic) [+ default zone fixtures]
W3. Sensing/WorkloadClassifier    (atomic) @dep:W1
W4. Sensing/GridTelemetry         (atomic) @dep:W1
W5. Sensing/DataCenterTelemetry   (atomic) @dep:W1
W6. Decision/ZoneRegistry         (atomic) @dep:W1,W2
W7. Decision/FeasibilityFilter    (atomic) @dep:W1
W8. Decision/MultiCriteriaScorer  (atomic) @dep:W1
W9. Decision/SchedulerCore        (atomic) @dep:W7,W8
W10. Compliance/ComplianceTagger  (atomic) @dep:W1
W11. Compliance/AuditLog          (atomic) @dep:W1
W12. ControlPlane/Facade          (atomic) @dep:W3..W11
W13. ControlPlane/RestApi         (atomic) @dep:W12
W14. ControlPlane/Cli             (atomic) @dep:W12
W15. QualityGate/UnitTests        (atomic) @dep:W3..W11
W16. QualityGate/ScenarioTests    (atomic) @dep:W12
W17. QualityGate/AcceptanceCheck  (atomic) @dep:W15,W16
```

## Per-Node Execution Spec

각 노드는 DESIGN 의 동명 섹션 PPR 을 참조한다. 본 WORKPLAN 은 파일 매핑만 제공.

| Node | Target File(s) |
|------|----------------|
| W1   | `src/wattweave/types.py` |
| W2   | `src/wattweave/config.py` + `config/zones.json` |
| W3   | `src/wattweave/sensing/workload_classifier.py` |
| W4   | `src/wattweave/sensing/grid_telemetry.py` |
| W5   | `src/wattweave/sensing/dc_telemetry.py` |
| W6   | `src/wattweave/decision/zone_registry.py` |
| W7   | `src/wattweave/decision/feasibility.py` |
| W8   | `src/wattweave/decision/scorer.py` |
| W9   | `src/wattweave/decision/scheduler.py` |
| W10  | `src/wattweave/compliance/tagger.py` |
| W11  | `src/wattweave/compliance/audit.py` |
| W12  | `src/wattweave/control/facade.py` |
| W13  | `src/wattweave/control/api.py` |
| W14  | `src/wattweave/control/cli.py` |
| W15  | `tests/test_units.py` |
| W16  | `tests/test_scenarios.py` |
| W17  | `tests/test_acceptance.py` + `.pgf/ACCEPTANCE-WattWeaveAI.md` |

## Acceptance Gate
- 모든 W1..W14 생성 + W15..W17 테스트 통과 시 verify 단계 진입.
