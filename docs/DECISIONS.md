# DECISIONS.md — 설계 결정 이력

Append-only. 과거 항목은 덮어쓰지 않는다. 이 저장소는 `/home/jiho/LLM_CBBA`와 Git 이력을
공유하지 않으므로 D-001부터 새로 시작한다.

## D-001: 연구 계약 확정 (P0)

**배경** 학부 학술대회 발표를 위한 신규 독립 프로젝트. `/home/jiho/LLM_CBBA`의
earthquake/vehicle-inspection/fire-patrol 연구와는 별개이며, 그 저장소의 D-xxx 결정을 근거로
쓰지 않는다. MP4MR(김연주 외, J. ICROS 2025)의 구조를 참고하되 그대로 복제하지 않는다.

**결정** `docs/RESEARCH_CONTRACT.md` v1.0을 단일 진실 원천으로 확정한다. 핵심 요지:

- RQ1(LLM 복합 task graph 생성)/RQ2(이종 UAV/UGV CBBA 할당)만 필수, RQ3(선택적 재할당)는
  P8 후속.
- 핵심 차별점은 CBBA 자체가 아니라 **결정론적 whole-graph Validator**(MP4MR의 LLM Critic
  대체).
- Task 5종(AREA_RECON/THERMAL_RECON/SUPPRESSANT_DROP/GROUND_INSPECTION/
  HAZARD_MARKER_DEPLOY), agent 6대(Scout UAV 2/Response UAV 2/Safety UGV 2) 고정.
- Generic Agent + platform adapter 분리(PX4 전용 필드를 core에 안 둠).
- UAV는 Euclidean, UGV는 route-graph Dijkstra로 이동비용 분리.
- MissionPatch(AddTask/RemoveEdge/AddEdge)를 clone에 적용 후 최종 candidate graph만
  검증·diff 기반 reconciliation·전체 commit-or-rollback.
- CBBA는 rolling READY-frontier epoch 방식.
- 평가는 9개(family당 3개, 확장 시 18개) NL 입력, 사람이 사전 고정한 reference annotation
  대비 task/edge precision·recall.

**근거 — 이 결정에 도달하기까지의 교차검증 이력**: 이 계약은 Claude와 Codex(GPT)가 여러
라운드에 걸쳐 서로의 설계를 검증하며 도달했다. 주요 정정 사항:

1. 최초 제안(LLM_MRTA 초안)은 RQ3(선택적 재할당)를 필수로, agent 6대(UAV+UGV)를 처음부터
   포함했으나, "옛 fire-patrol 프로젝트에서 검증된 것과 검증 안 된 것을 구분하라"는 지적에 따라
   범위를 RQ1/RQ2로 좁히고 RQ3를 후속으로 미룸.
2. "capability 이종성이 선택적 재할당 실험 결과를 강화하지 않는다"는 것을 이전 프로젝트에서
   직접 재현 실험으로 확인함(균일 capability로 바꿔도 reset/위반 패턴이 동일) — 이 사실이
   RQ1/RQ2와 RQ3를 별개 기여로 분리하는 근거가 됨.
3. Validator invariant #10("workflow")과 mission family("aerial-only") 요구사항이 충돌하는
   것처럼 보였으나, invariant 자체가 이미 조건부(downstream 존재 시에만 predecessor 요구)임을
   확인함 — 대신 "구조적으로 유효한 부분 graph"와 "의미적으로 불완전한 graph"를 구별 못 하는
   실제 한계를 찾아, 이를 Validator가 아니라 §12 평가 하네스의 mission profile로 분리하기로
   함.
4. invariant #13("종결 task 불변")이 RQ3의 재배선(완료된 SUPPRESSANT_DROP의 outgoing edge를
   바꿔야 함)과 충돌하는 것을 발견 — "상태·결과·target·incoming은 불변, 아직 RUNNING 아닌
   successor를 향한 outgoing만 같은 atomic patch 안에서 재배선 가능"으로 정교화함.
5. "release를 caller가 명시적으로 호출해야 하는 operation(`ReleaseAssignment`)으로 둘지,
   AddEdge의 즉시 부수효과로 둘지"를 놓고 두 안이 나왔으나, 최종적으로 **최종 candidate graph와
   원본 graph의 diff를 기준으로 한 자동 reconciliation**으로 정함 — "같은 patch에서 추가했다
   다시 제거한 edge가 불필요한 release를 유발한다"는 구체적 반례가 결정적이었음(AddEdge 즉시
   부수효과 방식의 결함).
6. CBBA가 언제 도는지(rolling READY-frontier vs PENDING까지 선점 번들링)가 계약에 빠져있던
   것을 발견해 명시적으로 rolling READY-frontier로 확정.
7. MP4MR 원문(Actor-Critic 구조, task 11종, BP scheduler, ROS2-Gazebo 구조, HILS 미구현·
   후속과제 명시)을 두 차례 직접 재확인해 참고 서술의 정확성을 검증함.

**영향** `/home/jiho/LLM_MRTA`를 독립 Git 저장소로 생성. P1부터 이 계약을 근거로 구현한다.

