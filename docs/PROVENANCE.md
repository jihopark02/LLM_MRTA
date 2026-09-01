# PROVENANCE.md — 이식 코드 등록부

`/home/jiho/LLM_CBBA`(이하 "이전 저장소")에서 재사용하는 모든 코드/패턴을 여기에 기록한다.
가져올 때마다: 원본 경로, 원본 커밋(가능하면 해시), 무엇을 가져왔는지(패턴 vs 내용), 왜
가져왔는지를 적는다. 연구 계약·task 어휘·domain invariant·prompt·scenario·world·결과값은
절대 이 표에 올리지 않는다(가져오지 않기로 결정했으므로).

## 이식 항목

### 2026-09-01 — CBBA bundle/consensus 코어 + 시간할인 보상 scoring 패턴 (P3)

- 원본:
  - `research/allocation/cbba.py` @ sha256 `7288b440…791c0c` (LLM_CBBA, git 이력 없음, mtime 2026-08-04)
  - `research/allocation/scoring.py` @ sha256 `5d4b0c9c…bf69` (LLM_CBBA, mtime 2026-08-04)
- 종류: 직접 포팅 후 수정
- 이유: CBBA 자체(Choi·Brunet·How 2009의 bundle 구성 + Table I action rule + s-vector
  timestamp + suffix release)는 도메인 무관한 검증된 알고리즘이다. 계약 §11/§14가 명시적으로
  "bundle/consensus/tie-break 핵심과 보상형태" 재사용을 승인. `path_score`의 시간할인 보상
  구조(`Σ λ^completion_time · reward`)도 CBBA 논문 §IV의 DMG 속성에 필요한 표준 형태.
- 수정한 부분:
  - `UAV` → generic `Agent`(§6), `mission.types` → `core/*`.
  - **이동시간을 platform-aware로 새로 작성**(§8): UAV는 Euclidean, UGV는 `RouteGraph`
    Dijkstra 최단경로(`scene.agent_access_nodes` 시작 노드 + incident `access_node`). 원본의
    `math.dist(from,to,3D)/speed` 단일식은 버림.
  - 보상 `10.0 * priority` → `priority`(계약 §11 공식 `Σ priority(task_j)·λ^t` 그대로).
  - `TaskStatus` enum을 이 저장소 것으로 교체, READY frontier를 `TaskGraph`에서 계산.
  - `ConvergenceError` 등 원본 에러 타입 대신 이 저장소 규약.
- 가져오지 않은 부분: `network.py`(통신 outage 모델), `reallocation.py`(RQ3/P8 영역),
  원본 테스트 파일 내용, `bundle_capacity` 기본값 4(계약 §17 — bundle 길이 제약 안 둠),
  원본 SPEC 참조 주석.

## 항목 형식

```
### <날짜> — <가져온 것 한 줄 요약>

- 원본: `research/<path>` @ `<commit-hash>` (LLM_CBBA)
- 종류: 패턴만 / 구조만 / 직접 포팅 후 수정
- 이유: <왜 이걸 재사용하는가 — 알고리즘적으로 도메인 무관함을 설명>
- 수정한 부분: <이식하면서 바꾼 것, 있다면>
- 가져오지 않은 부분: <원본에 있지만 의도적으로 안 가져온 것>
```

## 예정된 이식 후보 (아직 미실행)

- `mission/graph.py`의 TaskGraph 연산 패턴(cycle 검사, predecessor/successor 조회) — 도메인
  무관 자료구조. (P1에서 참고 없이 새로 작성함 — 표준 자료구조라 포팅 불필요로 판단.)
- `execution/sim_executor.py`의 event-loop 구조 — 단, `execution/mission_runner.py`의
  premature-deadlock 버그(§14 RESEARCH_CONTRACT.md 참고)는 패턴만 배우고 고친 형태로 새로
  작성. 옛 코드를 그대로 복사하지 않는다.
- `mission/loader.py`의 environment/reference 분리 원칙(fleet+landmark 어휘만 담는 파일과,
  그 위에 task 인스턴스를 얹는 별도 파일을 분리) — 재현 가능한 오프라인 테스트를 위한 검증된
  설계 패턴.
- `llm/backends.py`의 structured-output 호출 래퍼 — 백엔드 추상화 자체는 도메인 무관.
- 도메인 독립 테스트 유틸리티(mock LLM 응답 주입 패턴 등).

## 명시적으로 가져오지 않는 것

이전 연구 계약(SPEC/CLAUDE/AGENTS/ROADMAP/DECISIONS의 내용), earthquake/vehicle-inspection/
fire-patrol의 task enum, `UAV` 중심 dataclass(PX4 전용 필드 포함), fire-patrol Validator
invariant의 구체적 규칙, 기존 prompt 문구, 기존 scenario/world 파일, 기존 실험 결과값(골든값),
기존 테스트 파일의 내용(교훈만 배우고 새로 작성).
