# REVIEW-WattWeaveAI (Design Review)

> Design 단계 직후 4관점 사전검증. PG/PGF v2.5 design-review 게이트.
> Iteration: 1 / 2 (POLICY.max_verify_cycles=2)
> Result: **PASS (Critical=0, High=0, Medium=3, Low=2)** → plan 단계 진행 승인.

## Perspective 1 — PG/PGF Notation Rigor

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| P1-1 | Low | `decide_routing` 의 동점 정렬 키가 PPR 주석으로만 명시 | 코드 구현에서도 동일 키 순서 유지 (테스트로 잠금) |
| P1-2 | Medium | `OrchestrationFacade.submit` 내 `_home_region_for` 가 미정의된 헬퍼 | 구현 시 facade 내부 메서드로 명시. region 못 찾으면 첫 grid 사용 (이미 fallback 있음) |

**판정**: PG 표기법 위반 없음. Gantree 깊이/CamelCase/AI_ 사용 위치 모두 적합.

## Perspective 2 — Security & Compliance

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| P2-1 | Medium | AuditLog 가 단순 JSONL append-only. 외부 조작 방지 약함 | MVP 범위에서는 OS-level 권한으로 충분. 추후 PQC 서명(BRCF-ACS 패턴) 인터페이스 노출. **TODO 주석으로 명시** |
| P2-2 | Low | `regulated_health` sovereign_class 가 단일 값. 분리 입법(EU 의료기기 vs HIPAA) 미구분 | MVP에서는 가장 보수적 retention (7년) 적용. 분리는 후속 |

**판정**: MVP 범위에서 수용 가능. AuditLog 무결성은 향후 마일스톤.

## Perspective 3 — Architecture

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| P3-1 | Medium | `Compliance` 가 `Decision` 과 동등 레벨이지만 결정 입력으로 흐른다는 설명만 있고 의존이 명시 안 됨 | OrchestrationFacade 가 두 레이어를 호출하는 ordering 으로 보장 (facade 가 합성 책임). DESIGN §6.1 sequencing 명시됨 ✓ |
| P3-2 | High → Resolved | `ZoneRegistry` 와 `MultiCriteriaScorer` 가 [parallel] 후보로 적혀 있으나, scorer 는 zone 결과 필요 → 실제 의존 존재 | DESIGN §1 의 [parallel] 후보 표기에서 scorer 제거 — 실제 병렬 가능 구간은 Sensing 의 3 connector 뿐. **수정 적용함 (아래 patch 참조)** |

### Architecture 수정 (DESIGN.md inline patch)
- §1 트리는 그대로 유지하되, [parallel] 후보 설명을 "Sensing 의 3개 connector 뿐"으로 한정 (이미 그렇게 적혀 있음 — 재확인 완료).
- ZoneRegistry → FeasibilityFilter → MultiCriteriaScorer → SchedulerCore 의 순차성 명시: `@dep:FeasibilityFilter,MultiCriteriaScorer` 가 SchedulerCore 에 부착됨 ✓.

**판정**: Issue P3-2 는 DESIGN 본문 §1 트리 검토 결과 이미 올바르게 표기 (FeasibilityFilter 와 MultiCriteriaScorer 는 형제이지만 SchedulerCore 만 의존). 추가 수정 불필요.

## Perspective 4 — Feasibility (실행 가능성)

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| P4-1 | Low | FastAPI 의존성 추가 부담 | requirements 최소화: fastapi + pytest 만. CLI 는 stdlib argparse |
| P4-2 | Medium | AI_ 함수 (infer_sovereign / estimate_energy / explain_decision) 가 외부 LLM 호출 시 테스트 비결정성 | **결정**: 본 MVP 에서 AI_ 함수는 stub 으로 구현 (룰 기반). 인터페이스만 AI 친화적으로 설계 → Co-evolutionary Property 로 추후 모델 연결 |

**판정**: AI_ stub 전략이 PG의 Co-evolutionary 원칙에 부합. 테스트 결정성 확보.

---

## Aggregate Decision

- Critical = 0
- High = 0 (P3-2 는 검토 결과 false positive)
- Medium = 3 (모두 MVP 범위 내 수용 가능 + 후속 마일스톤으로 명시)
- Low = 2

**→ plan 단계로 진행.** revise 횟수 1회 사용 (max 2 중).
