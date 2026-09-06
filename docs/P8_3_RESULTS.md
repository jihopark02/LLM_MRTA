# P8.3 Operator UI 검증 결과

검증일: 2026-09-06  
브랜치: `feature/operator-interaction`  
계약: v1.32 / D-034  
Validator: 1.4

## 범위

P8.3은 연구 성능 평가가 아니라 운용자 상호작용 경로의 구현 게이트다. 확인한 경로는 다음과 같다.

```text
운용자 발화
→ LLM intent wire output
→ strict OperatorIntent
→ 결정론적 grounding / clarification / MissionPatch
→ plan-time CBBA
→ 결정론적 실행 버튼 / SimExecutor
→ 단일 순서형 감사 event stream
```

12-dialogue 정량 평가는 P8.4 범위다. 따라서 아래 3턴 성공을 intent 정확도나 일반화 성능으로
주장하지 않는다.

## 자동 검증

- 전체 pytest: 593 passed
- ruff: clean
- Streamlit `AppTest`: 초기 화면 → mock 임무 생성 → 모호한 incident 후보 표시 → 구조화된
  `FIRE_SITE_1` 선택 → 실행 버튼 → `EXECUTED` 전환 → 감사 JSON 생성
- 실행 action: `COMPLETED` / `DEADLOCK` / `STEP_LIMIT` / 예외, 실패 뒤 동일 graph 재시도,
  원본 graph·scene·plan 불변
- 감사 순서: `t1 → t2 → EXECUTION → t3`, `event_seq`는 직렬화 시 0부터 파생
- cached backend: 모델·prompt/schema version·context hash·user payload 중 하나라도 다르면
  cache miss, cached 응답은 항상 `mode=cached`

## 실제 API 3턴

요청 모델 `gpt-5-mini`, 실제 응답 모델 `gpt-5-mini-2025-08-07`. 총 5회 호출(intent 3회 +
첫 NEW_MISSION의 task/edge 생성 2회)이 모두 같은 snapshot으로 기록됐다.

| turn | 운용자 발화 요약 | intent | 결과 |
|---|---|---|---|
| t1 | 전체 구역 정찰 + 기존 두 화재 지상 진압까지 | `NEW_MISSION` | COMMITTED, 12 tasks / 6 edges |
| t2 | A 구역 신규 화재 보고 | `REPORT_INCIDENT` | COMMITTED, `FIRE_SITE_3` 등록 |
| t3 | “거기”를 지상 진압까지 추가 | `UPDATE_MISSION` | COMMITTED, 신규 chain 4 tasks / 3 edges |

최종 16 tasks / 9 edges를 실행한 결과:

- termination: `COMPLETED`
- makespan: 404.0321 s
- capability violations: 0
- precedence violations: 0
- audit: TURN 3개 뒤 EXECUTION 1개, `turn_count=3`

동일한 새 세션을 만들고 같은 3턴을 `CachedBackend`로 재생했을 때 세 턴 모두 COMMITTED,
실행 결과와 makespan도 동일했다. 로컬 원본 감사 파일과 응답 cache는 각각
`data/interaction_runs/`, `data/llm_cache/`에 생성되며 `.gitignore` 대상이다.

## 실제 API에서 발견해 수정한 결함

최초 live 시도는 내부 `IntentEnvelope`가 생성한 중첩 JSON Schema `oneOf`를 OpenAI structured
output이 거부해 세 턴 모두 HTTP 400 `TURN_ERROR`로 끝났다. state는 생성되지 않았다. D-034는
API 전용 평면 `IntentWireEnvelope`를 추가하고, 엄격한 kind/slot 검사 후 기존 discriminated
union으로 결정론적으로 변환하도록 수정했다. mock만으로는 찾을 수 없었던 통합 배선 결함이다.

## UI 표시 범위

`demo/app.py`는 계약 §18.12의 14항목을 표시한다: 대화, scene, TaskGraph, intent/slot,
grounding, patch diff/NO_CHANGE, Validator 판정, CBBA 할당/makespan, 이전 계획 대비 assignment
변화, phase, 실행 버튼, ExecutionResult, live/cached/mock 배너, clarification 후보/취소 및
pending 중 입력·실행 비활성화. graph/경로의 시각적 폴리싱은 P8.5 범위다.