## D-002: P1 완료 게이트 강화 + reference fixture 고정 형상 (계약 v1.1)

**배경** P1은 semantic scene / `Agent` / `TaskGraph` / route graph / reference fixture를
구현하지만, v1.0의 P1 게이트는 "route graph 도달가능성 전수 검증 + Agent/Task 단위테스트"만
요구했다. 이대로면 `TaskGraph`나 reference fixture가 잘못돼도 P1 통과를 선언할 수 있고,
P2(Validator) 착수 시점에 잘못된 fixture를 근거로 삼게 된다. Codex 검토에서 지적됨.

**결정**

- 계약을 v1.1로 갱신한다.
- §15에 **P1 완료 게이트** 5개 항목을 추가한다: (1) Agent/Task/TaskGraph/RouteGraph
  단위테스트, (2) scene·fixture 로드 성공, (3) fixture가 고정 형상과 일치, (4) 모든
  ID/target/edge 참조 유효 + cycle 없음, (5) route graph 도달가능성 전수 검증.
- §3에 reference fixture 고정 형상을 명시한다: task 12(`AREA_RECON` 4 + workflow 4×2),
  edge 6(3×2), 계산된 초기 READY 6(`AREA_RECON` 4 + `THERMAL_RECON` 2), 초기 PENDING 6.
  이 fixture는 §12 Family A(full-response)에 대응하는 canonical graph다.
- READY/PENDING은 fixture YAML에 적지 않고 graph predecessor 상태에서 계산한다(기존 §7/§9
  원칙 재확인).

**근거** 고정값은 §3 zone 4개 + §4 workflow 4단계 × incident 2개에서 유일하게 유도된다.
게이트가 구현 산출물(fixture 형상)을 직접 검사해야 "구현 범위 전체를 검사하지 않는 게이트"
문제가 사라진다.

**영향** P1 구현 전에 이 문서 커밋을 먼저 한다. 이후 Claude가 P1을 구현하고 커밋 단위로
Codex가 독립 검토한다. 함께 CLAUDE.md에 문서 갱신 트리거와 DECISIONS 기록 범위를 명문화한다
(운영 절차 보강이므로 별도 decision 없이 이 커밋에 포함).

## D-003: compiler 입력 경계 + P1 Codex 검토 반영 (계약 v1.2)

**배경** P1 구현 후 Codex 검토에서 4개 중요 지적:

1. `compile_graph()`가 edge 추가 직후 `recompute_ready()`를 호출해, 존재하지 않는
   predecessor는 KeyError로 종료되고 중복 edge는 set 저장으로 조용히 합쳐졌다. 이 상태로
   같은 compiler를 P5 LLM 출력에 쓰면 P2 Validator가 E_UNKNOWN_REF/E_DUPLICATE_EDGE를
   판정할 기회를 잃는다.
2. `RouteGraph.add_lane()`이 weight를 검증하지 않아 음수·NaN·inf가 통과했다(Dijkstra 전제
   위반).
3. 계약 §3의 incident `RESPONSE_REQUIRED`가 scene 데이터에 없고 주석으로만 존재했다.
4. "str,Enum이 YAML 왕복된다"는 서술이 틀렸다(`yaml.safe_dump`는 RepresenterError).

**결정** 계약을 v1.2로 갱신하고 다음을 확정:

- **compiler 입력 경계**(§7): 결정론적 compiler는 신뢰된 task 목록(손으로 쓴 reference
  fixture, 또는 §12 Validator를 이미 통과한 LLM 출력)만 받는다. 함수명을
  `compile_reference_graph`로 바꾸고, 깨진 신뢰 입력(존재하지 않는 edge 끝점, 중복 edge)에는
  명시적 ValueError를 던진다. raw LLM candidate의 구조 검증은 P2 Validator가 자체 candidate
  표현 위에서 수행한 뒤에만 compile한다.
- **RouteGraph weight**: finite & strictly positive 강제, 단위테스트 추가.
- **incident status**: `IncidentStatus.RESPONSE_REQUIRED`를 core enum으로 추가하고 scene
  YAML 필수 필드로 명시, loader가 검증(§3).
- **enum 직렬화 서술 정정**(§6): 읽기는 커스텀 loader 불필요, 직렬화 경계에서는 `.value`.
- 추가 보강(별도 decision 불필요, 구현 선택): scene loader가 agent `speed`를 finite
  positive로 검증. `Task.duration`도 동일 원칙. 문서 경로 오타(`core/compiler.py` →
  `scenarios/compiler.py`) 수정.

**근거** #1이 P2 Validator의 입력 경계를 결정하므로 P2 착수 전 해결이 필수. Codex가 명시적
반례(unknown predecessor → KeyError, duplicate edge 2개 → 1개만 저장)를 재현해 제시함.

**영향** P1 재검증 대상. 반례 테스트 10개 추가(총 51 passed). P2 착수 시 candidate 표현을
별도로 설계하고, compiler는 검증 통과분만 받는다.

## D-004: scene 로드 검증 보강 + §8 travel_time 예시 정정 (계약 v1.3)

**배경** P1 2차 Codex 검토에서 3개 P1 차단 문제:

1. `load_scene()`이 incident의 `access_node`가 route graph에 존재하는지 검사하지 않는다.
   존재하지 않아도 로드가 성공하고, 나중에 UGV task compile 시 KeyError가 난다. 계약 §8은
   "scene 로드 시점에 UGV 대상 위치가 route graph에 연결" 및 "unreachable이면 로드 거부"를
   규정하는데 그 전제(access_node 존재)가 빠졌다.
2. `load_scene()`의 fleet loader가 중복 `agent_id`를 검사하지 않는다. CBBA에서 agent_id는
   winner/bid/bundle dict의 key이므로 중복 시 한 agent가 조용히 덮어써진다.
3. `pyproject.toml`에 `[build-system]`과 package discovery 설정이 없어 깨끗한 venv에서
   `pip install -e .`가 실패하거나 `UNKNOWN-0.0.0`으로 설치된다.

**결정**

- §8에 scene 로드 시점 검증 4종을 명시하고, `load_scene()`에 (a) incident access_node
  존재, (d) agent_id 유일 검사를 추가한다. 각각 실패 테스트 추가.
- §8 `travel_time` 예시가 `agent.access_node`(존재하지 않는 필드)를 쓰던 것을
  `scene.agent_access_nodes[agent_id]` 기반으로 정정한다.
- `pyproject.toml`에 setuptools build-system과 `[tool.setuptools.packages.find]`
  (`core*`, `scenarios*`; 이후 package가 늘면 확장)을 추가한다.
- 저우선순위: `Task.__post_init__`에 `duration` finite-positive 검사를 추가해 D-003의
  "Task.duration도 finite positive" 서술과 일치시킨다(계약 변경 아님, 구현 선택).

**근거** 세 문제 모두 Codex가 깨끗한 Python 3.10 venv에서 직접 재현. 1·2는 scene 데이터
무결성, 3은 재현성.

**절차 노트**: D-003에서 계약 변경과 코드를 같은 커밋에 넣었다. 이력은 다시 쓰지 않되,
D-004부터 "계약 문서 커밋 → 구현 커밋" 순서를 지킨다.

## D-005: MissionPatch operation 순서 의존성 (계약 v1.4)

**배경** P1 승인 후, Codex가 §10 MissionPatch 계약의 모순을 지적. §10은 "operation 순서와
무관하게 결과가 같고, diff reconciliation이 이를 보장한다"고 적었으나, diff는 (원본 graph,
최종 graph) 두 상태만 비교해 lifecycle 부수효과를 정리할 뿐 **최종 graph 자체의 순서
의존성을 없애지 못한다**.

반례(초기 graph에 A→B 없음):
- `AddEdge(A,B)` 다음 `RemoveEdge(A,B)` → 최종 edge 없음
- `RemoveEdge(A,B)` 다음 `AddEdge(A,B)` → 최종 edge 있음

**결정** 계약을 v1.4로 갱신. §10 처리 절차를 다음으로 교체:

1. clone.
2. **raw operation 목록 self-일관성 검증**(list 위에서, set/graph 진입 전 —
   Codex 지적대로 중복 정보가 사라지기 전에): schema, 같은 task_id AddTask ≥2, 같은 edge
   AddEdge/RemoveEdge ≥2, 같은 edge Add+Remove 동시, 원본에도 AddEdge에도 없는 edge
   RemoveEdge → 전부 `E_PATCH_CONFLICT`.
3. canonical 순서 `AddTask → RemoveEdge → AddEdge`로 적용. 2단계가 self-충돌·중복을
   제거했으므로 최종 graph는 나열 순서와 무관하게 유일 — 순서 독립성은 diff가 아니라 2·3이
   보장한다.
4. 이후는 기존과 동일(whole-graph Validator → predecessor-set diff → reconciliation →
   재검사 → commit/rollback).

**대안 검토** "set 의미론(최종 edge = (원본 ∪ Add) \ Remove)"도 순서 독립적이고 기존
"추가했다 제거" 문장을 살리지만, "patch가 자기모순이면 caller 버그로 거부"가 더 단순하고
방어적이라 판단. §10의 diff-기반 정당화 예시를 "서로 다른 edge를 제거·추가하는 RQ3
재배선"으로 교체(정상 RQ3 재배선은 이 제한에 걸리지 않음).

**저우선순위 유보** CANCELLED predecessor가 successor를 충족시키는지는 계약에 미정의.
현재 `TaskGraph.recompute_ready`는 COMPLETED만 충족으로 취급한다. P1~P3에서 cancellation을
쓰지 않으므로 문제없으나, P4 executor 설계 전에 의미를 확정한다. §10 6단계에 명시.

**영향** P2 구현은 raw `MissionPatch` 표현(list)을 먼저 검증한 뒤 canonical 순서로 적용한다.
`compile_reference_graph`(D-003)와 마찬가지로 "raw candidate/patch는 list로 받아 검증 후에만
graph화"라는 입력 경계 원칙을 따른다.
