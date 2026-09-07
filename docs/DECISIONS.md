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

## D-006: reconciliation release 경로의 도달성 (계약 v1.5)

**배경** P2 구현 중 확인: 고정 5종 task 어휘 + 엄격한 §9 #10("downstream 존재 시 정확히
canonical predecessor 1개") 하에서는 어떤 **유효한** patch도 기존 task의 predecessor 집합을
바꿀 수 없다. workflow task는 canonical predecessor edge를 제거하면 즉시 E_WORKFLOW가 되고,
다른 predecessor를 추가해도 E_WORKFLOW다. AREA_RECON은 edge를 가질 수 없다. RemoveTask
operation은 없다. 따라서 P2의 유효 graph에서 patch가 할 수 있는 것은 "AREA_RECON 추가"와
"incident chain을 canonical하게 연장"뿐이다.

**결정** §10 6단계의 reconciliation release 로직(ASSIGNED→PENDING + assignment/bundle/
winning-bid 제거, E_RUNNING_LOCKED, terminal outgoing 재배선 허용)을 P2에서 **구현하고
단위테스트**하되, end-to-end(apply_patch 경유)로는 RQ3(P8)가 recheck 계열 task를 도입하기
전까지 도달하지 않음을 계약 §10에 명시한다. §9 #13의 terminal **incoming** 불변은 P2에서
도달 가능하며 end-to-end 테스트한다.

**근거** reconciliation을 P8로 미루면 §10이 반쪽만 구현되고, P8에서 계약을 개정하며 다시
설계해야 한다. 지금 구현해 두면 P8은 task 어휘 확장 + precondition만 다루면 된다. 도달성
한계를 명시하지 않으면 "P2 gate의 reconciliation 테스트"가 무엇을 의미하는지 모호하다.

**영향** P2 gate의 "MissionPatch reconciliation" 항목은 (a) op-list 검증 + canonical 적용 +
whole-graph 재검증 + 트랜잭션 = end-to-end 테스트, (b) predecessor-diff + release +
E_RUNNING_LOCKED = 단위테스트로 충족된다. `validator/patch_apply.py`에 도달성 note를 남김.

## D-007: P2 Codex 2차 검토 반영 (계약 v1.6)

**배경** P2 구현 후 2차 Codex 검토에서 테스트가 못 잡은 결함 3 + 보강 2:

1. `pyproject.toml` package discovery에 `validator*`가 없어 설치 패키지에서 누락(테스트는
   루트 pythonpath라 은폐).
2. `validate_patch_ops`가 operation의 **클래스 종류만** 확인하고 필드는 안 봄:
   `AddTask("NOT_A_TYPE", ...)` → E_SCHEMA 아닌 KeyError crash, `priority=True` → 승인,
   숫자 target → 후속 E_UNKNOWN_REF. 런타임 입력 경계가 fail-closed가 아님.
3. `graph_hash`가 node를 `(task_type, target)`로만 해시 — priority가 다른 두 임무가 같은
   graph_hash. priority는 P3 CBBA 실행 입력이므로 서로 다른 임무를 같은 graph로 감사 기록.
4. `_assignment_invariant_errors`가 `assigned_agent is not None`만 검사 — 존재하지 않는
   agent, owner 불일치, 중복 bundle, stale bundle/bid를 빈 patch가 통과.
5. `MissionCandidate.from_raw`가 알 수 없는 키를 조용히 버림 — LLM이 `assigned_agent`를
   출력해도 통과. 계약 §7("LLM은 task_type/target/priority만") 미강제.

**결정** 계약을 v1.6으로 갱신:

- §10에 **assignment consistency invariant**(§10 7단계) 5개 규칙 명시 — assigned_agent가
  fleet에 존재, ASSIGNED/RUNNING ⟺ assigned_agent 설정, ASSIGNED/RUNNING은 정확히 한
  agent의 bundle∪path에 있고 그게 owner, 비활성 task는 bundle/path/winning_bids에 없음.
  bundle/path 세부 관계(순서, bundle⊆path, current_task)는 P3에서 확정. 위반 시 `E_SCHEMA`.
- §7에 schema 검증이 허용 키를 정확히 제한함을 명시(top-level `{tasks, edges}`, task entry
  `{task_type, target, priority}`, 그 외 키는 `E_SCHEMA`).
- graph_hash payload의 node는 `(task_type, target, priority)`. candidate/patch 양쪽이 같은
  canonical 함수를 쓰고, task 순서 불변·priority 변화 시 해시 변화 회귀 테스트 추가.
- `validate_patch_ops`가 operation 필드를 런타임 검증(TaskType 실체, target str,
  priority int∧¬bool, edge endpoint (TaskType,str), operations가 list). 검증 안 된 op의
  `.key`/`.edge`에 접근 금지.
- `pyproject.toml` include에 `validator*` 추가, 프로젝트 밖 설치 import 확인.

**영향** P2 재검증 대상. D-006의 private reconciliation 단위테스트 방식은 P8 어휘 확장 시
반드시 public `apply_patch()` end-to-end 테스트로 교체(Codex 조건부 수용).

## D-008: P2 Codex 3차 검토 반영 (계약 v1.7)

**배경** D-007 반영 후 3차 검토에서 추가 확인:

1. `build/lib/**` 20개 파일이 3af6e29에 커밋됨(wheel 검증 산출물을 `git add -A`가 포함).
   소스와 갈라지면 패키징 오염. → build hygiene, 계약 무관.
2. D-007이 판정 규칙을 바꿨는데(unknown field 거부, op field schema, assignment invariant
   강화, hash 형식) `VALIDATOR_VERSION`이 "1.0" 그대로. 같은 버전에서 동일 입력의 판정이
   달라질 수 있어 §14 재현성과 충돌.
3. `_assignment_invariant_errors`가 `state.graph.tasks`만 순회 →
   `S1.bundle = ["GHOST_TASK"]`, `winning_bids = {"GHOST_TASK": 3.0}` 같은 dangling
   참조가 빈 patch를 통과. D-007 규칙 1~4는 "graph에 존재하는 task" 방향만 검사, 역방향
   참조 무결성 누락.
4. priority가 임의 정수 허용(`-10`, `0`, `10**100` 전부 accepted). 코드 버그는 아니나
   P3 CBBA 보상 함수에서 음수 priority가 음수 bid·미할당 유발 가능.
5. (저) rejected `PatchResult.graph_hash`가 빈 문자열 — §14 "최소 graph_hash 기록"과
   형식상 충돌. malformed op는 최종 graph가 없으므로 정리 필요.

**결정** 계약 v1.7:

- **VALIDATOR_VERSION "1.0" → "1.1"**. §14에 bump 규칙 명시(판정 규칙 변경 시 필수, 같은
  버전에서 동일 입력의 accepted/error_codes 불변). 테스트는 버전 literal을 확인.
- **priority 1..10 고정**(§7). candidate schema와 patch op schema가 범위를 `E_SCHEMA`로
  강제. 현재 시나리오가 3/7/9를 쓰므로 1..10이 자연스럽다.
- **assignment 참조 무결성**(§10 규칙 6): 모든 bundle/path/winning_bids 참조가 graph에
  존재하는 task를 가리키고, `state.agents` dict key가 `Agent.agent_id`와 일치. 위반 시
  `E_SCHEMA`.
- **rejected patch graph_hash 범위**(§14): whole-graph 단계 이전 거부는 `graph_hash` 빈
  문자열, `scene_hash`+`validator_version`+`error_codes`가 감사 기록. `patch_hash`(raw op
  해시) 도입은 P5 전 정리 대상.
- build hygiene: 추적 중인 `build/` 제거, `.gitignore`에 `build/` `dist/` 추가.

**영향** P2 재검증. P3 착수 전 priority 범위가 계약에 고정됨 — CBBA 보상 함수는 1..10만
가정하면 된다.

## D-009: P3 platform-aware CBBA 구체화 (계약 v1.8)

**배경** P3(§11 CBBA + §8 platform-aware travel) 구현. §11이 abstract하게만 두었던
상수·형태를 확정한다.

**결정**

- **이식**: LLM_CBBA `research/allocation/{cbba,scoring}.py`의 CBBA 코어(bundle 구성 +
  Table I action rule + s-vector + suffix release)와 시간할인 보상 구조를 포팅. sha256로
  PROVENANCE.md에 pin.
- **λ = 0.999** 고정(이전 저장소 `DEFAULT_LAMBDA` 재사용). 모든 조건 동일.
- **보상 = `priority`** (스케일 없음). §11 공식이 `Σ priority·λ^t`이므로 이전 저장소의
  `10·priority`는 안 씀. argmax는 불변이나 `winning_bids` 크기가 달라짐.
- **이동비용은 새로 작성**(포팅 아님, §8): UAV Euclidean, UGV는 `RouteGraph` Dijkstra
  (`scene.agent_access_nodes` 시작 + incident `access_node`). `allocation/travel.py`.
- **tie-break**: `_beats()` — 정확히 같은 bid이면 `agent_id` 사전순 작은 쪽 승. 없으면 동일
  agent 두 대가 tie를 못 깨고 무한 leave. `_action_rule`의 4개 bid 비교에 적용.
- **bundle 무제한**: `capacity` 기본값 = frontier 크기(§17 — Phase 1 bundle 길이 제약 없음).
- **rolling frontier**: `allocation/allocate.py`가 clone 위에서 epoch 반복 —
  `recompute_ready` → frontier auction → plan-time 시뮬(agent 위치·task 완료시각 전진) →
  frontier task를 COMPLETED로 표시 → 반복. 이건 평가용 계획 시뮬레이션이며, 실제 실행은
  P4 executor가 담당한다.
- **§13 지표**: `AllocationResult`에 allocation_success, unassigned, capability/precedence
  violation, uav_flight_distance/ugv_route_distance, estimated_makespan, workload,
  agent_utilization, idle_agents, epoch별 consensus rounds.

**P3 게이트 결과**: reference fixture 12 task 전부 할당, capability/precedence violation 0,
UGV 이동거리가 route-graph Dijkstra 합과 일치(Euclidean과 불일치), 재실행 결정성. 4 epoch
(AREA_RECON×4+THERMAL_RECON×2 → SUPPRESSANT_DROP×2 → GROUND_INSPECTION×2 →
HAZARD_MARKER_DEPLOY×2), 모든 agent 활용(idle 0), Response UAV가 두 drop 모두 수행.

**영향** 다음은 P4(2D executor, end-to-end). executor는 `run_epoch`를 재사용하고 `allocate`의
plan-time 시뮬 대신 실제 이벤트 루프로 frontier를 굴린다.

## D-010: P3 Codex 검토 반영 — plan-time schedule 모델 (계약 v1.9)

**배경** P3 구현 후 Codex 검토에서:

1. `allocation*`가 `pyproject.toml` discovery에 없음 — 설치 wheel에서 `import allocation` 실패
   (루트 pythonpath 테스트는 통과하므로 은폐).
2. `allocate._walk`가 `clock += travel` 다음에 `pred_ready`를 보므로, successor가 아직
   PENDING인데도 agent가 목적지로 **미리 이동한 것으로 계산**된다. reference fixture에서
   `SUPPRESSANT_DROP_F1` 시작이 49.17s(THERMAL_RECON_F1 완료 시각)로 나오는데, R1의 이동
   21.91s가 predecessor 실행 중 소진됨 — 정상은 71.08s. 기존 테스트는
   `pred_completion <= succ_start`만 봐서 두 값이 같으면 통과(travel gap 소멸).
3. utilization의 `busy = end - agent_free_at`가 predecessor 대기시간까지 포함 —
   `busy/makespan` 정의와 불일치.
4. tie-break: 계약 §11은 "정확히 같은 bid"라고 했으나 코드는 `EPSILON=1e-9` 이내를 동점
   처리. `_beats(1.0,"A", 1.0+5e-10,"B") → True`(A가 더 낮은데 승).
5. frontier stall 미감지 — winner 0이어도 같은 frontier를 `max_epochs`까지 재경매.
6. §10 rule 5가 "bundle/path 관계는 P3에서 확정"이라 했으나 D-009에 미정.

**결정** 계약 v1.9:

- **plan-time topological-wave barrier**(§13): epoch 1 시작 0, 각 epoch frontier 계획 실행,
  epoch 종료 시각 = 그 wave의 최대 completion, 다음 epoch agent 출발 = `max(agent_free_at,
  epoch_start)`, 그다음 travel → task_start → dwell. **barrier 이전 이동 금지.** 이 방식이
  "4 frontier wave" 설명을 유지하면서 시간 역전을 제거한다. makespan·utilization 골든값이
  바뀐다(예상: reference fixture makespan 156.7 → 더 큰 값).
- **utilization busy = travel + dwell만**. 대기시간은 제외(makespan − busy − 종료후여유).
- **tie-break 허용오차**(§11): `|Δbid| ≤ 1e-9`를 동점으로 명시 — 코드 `EPSILON`과 일치.
  부동소수점 안정성 때문에 정확 상등을 안 쓴다.
- **bundle/path postcondition**(§11, §10 rule 5): bundle=획득순서, path=실행순서, 수렴 후
  동일 task 집합(중복 없음), 각 task는 winner 한 명의 bundle/path에만, plan-time
  `current_task=None`, 계획 기준은 `AllocationResult.assignments`. **CBBA postcondition으로
  정의**(Validator invariant 아님) → `VALIDATOR_VERSION` bump 불필요.
- **stall guard**: `run_epoch` 결과 winner가 0이면 즉시 중단.
- `pyproject.toml`에 `allocation*` 추가, 격리 디렉터리 import 검증.
- PROVENANCE.md의 sha256을 전체 값으로 기록(축약 금지).

**영향** P3 재검증. makespan/utilization 관련 값이 바뀌므로 P3 게이트 테스트도 갱신. P4
executor는 이 barrier 모델이 아니라 실제 이벤트 루프를 쓴다(D-009 영향 유지).

## D-011: P4 2D executor (계약 v1.10)

**배경** P4(§15) — 2D discrete-event executor로 reference mission을 end-to-end 실행.

**결정** `execution/executor.py`의 `SimExecutor`:

- **event loop**: `recompute_ready` → READY frontier auction(`run_epoch`) → dispatch(agent
  가 path[0]의 predecessor가 모두 COMPLETED면 이동 시작, `travel = leg_distance/speed`) →
  advance(가장 이른 완료 시각으로 시계 전진, task COMPLETED, agent 위치 갱신) → 반복. task
  완료는 위치 도달 + dwell만(§3).
- **held carry-forward**(§11): 새 epoch는 미완료 할당을 `held={task: (winner, bid)}`로
  넘겨 재경매하지 않는다. 없으면 staggered readiness 때문에 매 epoch 빈 bundle 재경매 →
  한 agent가 연달아 이기고 동종 agent가 유휴. `allocation/cbba.py`의
  `CBBAState.initialize`/`run_epoch`에 `held` 파라미터 추가. reference mission workload가
  균형(S1/S2 3, R1/R2 1, G1/G2 2)이 되고 idle 0.
- **projected-position bidding**: RUNNING task가 있는 agent는 그 task 도착 지점을 기준으로
  입찰(임시로 position 이동 → 경매 후 복원). RUNNING task는 경매 후 path[0]에 다시 pin.
- **deadlock 판정**(§14): "아무도 작업 중 아니고 dispatch 불가" 직전에 `recompute_ready`를
  한 번 더 호출하고 epoch 재시도, 그래도 진전 없으면 `deadlocked=True` + 미완료 task 반환,
  종료(무한 루프 없음). agent.bundle/path는 완료 시 executor가 제거.
- **§13 지표**: `ExecutionResult`에 completed, assignments, task_start/completion,
  consensus_rounds, epochs, makespan, capability/precedence violations, uav/ugv 이동거리,
  workload, agent_utilization(busy = travel+dwell / makespan), idle_agents, deadlocked.
- executor는 `state.clone()` 위에서 동작 — 호출자 state 불변.

**P4 게이트 결과**: reference mission 12/12 완주, capability/precedence violation 0,
deadlock 아님, 재실행 결정성. 최소 재현 테스트(단일 agent R1, THERMAL_RECON→SUPPRESSANT_DROP
체인 — false deadlock 없이 완주). 부분 진전 후 실제 deadlock(예: Response UAV 없음 →
SUPPRESSANT_DROP 영구 미배치)도 종료·보고.

**영향** RQ1/RQ2 필수 범위의 실행 파이프라인 완성(P1~P4). 다음은 P5(LLM Step1/Step2/repair
mock 테스트). P7 Gazebo executor는 이 executor와 동일 route semantics를 공유해야 한다(§8).

## D-012: P4 Codex 검토 반영 (계약 v1.11)

**배경** P4 구현 후 Codex 검토에서 정상 fixture가 못 잡은 3 + 4:

1. **실행 중 agent의 신규 task 입찰 오류**: RUNNING task가 residual path에 남아 이동·dwell·
   reward가 이중 계산됨. 재현: R1(현재 task 완료 위치 = 신규 task 위치)이 R2(70m 떨어짐)에게
   짐 — 정상은 R1 승(9.7043 > 9.6077). CBBA 할당 결과 자체가 바뀜.
2. **완주 후 MissionState invariant 위반**: COMPLETED 시 `task.assigned_agent`를 안 지워
   §10 assignment invariant가 12개 에러("non-active task still assigned"). `agent.current_task`도
   dispatch/completion 어디서도 갱신 안 됨.
3. **`execution*`가 `pyproject.toml` discovery에 없음** — P3 allocation과 같은 결함.
4. **`max_steps` 소진을 deadlock으로 오판**: `max_steps=1`도 `deadlocked=True`. §13 deadlock
   집계에 거짓 실패 혼입.
5. precedence 테스트가 travel gap을 검사 안 함(`succ_start >= pred_completion`만).
6. CANCELLED predecessor 의미가 v1.4에서 "P4 결정"으로 유보됐는데 D-011/구현에서도 미확정.
7. PROVENANCE가 executor를 "예정된 이식 후보"로 표시 — 실제 상태 모호.

**결정** 계약 v1.11:

- **residual-path 입찰**(§14): RUNNING task는 그 agent의 residual path에서 임시 제거하고
  도착 지점으로 위치 투영, 경매 후 실제 path 선두에 재병합. 재현 사례를 회귀 테스트로 추가.
- **assignment 정리**(§14, §10): COMPLETED 시 `assigned_agent=None`, `current_task=None`,
  bundle/path 제거. dispatch 시 `current_task=task_id`. 완주 후
  `_assignment_invariant_errors(executor.work) == []` 직접 검증.
- **`pyproject.toml`에 `execution*` 추가**, wheel 격리 import 검증.
- **종료 사유**(§14): `ExecutionResult.termination` ∈ {`COMPLETED`, `DEADLOCK`, `STEP_LIMIT`}.
  `deadlocked` = `termination == DEADLOCK`. `STEP_LIMIT`은 deadlock 아님.
- **precedence 테스트 강화**: `task_departure`(agent 이동 시작 시각)를 결과에 기록하고
  `task_departure[succ] >= task_completion[pred]`를 검증(서로 다른 위치 synthetic chain).
- **cancellation**(§10): P1~P7 미지원, P8 유보. CANCELLED predecessor 있으면 successor는
  blocked → deadlock 보고가 의도된 의미.
- **PROVENANCE**: executor를 "참고하지 않고 신규 작성"으로 후보에서 제외(§14가 옛 코드
  복사 금지를 명시).

**영향** P4 재검증. #1은 CBBA 할당 결과를 바꾼다. (residual-path만 고친 중간 상태에서는
workload가 쏠렸으나, D-013의 availability-aware 수정 후 다시 균형이 됨 — 아래 참조.)

## D-013: P4 Codex 재검토 — availability-aware residual bidding (계약 v1.12)

**배경** D-012 반영 후 재검토에서 residual-path 입찰의 시간 모델 결함:

1. **RUNNING agent의 남은 가용시간이 입찰에서 누락**: residual-path 수정이 이중 계산은 없앴지만
   agent가 완료 위치에 도달할 때까지의 시간도 사라져, 실행 중 agent가 "지금 즉시 그 위치에서
   시작 가능"으로 계산됨. 재현: R1(신규 task 위치에서 1000초 후 가용) vs R2(70m, 즉시) →
   현재 R1 낙찰(9.7043 > 9.6077), 정상은 R2(9.6077 > 3.5682). reference mission의 workload
   집중도 일부는 이 누락 때문 — GROUND_INSPECTION_F2에서 G2(41초 대기 + 48초 이동 = 89초) vs
   G1(즉시, 70초)이면 G1이 더 빠름.
2. **residual regression 테스트가 실제 executor를 안 거침**: `run_epoch`를 직접 호출하고 R1을
   빈 path로 목적지에 놓아서, path 제거·투영·재병합·가용시간 중 아무것도 검사 안 함.
3. **마지막 step 완주가 `STEP_LIMIT`으로 반환**: loop 시작에서만 완주 확인 →
   `max_steps=2`에서 완료했는데 `unfinished == [] && termination == STEP_LIMIT` 모순.
4. **precedence violation 지표가 arrival(`task_start`) 사용**: successor가 predecessor 완료
   전에 출발해도 도착만 나중이면 violation 0. departure 기준이어야 함.

**결정** 계약 v1.12:

- **availability-aware residual bidding**(§11): `path_score`/`marginal_score`/`run_epoch`에
  `start_delay`/`start_delays` 추가. executor는 `availability_delay = max(0, finish_at − now)`를
  전달, 위치는 착지 지점 투영. P3 `allocate`는 delay 0.
- **마지막 step COMPLETED**(§14): `run()` loop 종료 후 최종 상태로 재판정 —
  모든 task terminal이면 `COMPLETED`.
- **precedence violation = departure 기준**(§14): `task_completion[p] > task_departure[s]`.
- **residual regression 테스트**: 실제 `SimExecutor._run_epoch()`를 R1 mid-task 상태
  (`sim.current`, `path=[running]`, `finish_at > now`)로 통과시키고, 남은 시간 짧을 때 R1
  승 / 길 때 R2 승 두 경우 검증.

**결과** availability-aware 후 reference mission executor workload가 다시 균형
(S1/S2 3, R1/R2 1, G1/G2 2, idle 0). **D-012의 "집중이 정상 greedy CBBA"는 철회** — 집중은
가용시간 누락 버그 때문이었다. makespan 232.9, capability/precedence violation 0.

**영향** P4 재검증. `allocate`(P3)는 `start_delays` 미전달로 불변.

## D-014: STEP_LIMIT 실행의 지표 (계약 v1.13, 비차단)

**배경** P4 승인 후 Codex가 발견: busy time을 dispatch 시점에 예정 travel+dwell 전체로
더하므로, 실행 중 task가 남은 채 `STEP_LIMIT`으로 끝나면 `agent_utilization`이 1을 넘는다
(미래 busy가 분자, 완료 시각까지만 분모). `COMPLETED`/`DEADLOCK`에는 실행 중 agent가 없어
정상이고 P4 게이트에 영향 없음.

**결정** `STEP_LIMIT` 실행의 `makespan`/`agent_utilization`은 평가 지표로 쓰지 않는다.
`_result`가 `STEP_LIMIT`이면 `agent_utilization`을 빈 dict로 반환한다(§14). 테스트에 명시.
연구 결과에는 `STEP_LIMIT` 실행을 포함하지 않는다.

## D-015: patch_hash를 P8로 유보 (계약 v1.14)

**배경** §14에 `patch_hash`(raw MissionPatch operation 해시) 도입이 "P5 전 정리 대상"으로
남아 있었다. P5 candidate 검증 경로는 `MissionCandidate`만 쓰고 `MissionPatch`는 쓰지
않으며, MissionPatch는 RQ3(P8)에서 실제로 사용된다(D-006).

**결정** `patch_hash` 도입 여부·형식은 **P8 문서 개정 시 확정**한다. P5는 이것 없이 진행한다.
§14 문구를 "P5 전"에서 "P8로 유보"로 수정.

**미확정으로 남긴 것 (P5 착수 전 사용자 결정 필요)**: HAZARD_MARKER_DEPLOY를 유지할지
GROUND_SUPPRESSION 중심 workflow로 바꿀지. → D-016에서 결정됨.

## D-016: task 어휘 변경 — HAZARD_MARKER_DEPLOY → GROUND_SUPPRESSION (계약 v1.15)

**배경** P5 착수 전 사용자가 UGV 지상 진압 중심 workflow로 방향을 정함(D-015에서 유보했던
결정). 사용자 응답: (a) GROUND_SUPPRESSION이 HAZARD_MARKER_DEPLOY만 교체, (b) Safety UGV
capability를 `MARKER_DISPENSER` → `SUPPRESSANT_APPLICATOR` 교체, (c) §2 차별점은 Validator +
CBBA 축 유지.

**결정 — 이 항목이 D-001~D-015의 관련 부분을 supersede한다** (DECISIONS는 append-only이므로
과거 항목은 그대로 두되, 아래가 우선):

- `TaskType.HAZARD_MARKER_DEPLOY` → `GROUND_SUPPRESSION`. 의미: Ground Response UGV가
  GROUND_INSPECTION 완료 후 incident 접근 지점에서 수행하는 **symbolic** 진압 task. 위치 도달
  + dwell로만 완료 판정; 물리적 소화 성공·소화 소요시간을 산출하거나 주장하지 않는다.
- workflow 체인: `THERMAL_RECON → SUPPRESSANT_DROP → GROUND_INSPECTION → GROUND_SUPPRESSION`.
- `Capability.MARKER_DISPENSER` → `SUPPRESSANT_APPLICATOR`. Ground Response UGV(G1/G2) =
  `GROUND_MOBILITY` + `SUPPRESSANT_APPLICATOR`. `GROUND_SUPPRESSION` required_capabilities =
  두 capability 모두. eligible bidder 2(G1/G2).
- 문서 명칭 "Safety UGV" → "Ground Response UGV". agent ID `G1`/`G2` 유지.
- `VALIDATOR_VERSION` **1.1 → 1.2** — 허용 TaskType 집합과 §9 #10 workflow invariant의 판정
  의미가 바뀜(§14 bump 규칙).
- reference fixture: `GROUND_SUPPRESSION`의 priority는 incident priority를 따른다 —
  FIRE_SITE_1 = 9, FIRE_SITE_2 = 7 (기존 marker의 6/5 아님). duration은 `TASK_TABLE`에
  하나로 고정된 symbolic scenario parameter.
- §2에서 "UGV FIRE_SUPPRESS는 그대로 복제하지 않는다"를 삭제하고, GROUND_SUPPRESSION이
  symbolic이며 독창성 주장은 Validator+CBBA 축에 둔다는 문단을 추가.
- §3 fixture 형상, §4 vocabulary·workflow, §5 agent·bidder, §7 required_capabilities 예시,
  §9 #12 scope, §15 P1 게이트 5번을 GROUND_SUPPRESSION 기준으로 개정.

**골든값 재산출 결과** (GROUND_SUPPRESSION duration = 45.0 symbolic, priority F1 9 / F2 7):

- **P3 `allocate`**: allocation_success, capability/precedence violation 0. makespan ≈ 359.8
  (barrier 상한, 이전 334.8 → +25 = duration 20→45 차이). workload S1/S2 3, R1/R2 1, G1/G2 2,
  idle 0. consensus rounds [8, 4, 4, 4]. uav_flight ≈ 999.5, ugv_route ≈ 346.3.
- **P4 `SimExecutor`**: termination COMPLETED, 12/12, capability/precedence violation 0. makespan
  ≈ 257.9 (이전 232.9). workload S1/S2 3, R1/R2 1, G1/G2 2, idle 0. epochs 7,
  consensus rounds [8, 4, 3, 3, 3, 3, 3].
- assignment 구조는 어휘 변경 전과 동일(GROUND_SUPPRESSION이 각 incident의 GROUND_INSPECTION
  담당 UGV에 배정: F1→G2, F2→G1). 균형 workload는 값 역조정 없이 그대로 나온 결과다.

**작업 순서**: 계약 커밋 → enum/capability/compiler/scene/fixture/Validator → VALIDATOR_VERSION
1.2 → 테스트·현재 문서 참조 수정 → P1~P4 전체 실행 → 새 P3/P4 결과 기록 → README/CLAUDE →
현재 파일(코드·계약·테스트) 옛 어휘 잔존 검색(0이어야 함; DECISIONS D-001~D-015 과거 기록은
제외).

## D-017: P5 LLM 파이프라인 (계약 v1.16)

**배경** P5(§12) — 자연어 명령을 검증된 task graph로 바꾸는 파이프라인. 검증·컴파일
구성요소(P2 `MissionCandidate`/`validate_candidate`, `compile_reference_graph`)는 이미 있어,
P5는 LLM 호출 추상화 + orchestration이다.

**결정**

- `llm/schemas.py`: pydantic 구조화 출력 — `Step1Output`(tasks: task_type/target/priority),
  `Step2Output`(edges: "TYPE:target" 끝점), `RepairOutput`(tasks+edges). LLM은 좌표·
  capability·duration·task_id를 생성하지 않는다(§7).
- `llm/backend.py`: `LLMBackend` Protocol(`complete(system, user, schema) -> BaseModel`).
  `AnthropicBackend` — Anthropic SDK `client.messages.parse`, 기본 모델 `claude-opus-5`
  (계약이 모델을 pin하지 않음; Anthropic 스킬 기본값). `anthropic` import는 지연 로딩, `llm`
  optional dependency. `MockBackend(scripted)` — 스크립트 응답을 순서대로 반환, 스킬 부족 시
  AssertionError.
- `llm/prompts.py`: scene 어휘(zones/incidents/task types/workflow)를 주입한 Step1/Step2/
  repair 시스템 프롬프트.
- `llm/pipeline.py` `generate_mission(command, scene, backend) -> GenerationResult`:
  Step1 → `from_raw` schema 검증(오류 시 **즉시** 명시적 거부, SCHEMA) → Step2 →
  `validate_candidate`(whole-graph) → 통과면 승인 + `compile_reference_graph`로 실행 graph.
  실패면 구조화 오류를 넣어 repair 1회 → 재검증 → 승인 또는 명시적 거부. reference로 조용히
  fallback하지 않는다.
- `GenerationResult`: `approved`, `attempts`(1|2), `repaired`, `schema_valid`,
  `raw_whole_graph_valid`, `repaired_whole_graph_valid`, `failure_category`
  ∈ {SCHEMA, WORKFLOW, STRUCTURE, REFERENCE, FEASIBILITY, OTHER}, `errors`, `candidate`,
  `validation`, `graph`. §12 지표(schema-valid count / raw·repair 후 whole-graph-valid /
  failure category)를 이 필드들로 집계한다.
- `pydantic>=2`를 주 의존성으로 추가, `anthropic>=0.40`을 `llm` extra로, `llm*`를 package
  discovery에 추가.

**PROVENANCE** LLM_CBBA `llm/backends.py`의 백엔드 추상화 **패턴만** 참고(OpenAI 코드·
파일 캐시·dotenv·`mission_generator.py`는 미포팅). PROVENANCE.md에 기록.

**게이트** `tests/test_llm_pipeline.py` 7개 — 첫 시도 승인(부분 graph + full workflow),
workflow 오류 repair 후 승인, repair 후에도 실패 → 명시적 거부(graph None), 알 수 없는
task type → SCHEMA 거부, cross-incident 거부, backend 소진 시 AssertionError. 총 185 tests.

**영향** 다음은 P6(최소 9개 입력 평가 + 결과 시각화). MockBackend에 사람이 사전 고정한
reference annotation을 주입해 §12 precision/recall을 측정한다. 실제 LLM 평가는 API 키가
있을 때 `AnthropicBackend`로 별도 수행.

## D-018: 실제 LLM backend는 OpenAI (계약 v1.17)

**배경** D-017은 provider 미지정 상태에서 `AnthropicBackend`(`claude-opus-5`)를 기본값으로
넣었다. 사용자가 OpenAI API 키를 보유. Claude Code 구독은 프로그램에서 Messages API를
호출할 수 없다(별도 `ANTHROPIC_API_KEY` 필요).

**결정 — D-017의 backend 선택을 supersede**:

- `llm/backend.py`의 `AnthropicBackend` → `OpenAIBackend` (`from openai import OpenAI`,
  `client.chat.completions.parse(response_format=<pydantic schema>)`, `OPENAI_API_KEY`·
  선택적 `OPENAI_BASE_URL` 환경변수, `temperature` 기본 0.0·`None`이면 생략).
- `pyproject.toml` `llm` extra: `anthropic` → `openai>=1.40`.
- `DEFAULT_MODEL = "gpt-5-mini"` — override 가능한 기본값. P6 실험은 모델을 **하나로
  고정**해 §14 재현성 기록에 포함한다(모델 문자열도 결과 표에).
- `LLMBackend` Protocol과 `MockBackend`, `llm/pipeline.py`, `llm/schemas.py`,
  `llm/prompts.py`는 변경 없음 — backend만 교체.

**PROVENANCE** LLM_CBBA `llm/backends.py`가 원래 OpenAI 기반이므로, 이번엔 그 구조에 더
가깝다(단, 파일 캐시·dotenv·`mission_generator.py`는 여전히 미포팅). PROVENANCE.md 갱신.

**영향** P5 게이트는 backend 무관(MockBackend) — 185 tests 그대로. P6에서 `OpenAIBackend`로
실제 9개 입력 평가. Claude Code 구독 ≠ Anthropic API라는 점을 사용자와 확인함.

## D-019: P5 Codex 검토 반영 — 순서·schema 엄격성·raw 보존 (계약 v1.18)

**배경** P5 승인 검토에서 3개 차단 + raw/final 보존 문제:

1. **Step 1 검증 전에 Step 2를 호출**: 계약은 "Step 1 → schema validation → Step 2" 순서를
   요구하는데 `pipeline.py`는 Step 1 직후 Step 2를 부르고 81행에서야 후보를 검증했다.
   `WATER_LOAD` 같은 금지 task가 Step 1에 나와도 Step 2가 호출됨을 재현.
2. **pydantic schema가 금지 필드를 버리고 타입을 교정**: 기본 설정이라
   `position`(task 추가 필드), top-level `notes`, `priority="3"`(str→int 강제),
   `priority=True`, edge의 `reason` 추가 필드가 전부 조용히 통과했다. "허용 키·타입을
   정확히 제한하고 그 외엔 E_SCHEMA"라는 계약과 충돌.
3. **pydantic validation 실패가 예외로 파이프라인을 탈출**: `backend.py`/`pipeline.py`에
   `model_validate()` 실패를 잡는 처리가 없어 `pydantic.ValidationError`가 그대로
   전파되고 `GenerationResult(failure_category="SCHEMA")`가 아니라 평가 실행 자체가
   중단됨을 재현.
4. **raw/repaired 미분리**: repair가 성공하면 최초 후보와 최초 Validator 오류가
   사라져 "raw output과 validated output 비교"(§16)를 재구성할 수 없었다.

**결정** 계약 v1.18:

- **순서 강제**(§12): `generate_mission`이 Step 1 출력을 `MissionCandidate.from_raw`(edges
  없이) + `consistency_errors()`로 먼저 schema 검증하고, 통과해야만 Step 2를 호출한다.
  실패 시 즉시 `SCHEMA` 거부 — Step 2 backend 호출은 발생하지 않는다. mock 테스트가
  backend 호출 횟수(정확히 1)로 이를 검증한다.
- **schema 엄격화**(`llm/schemas.py`): 모든 모델에
  `model_config = ConfigDict(extra="forbid", strict=True)`. 추가 필드·문자열/bool priority가
  전부 `pydantic.ValidationError`로 거부됨을 확인(재현 케이스 5종 회귀 테스트).
- **backend 예외 → 명시적 거부**(`llm/pipeline.py`): 각 backend 호출을 `_call()` 헬퍼로
  감싸 `pydantic.ValidationError`만 잡아 `GenerationResult(approved=False,
  failure_category="SCHEMA")`로 변환한다. 그 외 예외(네트워크·인증·`MockBackend` 소진의
  `AssertionError`)는 그대로 전파 — SCHEMA로 뭉뚱그리지 않는다.
- **raw/final 분리 보존**(`GenerationResult`): `raw_candidate`/`raw_validation`(Step 1+2
  직후, repair 이전)과 `candidate`/`validation`(최종)을 항상 함께 갖는다.
  `raw_schema_valid`/`raw_whole_graph_valid`는 raw 기준 고정. `repaired_schema_valid`/
  `repaired_whole_graph_valid`는 repair를 실제로 시도했을 때만 bool이고, 시도 안 했으면
  `None`(이전에는 repair가 schema에서 또 실패하면 최초 성공 여부까지 덮어썼음).

**비차단(같이 처리)**:
- `OpenAIBackend`에 `client` 주입 지점 추가 — `openai` 미설치·네트워크 없이 fake client로
  모델명·`response_format`·messages·`temperature` 생략을 테스트.
- `completion.model`(실제 resolved snapshot, 예: `gpt-5-mini-2025-08-07`)을
  `OpenAIBackend.resolved_models`에 기록 — alias(`gpt-5-mini`)가 가리키는 실제 스냅샷을
  결과와 함께 남겨 재현성을 보강한다(§14).
- repair 테스트가 repair prompt에 실제로 `E_WORKFLOW`와 원본 graph 내용이 들어갔는지
  assertion 추가.
- `.env` 권한을 `600`으로(다른 사용자가 읽지 못하게).

**영향** P5 재검증 대상. `tests/test_llm_pipeline.py` 13개(+6) +
`tests/test_openai_backend.py` 5개(신규) = 196 tests 전체 통과.

## D-020: prompt task glossary + P5 사소 보강 (계약 v1.19)

**배경** P5 승인 후 Codex 권고. prompt의 scene facts가 task_type 이름·target 종류만
전달하고 각 task의 의미·담당 platform 설명이 없어, `GROUND_INSPECTION`(점검)과
`GROUND_SUPPRESSION`(진압)처럼 이름이 비슷한 task를 LLM이 영어 의미로 추측해야 했다.
P6 실제 평가 전에 고치지 않으면 결과가 "임무 분해 능력"이 아니라 "task 이름 추측 능력"을
잴 위험이 있음.

**결정**

- `llm/prompts.py`에 5종 task type의 **의미 + 담당 platform** glossary를 scene facts에
  추가(§12). Step1/Step2/repair 프롬프트 전부에 포함.
- (사소, 같이 처리) `OpenAIBackend`가 client를 호출마다 새로 만들던 것을 **한 번 생성해
  재사용**하도록 수정.
- (사소) repair 자체가 pydantic schema 오류를 내는 경로에 회귀 테스트 추가(이미 코드는
  정상이었음, Codex가 직접 재현해 확인).
- P6 착수 시 참고: `OpenAIBackend.resolved_models`(실제 completion.model)를 **명령별·
  호출별로 결과에 연결해 저장**해야 한다(alias `gpt-5-mini`가 가리키는 실제 snapshot 추적,
  §14). 평가 하네스 설계 시 반영.

**영향** `tests/test_prompts.py` 신규(2), `tests/test_openai_backend.py` +1(client 재사용),
`tests/test_llm_pipeline.py` +1(repair 자체 schema 실패). 200 tests 전체 통과.

## D-021: P6 평가 하네스 설계 + 9개 명령 고정 (계약 v1.20)

**배경** P5 승인 후 P6(최소 9개 입력 평가 + 시각화) 착수. 계약 §12는 평가 지표 목록과
"LLM 출력을 보기 전에 사람이 canonical reference annotation을 고정한다"는 요구만 있고,
파일 형식·명령 문구·비교 규칙·집계 방식이 미정이었다. 하네스 코드를 짜기 전에, 그리고
LLM을 처음 호출하기 전에 이걸 고정해야 순서가 git 이력으로 증명된다.

**결정** 계약 v1.20:

- **reference annotation 파일**: `data/reference_annotations/<id>.yaml`. 필드 `id`, `family`
  (A/B/C), `profile`(FULL_RESPONSE/AERIAL_ONLY/SELECTIVE_RESPONSE), `command`(평가에 그대로
  들어갈 NL 문구), `rationale`(정답을 이렇게 고정한 근거), `allowed_graphs`(허용 정답 목록;
  대부분 1개). 각 graph는 shorthand `recon_zones: [ZONE_...]` +
  `incident_chains: {FIRE_SITE_x: [<§4 workflow의 연속 prefix>]}`로 적고, 로더가 chain을
  task 목록 + 순차 edge로 전개한다(prefix가 아니면 로드 에러).
- **비교 규칙**: `task_key = (task_type, target)` — priority 제외(§7에서 incident로부터 결정,
  task_key 동일성엔 무관). `edge_key = (pred_task_key, succ_task_key)`. 예측 graph를
  `allowed_graphs` 각각과 대조해 (task F1, edge F1) 사전식 최대인 graph 하나를 골라 그에 대한
  precision/recall/exact match를 보고한다.
- **raw·final 둘 다 측정**: `GenerationResult.raw_candidate`와 최종 `candidate` 각각.
  candidate가 없으면(SCHEMA 실패) 그 축의 precision/recall은 N/A(평균 분모에서 제외).
- **집계**(`X/9` 원시 개수): schema-valid, raw whole-graph-valid, repair 후 whole-graph-valid,
  approved. task/edge precision·recall은 candidate 있는 case 평균 + micro 분자/분모. exact
  graph match count. failure_category 히스토그램. latency(벽시계 초) min/mean/max. family
  (A/B/C)별 분해.
- **재현성**(§14): 결과 JSON에 `scene_hash`, `validator_version`, backend 종류, 명령별
  `resolved_models`(OpenAIBackend면 실제 `completion.model` 목록).
- 실제 평가는 `OpenAIBackend(model="gpt-5-mini")`. 하네스 self-test는 `MockBackend`.

**9개 명령**(LLM 호출 전 고정 — 파일이 이 커밋에 포함됨):

| id | family | profile | 요지 |
|----|--------|---------|------|
| A1 | A | FULL_RESPONSE | 양쪽 화재 전체 4단계 chain + 전 zone 항공 정찰 |
| A2 | A | FULL_RESPONSE | 같은 내용, 단계 이름을 명시적으로 나열 |
| A3 | A | FULL_RESPONSE | 같은 내용, 구어체 "다 처리해" |
| B1 | B | AERIAL_ONLY | 전 zone 항공 정찰 + 양쪽 화재 thermal recon, 진압·지상 금지 |
| B2 | B | AERIAL_ONLY | 같은 내용, "하늘에서 눈만" |
| B3 | B | AERIAL_ONLY | 같은 내용, "정찰 단계만" |
| C1 | C | SELECTIVE_RESPONSE | F1 전체 chain + F2 thermal recon만 + 전 zone 정찰 |
| C2 | C | SELECTIVE_RESPONSE | F2 전체 chain + F1 thermal recon만 + 전 zone 정찰 |
| C3 | C | SELECTIVE_RESPONSE | F1 전체 chain + F2 thermal recon만, zone 정찰 생략 |

family A의 canonical reference는 P1 `scenarios/reference_fixture.yaml`(12 task/6 edge)와 동일.

**영향** 신규 `data/reference_annotations/{A1..C3}.yaml`(9), `evaluation/` 패키지
(`annotations.py`, `metrics.py`, `harness.py`, `report.py`), `tests/test_evaluation.py`.
`pyproject.toml` packages.find에 `evaluation*` 추가.
## D-022: priority를 LLM 출력에서 제거, 결정론적 파생 + P6 감사 보강 (계약 v1.21)

**배경** P6 Codex 검토에서 승인 보류. 8개 지적 중 3개 차단:

1. **priority를 "생성"한다면서 평가에서 완전히 제외.** 계약 §1 RQ1은 priority 포함 graph
   생성을 평가한다고 했는데 P6 `task_key`는 `(task_type, target)`뿐 — priority가 전부 틀려도
   exact match. 게다가 내부 기준이 불일치: prompt는 "incident task는 incident priority"라고
   지시하지만 P1 fixture의 GROUND_INSPECTION은 8/6(incident는 9/7), AREA_RECON은 fixture
   4/5/3/4 · annotation 5로 임의. "9/9 exact match"가 priority 정확도를 전혀 증명 못 함.
2. **결과 JSON에 실제 LLM 후보 graph와 Validator 감사 기록이 없음.** `CaseResult`가 점수만
   저장하고 raw/final 후보·validation을 버림. 제3자가 9/9를 독립 재계산 불가인데
   `P6_RESULTS.md`는 이를 "원자료"라 부름.
3. **"14개 invariant 만족"은 사실과 다름.** #13~#14는 MissionPatch 전용(`whole_graph.py`),
   candidate 경로는 #1~#12만.

비차단 5개: repair 0/9가 실패처럼 보임(attempted vs recovered), family B edge P/R 1.00은
빈 집합 관례, annotation 명시형 schema가 `int()` 강제 변환(P5에서 고친 문제 재발),
`_N=9` 하드코딩, 하네스 예외가 `failure_category`와 섞임.

**결정** priority 정책 = **Option A**(LLM 출력에서 제거, 결정론적 파생):

- **schema**(`llm/schemas.py`): `LLMTask`는 `{task_type, target}`. `to_candidate_dict`도
  priority 없음. candidate schema(`validator/candidate.py`)의 task entry 허용 키는
  `{task_type, target}` — `priority`가 있으면 `E_SCHEMA`. `CandidateTask`는 priority 필드
  제거(구조 뷰).
- **파생**(`scenarios/compiler.py`): `derive_priority(scene, task_type, target)` —
  incident target → `scene.incidents[target].priority`(9/7), AREA_RECON → 상수
  `AREA_RECON_PRIORITY = 4`(zone은 심각도 없어 균일, 두 incident보다 낮음).
  `compile_reference_graph`는 `(task_type, target)` 2-tuple 목록을 받아 내부에서 파생.
  `compile_task`는 저수준 프리미티브로 남아 `priority` 인자 유지(패치 경로가 사용).
- **prompt**(`llm/prompts.py`): Step1에서 priority 지시 삭제.
- **hash**(`validator/validate.py`): `validate_candidate`가 각 candidate task의 priority를
  `derive_priority`로 채워 `graph_hash` triple에 넣음(감사 hash는 그대로 의미 유지).
- **fixture**: `reference_fixture.yaml`에서 `priority:` 키 제거, `fixture.py`는 2-tuple.
  파생 결과 — incident task 9/7, AREA_RECON 4(기존 fixture의 GROUND_INSPECTION 8/6,
  AREA_RECON 4/5/3/4에서 변경). P3/P4는 절대 makespan을 test에 하드코딩하지 않으므로
  (violation 0 · 결정성만 검사) golden test는 유지, CLAUDE.md의 참고 수치만 갱신.
- **`VALIDATOR_VERSION` 1.2 → 1.3**.
- **MissionPatch 경로**(`AddTask.priority`)는 손대지 않음 — RQ3(P8)에서 같은 파생 규칙으로
  정렬한다(D-006: patch 경로는 P2 단위테스트만, end-to-end 미도달).

P6 감사 보강:

- **JSON에 case별 저장**: raw·final 후보 `tasks`(task_type/target/파생 priority)·`edges`,
  raw·final `graph_hash`·`accepted`·`error_codes`, `repaired_schema_valid`. 제3자 재계산 가능.
- **집계**: `X/N`(N 동적), repair는 attempted/recovered/first-pass approved 분리, family B
  edge P/R은 `N/A (0 reference edges)`.
- **하네스 예외**: `failure_category`(모델 출력 실패)와 분리된 `harness_error` 필드.
- **annotation 명시형 schema**: bool 제외 실제 int·범위 검사 복원(현재 9개는 shorthand만
  써서 기존 결과엔 영향 없음).
- **"#1~#12"로 문구 정정**(`P6_RESULTS.md`, `CLAUDE.md`).
- **감사 필드 추가 후 9개 라이브 평가 재실행** — 기존 실행(`456e826`)은 후보 미저장이라 무효.

**영향** `llm/{schemas,prompts,pipeline}.py`, `validator/{candidate,validate,hashing}.py`,
`scenarios/{compiler,fixture}.py` + `reference_fixture.yaml`, `evaluation/{annotations,
harness,metrics,report,plots}.py`, 12개 test 파일. `docs/P6_RESULTS.md` 재작성. 라이브 재실행.
## D-023: scene loader priority 강제 + D-022 정정 (계약 v1.22)

**배경** P6 재검토(D-022 반영분). 원래 지적 8개는 모두 해결됐고 제3자가 JSON으로 9 case를
독립 재계산해 일치 확인. 다만 새 차단 버그 1개:

- **scene priority 검증이 너무 늦음.** D-022가 priority의 진실 원천을 semantic scene으로
  옮겼는데 `scenarios/scene.py`는 여전히 `int(i["priority"])`로 강제 변환. 재현:
  `priority: 11` → scene 로드 성공 → `validate_candidate` accepted=True → compiler에서
  `ValueError` 크래시. `priority: true` → 1로 변환 승인. `priority: "9"` → 9로 변환 승인.
  계약 §7 "파생 priority는 정수 1..10"을 scene 입력 경계가 보장하지 않았다.

**결정**

- `scenarios/scene.py`에 `_priority(value, label)` — `isinstance(int)` and not `bool` and
  `1 <= v <= 10`이 아니면 `ValueError`. `int()` 강제 변환 제거. incident 로드 시 적용.
  회귀 테스트 4값(`0`, `11`, `True`, `"9"`).
- **D-022 본문 정정**: "annotation 명시형 schema에 bool 제외 int·범위 검사 복원"이라고
  적었으나 실제 구현·의도는 **annotation도 `{task_type, target}`만 허용하고 priority 키를
  거부**하는 것이다(`evaluation/annotations.py` `_expand`, 테스트
  `test_annotation_explicit_task_with_priority_key_is_rejected`). Append-only이므로 D-022
  본문은 두고 이 항목이 정정본이다.
- **문서**: `README.md`·`docs/P6_RESULTS.md`의 재현 명령을 `python3 -m evaluation`으로 통일
  (이 환경에 `python` 없음). `core/task.py` docstring과 `CLAUDE.md`의 옛 LLM schema 서술
  (priority 생성) 갱신.
- `VALIDATOR_VERSION`은 올리지 않는다 — scene load 경계 강화이지 Validator 판정 규칙
  변경이 아니며, `industrial_park.yaml`은 이미 9/7로 유효해 기존 결과·JSON에 영향 없음.
  라이브 API 재실행 불필요.

**영향** `scenarios/scene.py`, `tests/test_scene.py`(+4), `core/task.py`(docstring),
`README.md`, `docs/P6_RESULTS.md`, `CLAUDE.md`. 라이브 재실행 없음.
## D-024: P6 승인 + 문서 정정 (문서 전용, 계약 v1.22 불변)

**배경** P6 재검토 최종 통과 — Codex가 연구 결과 승인. 다만 D-023 커밋(`88536ed`)의
문서에 보고 내용과 실제가 어긋난 곳이 있어 정리.

**결정** (계약 텍스트 변경 없음 — 버전 v1.22 유지)

- **P6 승인 완료.** `README.md`·`CLAUDE.md`의 "현재 단계"를 "P1~P6 승인 완료"로,
  세션 진입점(CLAUDE.md §세션 시작 체크리스트, §지금 어디까지)을 D-024 / v1.22 /
  VALIDATOR 1.3 / pytest 225 / 기준일 2026-09-02로 갱신. 다음 단계는 P7/P8 착수 여부 결정.
- **D-023의 "라이브 재실행 없음" 서술 정정**: scene loader 수정 자체는 결과에 영향이
  없어 재실행이 필수는 아니었으나, `pipeline_errors`를 포함한 완전한 감사 JSON을 남기기
  위해 2026-09-02에 라이브 9개 평가를 재실행했다. 그 결과 `data/eval_results/`의 JSON·
  그림·txt가 교체됐고 latency 평균이 15.9s → 18.2s로 바뀌었다(승인 수치 9/9·P/R·exact
  match는 불변). Append-only 원칙에 따라 D-023 본문은 두고 이 항목이 정정본이다.
- `evaluation/__main__.py` docstring의 `python -m evaluation` → `python3 -m evaluation`.
- `docs/P6_RESULTS.md` 헤더에 D-023·D-024 표기 추가.

**비차단(P6 안 막음, 외부 배포 준비 시 처리)**: `pyproject.toml`의
`[tool.setuptools.packages.find]`는 코드 패키지만 잡고 `scenarios/*.yaml`,
`data/reference_annotations/*.yaml`은 package data로 선언돼 있지 않다. `pip install -e`
로컬 실행에는 문제없으나 wheel 배포 시 누락된다. wheel 배포를 준비할 때
`[tool.setuptools.package-data]` 또는 `MANIFEST.in`으로 처리.

**영향** `README.md`, `CLAUDE.md`, `docs/P6_RESULTS.md`, `evaluation/__main__.py`
(docstring). 코드 동작·테스트·결과 수치 변화 없음.
## D-025: P6.5 얇은 통합 runner (계약 v1.23)

**배경** P6 승인 후 Codex 권고. RQ1(NL → LLM graph → Validator 승인)은 P6에서,
RQ2(검증된 graph → CBBA → 2D 실행)는 P3/P4에서 각각의 입력으로 검증됐으나, **하나의
NL 명령을 두 단계에 연속으로 관통시킨 적은 없다**. P7/P8(선택 단계)에 들어가기 전에,
발표에서 "전체 파이프라인 시연"이라고 말할 수 있도록 기존 모듈을 연결하는 얇은 runner를
둔다. 새 알고리즘 없음.

**결정** `evaluation/integration.py`:

- `run_full(command, scene, backend) -> FullRun`: `generate_mission`(RQ1) → 승인 시
  `gen.graph`(compiled TaskGraph)로 `MissionState` 구성 → `allocate`(CBBA plan-time) +
  `SimExecutor.run`(2D 실행) → `GenerationResult` + `AllocationResult` +
  `ExecutionResult`를 그대로 보존. 미승인이면 allocation/execution은 `None`.
- 대표 명령: A1(FULL_RESPONSE, 12 task/6 edge — P1 fixture와 동일 graph), B1(AERIAL_ONLY,
  6 task/0 edge), C1(SELECTIVE_RESPONSE, 9 task/3 edge). reference annotation의 command를
  그대로 사용.
- **게이트**(`tests/test_integration.py`, MockBackend): 세 명령 모두
  (1) `generate_mission` 승인,
  (2) `allocate` — capability/precedence violation 0, unassigned 0,
  (3) `SimExecutor` — 완주(deadlock 없음), violation 0,
  (4) A1은 LLM graph가 P1 fixture와 동일하므로 makespan이 P3/P4 골든(~359.8 / ~257.9)과
      일치.
- CLI: `python3 -m evaluation.integration [--mock] [--command ID ...] [--out PREFIX]` —
  실제 backend는 `OpenAIBackend`, 결과 표 + JSON.

**영향** 신규 `evaluation/integration.py`, `tests/test_integration.py`. `README.md`·
`CLAUDE.md` "현재 단계". P6.5 완료 시 발표 문구를 "NL → CBBA → 실행 전체 시연"으로
정정 가능.
## D-026: P6.5 통합 runner 정정 — fork 구조 + 감사 게이트 (계약 v1.24)

**배경** P6.5 재검토. 코드는 돌고 P1~P6 회귀 없으나, runner가 주장하는 데이터 흐름과
게이트가 검증하는 내용이 실제 구현에 못 미쳤다:

1. **`generate_mission → allocate → SimExecutor` 순차 서술이 사실과 다름.** `SimExecutor`는
   input state를 clone하고 `agent.current_task`를 초기화한 뒤 `_run_epoch`가 READY frontier
   에서 **자체적으로 `run_epoch`(CBBA)를 재수행**한다. `allocate`의 assignment는 executor에
   전달되지 않는다. 올바른 구조는 fork: 검증된 graph → (a) `allocate` plan-time 분석,
   (b) `SimExecutor` event-driven 실행. 이건 버그가 아니라 §13(estimated makespan ≠ 실행
   makespan) 설계대로다 — 문제는 문서·네이밍의 화살표다.
2. **`clean`이 명령 충실도를 안 봄.** validator 승인 + 할당 성공 + 무위반 + 완주만 검사하고
   annotation `allowed_graphs` 대조는 없다. `run_commands`가 정답 graph를 버렸다. C1 명령에
   C2 graph(둘 다 9 task/3 edge)를 생성해도 통과.
3. **감사 JSON이 너무 얇음.** task/edge 개수·makespan·violation·workload만 저장. 실제
   task/edge, graph_hash, scene_hash, validator_version, resolved_models, 그리고 MRTA의
   핵심인 **task→agent assignment(plan·exec 각각)**가 없어 독립 검증 불가.
4. **A1 fixture 동일성 테스트가 동일성을 안 봄.** task 12·edge 6·makespan 일치만 assert.
   우연히 같은 makespan인 다른 graph도 통과.
5. `P6_RESULTS.md`가 P6.5를 아직 "후속 작업"이라 서술.

**결정**

- **문서/서술**: §15 P6.5를 fork 구조로 정정. `integration.py` docstring·D-025 화살표,
  `README`·`CLAUDE`, `P6_RESULTS.md`의 표현을 "검증된 graph를 plan-time CBBA 분석과
  event-driven CBBA executor로 각각 실행"으로 통일. "allocate가 만든 계획을 SimExecutor가
  실행" 서술 금지.
- **`FullRun`**: `exact_match`(P6 `score_graph`로 최종 candidate ↔ annotation `allowed_graphs`
  대조) 추가. `operationally_clean`(기존 clean 조건, 단 `not deadlocked` → `termination ==
  COMPLETED`)와 `demo_pass`(= operationally_clean and exact_match) 분리.
- **`run_commands`**: `Annotation`을 그대로 넘겨 `run_full`이 `score_graph`를 쓸 수 있게.
  case별 `harness_error`(네트워크·인증 예외) 저장 — 한 case 실패가 나머지를 죽이지 않음.
- **감사 JSON**: `meta`(scene_hash, validator_version, requested/resolved model, 시각) +
  case별 `generation`(P6 `GraphSnapshot` 재사용: tasks[task_type/target/derived priority]·
  edges·graph_hash·accepted·error_codes, exact_match) + `plan_analysis`(assignments
  task→agent, estimated_makespan, consensus_rounds) + `execution`(termination, assignments
  task→agent, makespan, winning_bids). P6의 `GraphSnapshot`을 공유하도록 `evaluation.harness`
  의 snapshot 빌더를 public화.
- **A1 테스트**: `graph_hash` 또는 `(task_type, target)` 집합 + edge 집합 직접 비교로 graph
  동일성을 실제 검사. + fixture와 동일하므로 makespan이 P3/P4 골든과 일치함을 유지.
- **라이브 A1/B1/C1 재실행** — 기존 실행은 감사 필드 미저장이라 무효.

**영향** `evaluation/integration.py` 재작성, `evaluation/harness.py`(snapshot public),
`tests/test_integration.py` 강화, `data/eval_results/integration_gpt-5-mini.*` 재생성.
`docs/{P6_RESULTS,RESEARCH_CONTRACT}.md`, `README.md`, `CLAUDE.md`. 새 알고리즘 없음.

## D-027: Operator–LLM Planning Session (P8 착수, 계약 v1.25)

**배경** P8 착수 전 설계 3회 반복(v1/v2/v3) + Codex 검토. RQ3 인프라(§10 MissionPatch +
`apply_patch` reconciliation)는 P2에 이미 구현·단위테스트됨. 없는 것은 NL→intent→MissionPatch
경로, 대화 문맥/grounding, planning session, UI.

설계 중 확인한 제약:
- (a) 고정 5종 task 어휘 + 엄격한 §9 #10 하에서는 어떤 유효 patch도 기존 task의 predecessor
  집합을 못 바꿈(D-006) → "영향받은 commitment만 선택적 재할당"은 recheck 계열 어휘 없이
  시연 불가.
- (b) `allocation/allocate.py`는 fresh graph 전제 — `assignments` 빈 dict 시작, 완료 task를
  unassigned로 집계. 실행 후 residual re-plan에 그대로 못 씀.
- (c) `execution/executor.py`는 최종 MissionState도 UGV 위치(`self.access_nodes`)도
  checkpoint도 반환 안 함. `run()` blocking. 반환형 변경은 P4/P6.5 회귀.
- (d) `validator/patch.py`의 `AddTask.priority`가 D-022(LLM은 priority 미생성)와 불일치.

**결정** P8 첫 범위를 **실행 개시 전의 다중 턴 임무 계획 세션**으로만 고정. executor·
allocator 확장, post-execution update, 선택적 재할당은 전부 후속.

- §1 RQ3 재서술: "증분 graph 수정 + 결정론적 재검증 + atomic commit/rollback + 올바른
  clarification". "동적/선택적 재할당"은 후속.
- 신규 §18(Operator–LLM Planning Session): 범위 / 5종 대화 행위 / session lifecycle(실행 후
  QUERY만 허용, 나머지 UNSUPPORTED) / referent 규칙(K=3, 성공 grounding에만 추가) /
  NO_CHANGE / LLM·결정론 경계 / session 상태 경계(`fresh_session_state`, `phase` 3종,
  plan·execution 분리) / 감사 로그(TURN·EXECUTION event, `plan_assignment_changes` =
  added/removed/changed) / 신규 incident 등록(zone 사전 정의 response point, priority 7) /
  interaction eval(N=12, grounder-only + end-to-end 2분할, dialogue+turn 분모 보고).
- §10: `AddTask` op을 `{task_type, target}`로. priority는 `apply_patch`가 `derive_priority`
  파생(D-022 정렬). `_op_schema_error`의 priority 검사 제거.
- §14: `VALIDATOR_VERSION` 1.3 → 1.4. 세 변경 — (i) AddTask schema, (ii) `scene_hash` zone
  payload에 `reported_incident_position`·`reported_incident_access_node` 추가,
  (iii) `patch_hash`(op field-level schema 통과 시 생성) + `pre_state_hash`(bundle/path
  **내부 순서 보존**, agent만 정렬, winning_bids task_id 정렬, float 규칙 고정) 정의
  (D-015 유보 해제). 기록 정책: field schema 오류 → patch_hash null / field schema 통과
  이후(conflict·whole-graph·reconciliation·accepted) → patch_hash·pre_state_hash 둘 다.
  candidate 경로(#1~#12) 판정 불변. **baseline `v0.6.5-baseline`의 P6/P6.5 결과는
  Validator 1.3 / 옛 scene_hash(`0e8f098cd95aba26f1384fc6ad5c89ad047ec84912cf595936a7b56d75672c6d`)
  로 보존, 라이브 재실행 없음. P8부터 1.4 / 새 scene_hash.** 전체 단위테스트 재실행.
- §15: P8 → P8.0~P8.5 게이트 행. P7은 "(선택, 보류)".
- §17: "P0~P7 완료 전 RQ3" → "P0~P6.5 완료 전 RQ3"(§16 cut-order·§15·§1이 P7을 선행조건으로
  두지 않음 — 내부 모순 정정). 실행 중 patch 주입·실행 후 graph 수정·선택적 재할당을 제외
  목록에 추가.

Codex v1/v2/v3 검토에서 반영한 세부:
- "임무 단계 사이" 표현 삭제 — 실행 버튼 이후엔 graph 수정·incident 추가·NEW/UPDATE/REPORT
  전부 불가, 저장된 `ExecutionResult` 조회(QUERY)만. 실패 후엔 동일 graph 재시도만 허용.
- `pre_state_hash`는 bundle/path 내부 순서 보존(정렬 시 `path=[A,B]`와 `[B,A]`가 같은 hash가
  되어 CBBA 실행 의미가 유실).
- `scene_hash`의 zone payload는 현재 `[z.name, list(z.recon_waypoint)]`만 해시하므로,
  response point 2필드를 payload에 명시적으로 추가하지 않으면 scene 의미가 변해도 hash가
  안 바뀜 → payload에 포함.
- `fresh_session_state`는 `core/mission_state.py`가 아니라 `interaction/session.py`에 둔다
  (`core` → `scenarios` 의존성 방지). `core/`는 무변경.
- `register_incident`는 `incidents` dict만 새로 만들고 `zones`·`route_graph`·`fleet`은
  구조 공유 가능. 원본 Scene 불변을 테스트로 검증(P8.1 게이트의 "route_graph·fleet 비공유"를
  "원본 Scene 불변 검증"으로 교체).
- 실행 버튼도 감사 대상(`event_type: EXECUTION`).
- 반복/하위단계 UPDATE는 `NO_CHANGE`(중복 AddTask 안 만듦, "빈 patch commit" 아님, state
  identity 유지, `allocate` 재호출 안 함).
- session에 `execution: ExecutionResult | None` + `phase EXECUTION_FAILED` 추가. 실행은
  결정론적 UI 버튼이지 LLM intent 아님.
- 감사에서 `directly_released_tasks`(PatchResult, 정상 시나리오 항상 빈 목록)와
  `plan_assignment_changes`(두 plan-time 분석 간 차이)를 분리. "reassigned" 표현 안 씀.
- `invalid-update rejection`은 헤드라인 지표 아님 — Validator fault-injection + orchestrator
  방어 테스트로 강등.
- clarification 지표 2분할: grounder-only vs end-to-end. 헤드라인 = end-to-end.
- 표본 보고 = dialogues + turns + 지표별 분모.
- cache key = model + prompt/schema version + context hash + utterance.
- `label` 제거, incident ID 결정론 생성. `ReportIncidentIntent`는 `zone_ref`(zone_id + name
  alias 매칭). `UnsupportedIntent`는 고정 템플릿 응답(LLM 자유문장 노출 금지). pydantic
  union은 `kind` discriminator 명시. `TurnResult.audit`·`patch_ops`는 typed schema.

별도 `docs/P8_DESIGN.md`는 만들지 않는다 — RESEARCH_CONTRACT.md가 단일 진실 원천이고 이
항목에 설계 근거가 충분하다(중복·불일치 위험).

**영향** 신규 `interaction/*`(schemas, session, context, ground, scene_mut, interpret,
orchestrator, prompts, eval) + `demo/app.py` + `data/interaction_dialogues/*` +
`data/interaction_runs/*` + `tests/test_interaction_*`. 수정: `validator/{patch,patch_apply,
hashing}.py`, `scenarios/{scene.py, industrial_park.yaml}`, `pyproject.toml`,
`docs/{README,CLAUDE}`. **`core/`·`allocation/`·`execution/`·`validator/{validate,
whole_graph}.py`·`llm/pipeline.py`·`evaluation/`은 무변경.** feature branch
`feature/operator-interaction`(태그 `v0.6.5-baseline`에서 분기).

## D-028: incident referent 해석을 fail-closed로 (계약 v1.26)

**배경** P8.1d(결정론적 grounder) 검토에서 Codex가 재현한 차단 결함. `interaction/ground.py`가
"알려진 id와 정규화 매칭 → 아니면 incident 형태 정규식으로 미지 id 판정 → 그 외에는 최근
referent fallback" 순서였다. 즉 **denylist**였고, 정규식에 안 걸리는 표현이 전부 추측으로
흘러내렸다:

```
최근 referent = FIRE_SITE_1 인 상태에서
"FIRE_SITE_9"  -> CLARIFICATION   (정상)
"FIRE_SITE_9." -> RESOLVED FIRE_SITE_1   (오류)
"FIRE-SITE-9"  -> RESOLVED FIRE_SITE_1   (오류)
"북쪽 화재"     -> RESOLVED FIRE_SITE_1   (오류)
```

이는 UX 문제가 아니라 RQ3의 "불명확하면 추측하지 않는다"(§1, §18.7) 위반이며 §18.11의
"잘못된 추측 비율"을 직접 오염시킨다.

두 번째 결함: 정규화 충돌. `FIRE_SITE_1`과 legacy `FIRE SITE 1`이 둘 다 `FIRESITE1`로
정규화되는데 `normalized -> id` dict가 하나를 임의로 덮어써 조용히 선택했다. P8.1c의
`next_incident_id`가 malformed·legacy id의 존재를 전제하므로 현실적인 경로다.

세 번째: "live referent가 없어도 등록 incident가 하나면 자동 선택"은 P8.1d 구현이 도입한
**새 의미 규칙**인데 계약에 없었다. clarification precision/recall gold를 좌우하므로 기록해야
한다.

**결정** 계약 v1.26, §18.5에 명시:

- **fail-closed 우선순위 5단계.** 해석되지 않는 비어 있지 않은 표현은 절대 fallback으로
  내려가지 않는다(denylist → **allowlist** 전환).
- **허용 지시어 목록을 계약에 고정.** 표현이 없거나(`None`/공백) 정규화 후 목록과 일치할
  때만 referent·단일 incident fallback을 시도한다. 목록 확장은 계약 개정으로만.
- **정규화 충돌 → clarification.** `normalized -> id` 가 아니라 `normalized -> id 목록`으로
  두고, 후보 1개면 resolve, 2개 이상이면 되묻는다.
- **단일 incident 자동 선택을 명시적 정책으로 기록.** 표현이 없거나 허용 지시어이고 등록
  incident가 하나뿐이면 고를 대상이 없으므로 되묻지 않는다. §18.11 gold의 전제.

**대안 검토** Codex는 단일 incident fallback을 "입력이 아예 없을 때"로만 제한하는 안도
제시했다. 채택하지 않았다 — `None`과 허용 지시어("거기") 사이에 원리적 차이가 없고, 두
경우 모두 "지시 대상이 미지정인데 후보가 하나뿐"이라는 동일 상황이기 때문이다. 대신 그
경계를 계약에 명시해 평가 gold가 이를 전제하도록 했다.

**영향** `interaction/ground.py` 재작성(해석 순서), `tests/test_interaction_ground.py` 회귀
테스트 추가(정규식 우회 표현 3종 + 정규화 충돌). `VALIDATOR_VERSION` 불변, 코드 동작 외
계약 무결성 규칙·hash·평가 하네스 변화 없음.

## D-029: turn 감사 레코드 정렬 + 지시어 QUERY의 referent 정책 (계약 v1.27)

**배경** P8.2(orchestrator) 검토. Codex가 6개를 지적했고 4개는 순수 구현 결함(턴 전체 예외
격리, state+plan atomic commit, `resolved_models` 전체 기록, mission 없는 `QUERY_STATUS
about=incidents`)이라 코드로만 고친다. 나머지 2개는 계약과 코드가 갈라진 것이라 문서를 먼저
고친다.

1. **감사 schema 불일치.** §18.9는 `grounding {status, incident_id, up_to_step,
   clarification}` / `patch_result {...}`를 요구했으나 구현은
   `grounding {status, entity_kind, entity_id, clarification, candidates}` / `patch {...}`다.
   구현 쪽이 zone grounding까지 표현하므로 더 일반적이지만, 단일 진실 원천과 실제 JSON이
   달라서는 안 된다.
2. **지시어 QUERY가 referent 수명을 무한 갱신.** §18.5는 갱신 대상을 "명시 incident 대상
   `QUERY_STATUS`"로 한정하는데, 구현은 `"거기 상태"` 같은 지시어 해석 QUERY도 매번 갱신했다.
   재현: turn 2에 도입된 referent가 조회 3회 뒤 turn 4로 갱신되어, 반복 조회만으로 K=3
   만료가 영원히 연장된다.

**결정** 계약 v1.27:

- §18.9를 실제 `TurnAudit` 형상으로 정렬한다. `grounding`은 `entity_kind`/`entity_id`로
  일반화하고 **`via` ∈ {explicit, referent, sole_incident}** 를 추가 — §18.5 우선순위의 어느
  단계로 해석됐는지가 §18.11의 clarification 평가에서 "명시 지칭"과 "지시어 해석"을 가르는
  기준이기 때문이다. `patch_result` → `patch`. slot(`up_to_step`·`zone_ref`·`target_phrase`)은
  `extracted_slots`에 있으므로 grounding에 중복하지 않는다. `outcome`·`scene_changed`·
  `state_changed`·`referent_noted`·`answer`를 명시하고, `TURN_ERROR`의 원인이 휘발되지 않도록
  `error_type`·`error_detail`을 영구 레코드에 넣는다.
- `resolved_models`는 **그 턴의 모든 backend 호출**을 담는다. 종전 구현은 intent 분류 직후
  delta를 확정해 `NEW_MISSION`의 Step1/Step2/repair 모델이 누락됐다(§14 위반).
- §18.5: **지시어로 해석된 `QUERY_STATUS`는 referent window를 갱신하지 않는다.** 갱신하면
  window가 "언제 도입됐는가"가 아니라 "window 자신을 통해 언제 다시 언급됐는가"를 재는
  자기참조가 된다. 읽기 전용 조회는 새 지칭이 아니다. 명시 id QUERY는 새 지칭이므로 갱신하고,
  `UPDATE_MISSION`은 해석 경로와 무관하게 갱신한다(graph를 실제로 바꾸거나 이미 충족됐음을
  확인하는 행위이므로 그 incident는 실제로 최근이다).

**영향** `interaction/audit.py`(필드 추가), `interaction/ground.py`(`GroundingOutcome.via`),
`interaction/orchestrator.py`(예외 격리·atomic commit·모델 delta·QUERY 분기),
`tests/test_interaction_{ground,orchestrator}.py`. `VALIDATOR_VERSION` 불변, 계약 무결성 규칙·
hash·평가 하네스 변화 없음.

## D-030: session_id는 입력 경계다 (계약 v1.28)

**배경** P8.2 재검토. `interaction/audit_io.py`의 `audit_path()`가 `session_id`를 파일명에
그대로 결합한다(`Path(directory) / f"{session_id}.json"`). 재현:

```
session_id="../escape"     → data/interaction_runs/../escape.json
session_id="../../outside" → data/interaction_runs/../../outside.json
session_id="/tmp/absolute" → /tmp/absolute.json   (Path 결합이 절대 경로에 흡수된다)
```

§18.9는 감사 기록의 경로를 `data/interaction_runs/<session_id>.json`으로 **고정**하는데,
session id가 자유 문자열이면 그 문장이 보장이 아니라 희망사항이 된다.

**결정** 계약 v1.28. `session_id` 문법을 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`로 고정하고,
`MissionSession` 생성 시점에 강제한다.

검증 위치를 `audit_path()`가 아니라 생성자로 잡은 이유: session id는 파일명에만 쓰이는 값이
아니라 모든 `TurnAudit` 레코드에 복사되고 로그에 찍힌다. 경계에서 한 번 막으면 그 뒤로는
어디서 쓰이든 안전하고, 파일을 쓰는 순간이 아니라 세션이 만들어지는 순간 실패하므로 여러 턴을
진행한 뒤에야 저장이 거부되는 일이 없다.

문법 자체는 의도적으로 좁다. 앞 문자를 영숫자로 제한해 `-`·`.`로 시작하는 id(플래그로 오인,
`.`·`..`)를 막고, 64자 상한은 파일명 길이 제한을 위한 것이며, `/`·`\`·공백·빈 문자열은 모두
거부된다. `S1`, `demo-01`, UUID 형태는 통과한다.

**영향** `interaction/session.py`(`MissionSession.__post_init__`),
`tests/test_interaction_session.py`. 이는 §18.9 경로 보장의 근거를 명시한 것이고 판정 규칙·
hash·평가 하네스는 바뀌지 않는다 — `VALIDATOR_VERSION` 불변.

## D-031: 통합 event_log + 구조화된 clarification 후보 선택 (계약 v1.29)

**배경** P8.2 승인 후 P8.3(Streamlit UI + 실행) 착수 전, Codex 검토에서 이월된 두 항목은
세션·감사 JSON 스키마를 바꾸므로 코드 전에 계약으로 확정한다.

1. **event 시간 순서.** `session_audit_payload`가 turn 전체 → execution 전체 순으로 event를
   쌓아, execution이 마지막인 동안만 실제 순서와 같다. P8.3이 실행 후 `QUERY_STATUS`를
   허용하면 실제 순서 `t1 t2 EXECUTION t3`가 JSON에서 `t1 t2 t3 EXECUTION`으로 뒤바뀐다.
2. **clarification 후보 선택.** 정규화가 비는 malformed incident id는 후보로 제시돼도
   사용자가 그 문자열을 다시 입력하면 명시 매칭이 안 된다(정규화 충돌이 있는 두 실제 id도
   마찬가지). UI 후보 클릭을 자연어로 되먹이면 grounder를 재경유하며 이 문제가 남는다.

**결정** 계약 v1.29:

- **통합 `event_log: list[TurnAudit | ExecutionAudit]`**. `handle_turn`이 `TurnAudit`을,
  실행 함수가 실행 종료 즉시 `ExecutionAudit`을, 실행 후 turn이 다시 `TurnAudit`을 실제
  발생 순서대로 append한다. **list 순서가 event 순서의 유일한 진실 원천**이며 병합용 index를
  저장하지 않는다. `event_seq`(0..N-1)는 dataclass 필드가 아니라 직렬화 시 `enumerate`로
  파생한다 — 감사 파일에서 순서를 확인하기 위한 파생값이지 두 번째 상태가 아니다. execution은
  `turn_count`를 소비하지 않는다. `turn_log`는 제거하고 필요 시 `event_log`에서 `TurnAudit`만
  거르는 read-only property로만 남긴다. `write_session_audit`가 검증: 모든 event의
  `session_id` 일치 / `event_seq == 0..N-1` / append 후 기존 순서 불변 /
  `t1 t2 EXECUTION t3` JSON 순서 일치 / execution이 `turn_count` 미소비.

- **`PendingClarification`(typed, frozen)**: `source_turn_id`, `intent_kind`,
  `extracted_slots`, `unresolved_slot`(`zone_ref` | `target_phrase`), `entity_kind`,
  `candidates`, `original_utterance`. **entity ambiguity에서만** 생성한다(incident 후보 ≥ 2,
  또는 구조적으로 선택 가능한 zone 후보). mission 부재·`up_to_step` 누락·활성 mission 중
  `NEW`·incident 0개·fail-closed 2단계·`UNSUPPORTED`는 pending을 만들지 않는다 — 이들은
  자연어로 다시 말해야 풀린다. 첫 버전의 구조화 선택은 **entity 모호성만** 해소하고, 누락된
  workflow step을 UI로 채우는 것은 별도 설계다.

- **`select_clarification_candidate(session, entity_id) -> TurnResult`** — LLM 없는 결정론
  함수. pending 확인 → `entity_id in candidates` → scene 존재 확인 → 보류 intent·slot 복원 →
  선택 id를 resolved로 주입 → 원래 UPDATE/QUERY/REPORT 재개 → 성공 시 pending 제거. **이것도
  감사되는 새 턴**이다: `turn_count` +1, 새 `TurnAudit`, LLM 0회, `resolved_models = []`,
  `input_kind = "CANDIDATE_SELECTION"`, `resumed_from_turn_id`, `selected_entity_id`(별도
  필드 — LLM 추출값처럼 `extracted_slots`에 섞지 않는다). grounding `via = explicit`.

- **pending 중 다른 입력**: 후보 선택·취소만 허용. 일반 자연어는 LLM에 보내지 않고 "후보를
  선택하거나 취소해 주세요"로 응답(새 clarification으로 자동 덮어쓰지 않음 — backend 실패 시
  기존 clarification 유실 방지). `CANCEL_CLARIFICATION`은 결정론 버튼이며 graph·scene·referent
  불변, pending만 제거. pending 동안 실행 버튼 비활성.

- **pending 제거**: 성공한 `COMMITTED`·`NO_CHANGE`·`ANSWERED` / 명시적 취소 / phase 변경 ·
  새 session → 제거. 후보 아닌 id / Validator·`allocate` 실패 → 유지(재시도 가능).

- **정규화 함수 위치**: `scenarios/naming.py` — `normalize_identifier()`(대문자화 + 영숫자만),
  `normalize_zone_ref()`(한국어 `구역`/`지역` 접미사 제거 후 `normalize_identifier`). scene
  loader와 incident grounder가 `normalize_identifier`를 공유하고, zone grounder만
  `normalize_zone_ref`를 쓴다. `scenarios/scene.py`가 `interaction/`을 import하는 계층 역전을
  피하려는 것. scene YAML 로더는 `normalize_identifier(incident_id)`가 비는 id를 거부한다.
  주장은 "지원되는 로딩 경로와 `register_incident()`에서는 정규화 빈 id가 생성되지 않는다"이며
  "구조적으로 불가능"은 아니다. **부수효과**: incident id 매칭이 더 이상 zone 접미사를
  제거하지 않는다(incident id는 접미사를 갖지 않으므로 의도된 변화).

**영향** `interaction/session.py`(`event_log`, `PendingClarification`, `turn_log` property),
`interaction/audit.py`(`TurnAudit` 3필드), `interaction/audit_io.py`(`event_seq` 파생 +
writer 검증), `interaction/orchestrator.py`(`select_clarification_candidate`, pending 분기,
pending 중 입력 차단), `interaction/ground.py`(`scenarios.naming` 사용), `scenarios/naming.py`
(신규), `scenarios/scene.py`(로더 거부), `demo/app.py`(P8.3). 판정 규칙·hash·평가 하네스
불변 — `VALIDATOR_VERSION` 1.4 그대로.

## D-032: clarification reason·event append 경계·실행 감사 의미 확정 (계약 v1.30)

**배경** D-031 구현 전 재검토에서 세 가지 빈틈을 확인했다.

1. 현재 grounder는 unknown 표현에도 사용자가 참고할 known entity 목록을 `candidates`로 돌려준다.
   따라서 `len(candidates) >= 2`만으로 pending을 만들면 실제 모호성이 아닌
   `"북쪽 화재"`·미지 zone까지 후보 클릭 흐름으로 잘못 분류된다.
2. 후보 선택·취소와 실행은 LLM backend를 받지 않는데 감사 레코드는 `mode`를 요구한다.
   D-031의 함수 시그니처만으로는 그 값을 정직하게 정할 수 없다.
3. public mutable `event_log`는 외부 코드가 이미 기록된 event를 재배열할 수 있어, "list 순서가
   실제 시간 순서"라는 주장 자체를 세션이 보장하지 못한다. 실행기 예외의 감사 형상도 비어 있다.

**결정** 계약 v1.30:

- `ClarificationReason`을 grounder 결과와 감사 schema에 추가한다. 고정 값은
  `AMBIGUOUS_ENTITY`, `UNKNOWN_ENTITY`, `MISSING_ENTITY`, `NO_ENTITIES`, `MISSING_MISSION`,
  `MISSING_STEP`, `ACTIVE_MISSION`, `PENDING_SELECTION`, `INVALID_SELECTION`. pending은 오직
  `AMBIGUOUS_ENTITY` + 후보 2개 이상이며 다른 필수 slot도 완전할 때만 생성한다. 후보 목록은
  reason을 대신하지 않는다.
- 후보 선택·취소는 `mode`를 명시적으로 받는 결정론 함수다. 잘못된 후보와 pending 중 자연어도
  각각 새 감사 턴으로 남고 pending을 유지한다. 취소는 `CLARIFICATION_CANCELLED` outcome과
  `CLARIFICATION_CANCEL` input kind를 쓰며 pending만 제거한다.
- 세션이 private `_event_log`와 `append_event()`를 소유한다. 외부에는 read-only tuple을
  노출하고 writer는 순서를 재구성하지 않는다.
- 실행 진입점은 `execute_session(session, *, mode)`. 정상 종료뿐 아니라 DEADLOCK·STEP_LIMIT·
  executor 예외도 `ExecutionAudit`에 기록하며 예외는 `ERROR` termination과 원인을 남긴다.
  state/plan 부재·비-PLANNING phase·pending 존재는 event 생성 전 `ValueError`로 거부한다.

**대안 검토** 후보 수만으로 pending을 결정하는 방안은 unknown과 ambiguity를 구별하지 못해
채택하지 않았다. public event list + writer 검증만 두는 방안도 writer 호출 전 메모리 이력이
바뀌는 것을 막지 못해 채택하지 않았다. LLM 없는 action의 mode를 session에 고정하는 방안은 한
세션에서 live 실패 후 cached/mock로 전환하는 P8.3 요구와 충돌하므로 caller가 명시하도록 했다.

**영향** `interaction/{ground,audit,session,orchestrator,audit_io}.py`, 실행 action 신규 모듈,
`tests/test_interaction_*`. Validator 판정 규칙·hash payload·P6 평가 하네스는 바뀌지 않으므로
`VALIDATOR_VERSION`은 1.4 그대로다.

## D-033: 실행 실패 뒤 동일 graph 재시도 보존 (계약 v1.31)

**배경** D-032는 실행 action의 전제를 `phase == PLANNING`으로 적었지만, 기존 §18.1은 실행
실패 시 graph 수정은 금지하되 **동일 graph 재시도는 허용**한다. 그대로 구현하면
`EXECUTION_FAILED`에 들어간 세션이 재시도할 수 없어 두 조항이 충돌한다.

**결정** 실행 action은 state·plan이 있고 pending이 없으며 phase가 `PLANNING` 또는
`EXECUTION_FAILED`일 때 허용한다. 실패 뒤 재시도는 새 `ExecutionAudit`을 append하고 최근
`session.execution`을 교체한다. 이미 `EXECUTED`인 세션의 재실행은 거부한다.

**영향** §18.9 실행 전제와 P8.3 실행 action 테스트. Validator 규칙·hash·평가 하네스는
바뀌지 않으므로 `VALIDATOR_VERSION`은 1.4 그대로다.

## D-034: OpenAI 호환 intent wire schema 분리 (계약 v1.32)

**배경** P8.3의 실제 API 3턴 게이트 첫 호출에서 `gpt-5-mini`가 응답하기 전에 OpenAI API가
HTTP 400을 반환했다. Pydantic `IntentEnvelope`의 `kind` discriminated union은 JSON Schema의
중첩 `oneOf`와 `discriminator`로 직렬화되며, structured-output 경계가 이를 허용하지 않았다.
mock은 Pydantic 객체를 직접 반환하므로 이 배선 결함을 발견하지 못했다. 세 실패 턴은 모두
`TURN_ERROR`로 감사됐고 mission/state는 생성되지 않았다.

**결정** 내부 `OperatorIntent` 5종과 `IntentEnvelope`는 strict discriminated union으로
유지한다. API에는 별도의 평면 `IntentWireEnvelope`를 요청한다. wire object는 `kind`,
`zone_ref`, `target_phrase`, `up_to_step`, `about`, `note`를 모두 필수 키로 가지며, 사용하지 않는
slot은 `null`이다. Pydantic cross-field validator가 kind에 허용되지 않은 non-null slot을
거부하고, 통과한 객체만 결정론적으로 기존 `IntentEnvelope`로 변환한다. 따라서 transport
제약 때문에 내부 타입 안전성이나 intent 의미를 약화하지 않는다. interaction cache의
prompt/schema version은 새 wire 형상에 맞춰 갱신한다.

**대안 검토** 내부 union에서 discriminator를 제거하면 API schema는 단순해지지만 내부 판별의
명시성과 기존 strict 테스트를 약화한다. raw JSON을 받아 수동 파싱하면 structured output의
장점을 버린다. 두 방법 모두 채택하지 않았다.

**영향** `interaction/{schemas,interpret,prompts}.py`, mock/scripted interaction 테스트,
`llm/cache.py`의 prompt/schema version. Validator 판정 규칙·hash payload·P6 평가 하네스는
변하지 않으므로 `VALIDATOR_VERSION`은 1.4 그대로다.

## D-035: P8.4 interaction gold 구성·분모 고정 (계약 v1.33)

**배경** §18.11은 N=12와 네 dialogue shape를 적었지만 “family당 4”의 family가 무엇인지,
후보 클릭을 LLM 정확도 분모에 넣는지, gold 파일이 어떤 필드를 가져야 하는지 고정하지 않았다.
이 상태에서 live 결과를 먼저 보면 사례 구성이나 정답 schema를 결과에 맞춰 바꿀 수 있다.

**결정** P6와 같은 세 profile을 family로 재사용한다:
`A=FULL_RESPONSE`, `B=AERIAL_ONLY`, `C=SELECTIVE_RESPONSE`. 각 family에
`NEW-only`, `REPORT+UPDATE`, `QUERY`, `ambiguous-selection`을 한 건씩 두어
`A1..A4`, `B1..B4`, `C1..C4` 12개로 고정한다. 각 dialogue는 2~5 operator turn이며,
strict YAML은 자연어 발화의 기대 intent/slot/outcome/grounding/patch와 마지막 graph를 기록한다.
구조화된 후보 선택도 turn·감사·grounding 평가에는 포함하지만 LLM 호출이 아니므로 intent/slot
정확도 분모에서는 제외한다. gold와 strict loader를 어떤 P8.4 live 호출보다 먼저 커밋한다.

**대안 검토** interaction 전용의 새 A/B/C 의미를 만드는 방안은 P6 family와 같은 글자를 다른
뜻으로 쓰게 되어 채택하지 않았다. 후보 클릭을 intent 정확도에 넣는 방안도 LLM이 관여하지 않는
결정론적 UI action을 모델 성능처럼 보이게 하므로 채택하지 않았다.

**영향** §18.11, `data/interaction_dialogues/`, P8.4 annotation loader/harness/report.
Validator 판정 규칙·hash payload는 바뀌지 않으므로 `VALIDATOR_VERSION`은 1.4 그대로다.

## D-036: P8.4 gold에 initial graph 분리 (계약 v1.34)

**배경** D-035의 gold schema는 마지막 `final_graph`만 고정했다. 그러나 모든 dialogue가
`NEW_MISSION`으로 시작하고 일부는 뒤에서 patch를 적용하므로, final만으로는 첫 생성 graph의
정답을 후속 patch에서 역산해야 한다. 그러면 초기 생성 오류와 patch 오류가 한 정답에 섞인다.

**결정** 모든 dialogue에 `initial_graph`와 `final_graph`를 함께 둔다. initial은 첫 NEW의
정답이고 final은 모든 turn 후의 정답이다. strict loader는 둘을 각각 Validator로 self-check하고,
turn별 기대 patch 합집합이 initial→final의 task/edge 차이와 정확히 일치하는지 확인한다. 신규
incident를 포함한 final은 gold REPORT를 결정론적으로 적용한 scene에서 검증한다.

**영향** §18.11, P8.4 gold 12개, annotation loader. Validator 판정 규칙·hash payload는
바뀌지 않으므로 `VALIDATOR_VERSION`은 1.4 그대로다.

## D-037: P8.4 patch 승인·release gold 명문화 (계약 v1.35)

**배경** §18.11 첫 문단은 기대 `apply_patch` 판정과 released task를 요구하지만 D-035의
구체 schema 설명은 `added_tasks`/`added_edges`만 열거했다. 암묵적으로 모두 승인·release 0이라
가정하면 Validator/reconciliation 결과를 평가에서 실제로 확인하지 않게 된다.

**결정** patch가 있는 모든 gold turn은 `accepted`, `added_tasks`, `added_edges`,
`directly_released_tasks` 네 필드를 정확히 가진다. 현재 canonical chain extension은 모두
`accepted=true`, `directly_released_tasks=[]`다. loader는 누락·추가 필드를 거부한다.

**영향** §18.11, P8.4 gold와 loader. Validator 판정 규칙·hash payload는 바뀌지 않으므로
`VALIDATOR_VERSION`은 1.4 그대로다.

## D-038: P8.4 최초 live 결과 동결과 사후 튜닝 경계

**배경** D-035~D-037로 live 호출 전에 고정한 12개 dialogue를 P8.4 하네스로 실행했다.
grounder-only는 dialogue exact 12/12였지만, 실제 `gpt-5-mini-2025-08-07` end-to-end는
6/12였다. 주 실패는 한국어 조사가 포함된 slot(`거기는`, `Utility Yard에서` 등)과
`NEW_MISSION`의 금지 `note` 출력이다.

**결정** 최초 live 결과와 전체 turn audit를 `data/eval_results/p8_4_gpt-5-mini.*`에 그대로
동결한다. 앞선 실패로 전제가 사라진 후속 turn도 분모에서 제거하지 않는다. 이 결과를 보고
prompt/normalizer를 개선할 수는 있지만, 같은 12개에서 얻은 사후 상승값은 새 end-to-end
headline으로 쓰지 않는다. 성능 개선 주장은 별도의 held-out dialogue가 있어야 한다.
grounder-only의 intent·slot exact는 gold 주입 경계 검사이며 LLM 성능으로 서술하지 않는다.

**영향** `docs/P8_4_RESULTS.md`, P8.4 감사 JSON·text 결과, README/CLAUDE 상태. 계약의 평가
방법과 Validator 판정 규칙은 바뀌지 않으므로 계약은 v1.35, `VALIDATOR_VERSION`은 1.4를
유지한다.

## D-039: P9 실행 중 명령과 bidder-connected 선택적 재할당 (계약 v1.36)

**배경** P8은 실행 전 대화와 graph 수정까지만 지원한다. 운용자가 실제로 원하는 흐름은 실행
중 새 상황을 보고하고, 완료된 작업을 다시 하지 않으면서 필요한 미시작 할당만 바꿔 계속
수행하는 것이다. 기존 D-006은 고정 어휘의 valid patch가 predecessor diff를 만들지 않으므로
Validator reconciliation만으로 release가 나오지 않는다고 정확히 지적했지만, 이는 새 READY
task와 기존 미시작 task 사이의 입찰 경쟁까지 금지하는 근거는 아니다.

**결정** RQ4/P9를 선택 확장으로 추가한다. executor는 task-completion event에서만
checkpoint/pause하며, 동시에 남아 있는 RUNNING task와 모든 COMPLETED task는 잠근다. online
patch로 새로 READY가 된 task의 bidder union과 bidder를 공유하는 기존 ASSIGNED task를 직접
영향으로 보고, agent별 최초 영향 task부터 CBBA bundle suffix만 release한 뒤 새 READY와 함께
rebid한다. 정책 이름은 `bidder-connected bundle suffix`; 전역 최소·최적이라고 주장하지 않는다.

P9는 신규 recheck 어휘를 추가하지 않고 기존 canonical incident workflow 확장으로 시연한다.
online UPDATE는 checkpoint clone에서 patch·release·epoch를 모두 성공시킨 뒤 runtime/state를
한 번에 교체한다. P8 one-shot 실행과 P8.4 결과는 변경하지 않는다.

**대안 검토** 모든 미시작 task full reset은 단순하지만 선택적 보존 주장을 할 수 없고, held를
전부 보존하는 no-reset은 새 task만 빈 자리에 넣어 기존 commitment가 새 정보에 반응하지 않는다.
임의 wall-clock 중단과 RUNNING abort는 남은 travel/dwell·물리 상태 정의가 필요해 제외했다.

**영향** §1 RQ4, §15 P9.0~P9.4, §17 범위, 신규 §19, incremental `SimExecutor`, online
interaction audit/UI/evaluation. whole-graph Validator 판정 규칙과 hash payload는 바뀌지 않으므로
`VALIDATOR_VERSION`은 1.4 그대로다.

## D-040: P9 보존 지표 의미와 대표 비교 결과 (계약 v1.37)

**배경** P9.4 대표 fixture를 실행해 보니 release된 task가 같은 agent에게 다시 낙찰되는 경우가
있었다. 이를 `preserved_active_assignments`로 세면 “owner가 최종적으로 같음”과 “기존 commitment를
release하지 않음”이 섞인다. 선택 정책이 줄이는 것은 owner change가 아니라 release 범위이므로
두 값을 분리해야 한다.

**결정** preserved assignment는 release되지 않았고 전후 owner도 같은 task만 센다. release 후
같은 agent가 재낙찰한 task는 `released_tasks`에는 남고 `existing_owner_changes`는 0일 수 있지만,
preserved에는 포함하지 않는다. 비교 입력은 결과 확인 전에 커밋한
`data/online_reallocation_fixture.yaml`로 고정한다. 이 fixture는 event 10(t=121.643s)에
COMPLETED 10개, RUNNING 5개, 미시작 ASSIGNED 2개가 있으며, ZONE_B의 FIRE_SITE_6 full chain을
추가한다.

**결과** no-reset은 0개 release/2개 보존, full-reset은 2개 release/0개 보존, selective는
`AREA_RECON__ZONE_C` 1개 release/`GROUND_INSPECTION__FIRE_SITE_1` 1개 보존이었다. 세 정책 모두
COMPLETED, capability/precedence violation 0, makespan 453.883s였고 기존 owner change도 0이었다.
따라서 이 결과는 selective가 release 범위를 줄였다는 것만 보이며 성능 또는 최적성 우위를
보이지 않는다.

**영향** §19.4 보존 지표 정의, `allocation/online.py`, P9 Streamlit UI,
`evaluation/online_reallocation.py`, `docs/P9_RESULTS.md`. whole-graph Validator의 판정·hash는
바뀌지 않으므로 `VALIDATOR_VERSION`은 1.4 그대로다.

## D-041: suffix 주장 축소 + online 재시도 lifecycle + fixture strict schema (계약 v1.38)

**배경** P9.0~P9.4 완료 후 독립 재검토. Blocker는 없었고 checkpoint 등가성·턴 atomicity·
감사 순서는 재현으로 확인됐다. 다만 계약이 실증 범위를 넘어서는 주장을 하고 있었고,
lifecycle에 막다른 상태가 있었다.

1. **suffix 확장이 실증되지 않았다.** 대표 fixture와 모든 단위테스트에서
   `released == directly_affected`이고 `suffix_extra_release_count = 0`이다. 재현:
   frozen checkpoint에서 어떤 agent도 bundle에 ASSIGNED task를 2개 이상 갖지 않으며,
   `_selective_suffix()`를 `return directly_affected`로 바꿔도 625개 테스트와 P9 실험이
   전부 통과한다. 원인은 fixture 선택이 아니라 운용 경로 구조다 — `build_chain_patch`는
   `AREA_RECON`을 만들지 않으므로 신규 incident의 즉시 READY task는 `THERMAL_RECON`뿐이고,
   그 bidder union이 UAV 전체라 UAV bundle은 전부 영향, UGV bundle은 전부 비영향이 되어
   섞인 bundle이 존재할 수 없다.
2. **§19.5가 자기모순이었다.** "bundle 길이가 suffix 차이를 만들지 못하는 checkpoint는
   실험 fixture로 사용하지 않는다"고 쓰고 정확히 그런 fixture를 고정했다.
3. **online advance 예외가 세션을 막다른 길로 만든다.** 재현: 예외 주입 후
   `phase=EXECUTION_FAILED`·`runtime` 보존인데, online 재개는 phase 때문에, one-shot은
   runtime 때문에 거부된다. 상태 오염은 없으나 §18.1이 one-shot에 주는 재시도가 online에는
   없다.
4. **평가 fixture loader가 타입을 세탁한다.** `str(raw[...])`/`float(...)`가 `int` fixture_id,
   문자열 simulation_time을 조용히 통과시킨다. D-023이 scene loader에 금지한 패턴이다.

**결정** 계약 v1.38:

- **정책명을 `bidder-connected selective release`로 한다.** 실증된 주장은 "신규 READY task와
  입찰자가 겹치는 기존 미시작 assignment만 release/rebid해 full reset보다 더 많은 assignment를
  보존하면서 무위반 완주했다"까지다. bundle suffix 확장은 **보수적 구현 규칙**으로 격하하고,
  §19.3에 왜 현재 경로에서 도달하지 않는지와 어떤 조합에서 도달할 수 있는지를 명시한다.
  코드는 남긴다 — 다른 신규 READY 조합에서 bundle prefix commitment를 지키는 안전장치이기
  때문이다. 단위테스트로 **분기의 정확성**만 고정하고, 이를 end-to-end 실증으로 서술하지
  않는다(D-006과 같은 원칙: 도달하지 않는 경로는 도달하지 않는다고 쓴다).
- **`suffix_extra_release_count`를 §19.5 원시 지표로 보고한다.** 현재 값 0을 결과 문서와 JSON에
  그대로 적는다. 이 값은 `released`와 `directly_affected` 두 목록에서 파생되므로
  `OnlineReallocationAudit`에 중복 저장하지 않는다 — 주장이 걸린 곳은 실험이지 턴 감사가 아니다.
- **§19.5의 모순 문장을 삭제**하고, 평가 fixture strict schema 원칙을 추가한다.
- **online 재시도 lifecycle**: runtime이 보존된 `EXECUTION_FAILED`에서 checkpoint 재개를
  허용한다. `(phase, execution, runtime)` 세 조합의 의미를 §19.1 표로 명문화해 소비자가
  one-shot 결과 실패 / one-shot 예외 / online 예외를 구분하게 한다. 예외 실패에 가짜
  `ExecutionResult`를 만들지 않는다.

**영향** `allocation/online.py`(지표 노출 없음 — 파생), `evaluation/online_reallocation.py`
(strict loader + `suffix_extra_release_count`), `interaction/online_execute.py`(재시도 허용),
`demo/app.py`(재개 버튼), `tests/test_online_{allocation,evaluation,session}.py`,
`docs/P9_RESULTS.md`. 판정 규칙·hash·CBBA 수식 불변 — `VALIDATOR_VERSION` 1.4 그대로,
P9 결과 수치(release 0/2/1, makespan 453.883s, 위반 0)도 그대로다.

## D-042: D-041 정정 — suffix 단정 완화 + terminal online 상태 (계약 v1.39)

**D-041을 supersede한다.** D-041 본문은 당시 기록 그대로 둔다 — 그때 무엇을 잘못 판단했는지도
이력의 일부다. 아래 두 항목에 대해서는 이 결정이 현행 규칙이다.

**배경** D-041 재검토. 지표 설계(파생값을 감사에 중복 저장하지 않음, `selective`에만 정의)와
strict loader는 승인됐고 P9 수치도 그대로다. 그러나 D-041 자체에 두 가지 오류가 있었다.

1. **suffix 실증 범위를 반대 방향으로 과도하게 단정했다.** D-041은 "모든 reachable online
   path에서 `THERMAL_RECON`만 READY가 되므로 섞인 bundle이 존재할 수 없다"고 썼다. 이는
   증명되지 않았다. `build_chain_patch`는 신규 incident의 전체 chain만 만드는 게 아니라
   **기존 incident의 부분 workflow 연장**도 만든다 — `THERMAL_RECON`이 COMPLETED인 incident를
   `SUPPRESSANT_DROP`까지 늘리면 신규 READY의 bidder는 R1/R2이고 `AREA_RECON`(bidder S1/S2)은
   비영향이 되므로, S-agent bundle이 `THERMAL_RECON`(영향) → `AREA_RECON`(비영향) 순서면 suffix
   확장이 발생할 여지가 있다. 그 상태의 실제 도달 가능성은 확인하지 않았다.
2. **§19.1 표에 terminal online 실패 조합이 빠졌다.** `advance_to_next_completion()`은 예외
   외에 `DEADLOCK`/`STEP_LIMIT`라는 **결과**로도 끝난다. 그 경로는 candidate를 runtime에
   publish한 뒤 `phase=EXECUTION_FAILED`·`execution=ExecutionResult`·`runtime=candidate`를
   만드는데, D-041의 재시도 게이트는 `runtime is not None`만 봤다. 재현: DEADLOCK 종료 뒤
   `advance_online_session`을 다시 부르면 재개가 허용되고, phase가 `EXECUTION_PAUSED`로
   되돌아가면서 **기록된 DEADLOCK 결과가 stale하게 남는다**(`session.execution`은 DEADLOCK인데
   phase는 PAUSED).

**결정** 계약 v1.39:

- §19.3의 suffix 서술을 **관측 사실**과 **단정하지 않는 것**으로 분리한다. "대표 fixture와
  현재 테스트가 다루는 신규 incident 전체-chain 경로에서는 섞인 bundle이 나오지 않았고
  `suffix_extra_release_count = 0`이다"까지만 쓰고, 도메인 전체의 불가능성으로 일반화하지
  않는다. 부분 workflow 연장에서 mixed bundle이 도달 가능한지는 미검증으로 명시한다.
- **online 재시도 조건을 `phase == EXECUTION_FAILED AND runtime is not None AND
  execution is None`으로 좁힌다.** `execution`이 있으면 executor가 결과로 끝난 것이므로 재개는
  같은 종료를 반복할 뿐 아니라 기록을 지운다. §19.1 표에 해당 행(terminal — 재개 금지,
  `QUERY_STATUS`만 또는 새 session)을 추가한다.
- §19.5 fixture strict schema에 simulation time 음수 금지를 추가한다.

**영향** `interaction/online_execute.py`(`_preconditions`), `demo/app.py`(재시도 버튼 조건),
`evaluation/online_reallocation.py`(음수 시간 거부), `allocation/online.py` docstring,
`docs/P9_RESULTS.md`, `tests/test_online_{session,evaluation}.py`, `tests/test_demo_app.py`.
P9 실험 수치·결론 불변, `VALIDATOR_VERSION` 1.4 불변.

## D-043: P8.5 시각화 범위 고정 (계약 v1.40)

**배경** P9까지 끝난 뒤 발표 준비 단계. §15의 P8.5 게이트는 "UI graph·2D 실행 시각화 폴리싱"
한 줄에 기준이 `—`로 비어 있었다. 현재 `demo/app.py`는 **전부 `st.dataframe`과 `st.metric`**
이라 RQ1의 task graph도, RQ2/RQ4의 이종 UAV/UGV 이동도 그림으로 볼 수 없다. 시연하면
스프레드시트가 보인다.

순서를 "발표 자료 먼저, 남으면 시각화"에서 **"최소 시각화 먼저, 그다음 발표 구성"**으로
바꾼다 — 표만 있는 UI로는 발표 흐름 자체를 평가할 수 없기 때문이다.

**결정** 계약 v1.40, §18.14 신설. 범위는 **DAG + 정적 2D 지도까지**로 고정한다.

- **애니메이션 제외.** timestamp로 재구성은 가능하지만 agent별 보간, dwell/travel 분리,
  online update 전후 assignment history 연결, Streamlit rerun 상태 관리, 발표 환경의 프레임
  성능이 전부 따라온다. 학부 발표에는 정적 경로 + 순서 번호 + 상태 색으로 충분하다.
- **순수 view.** `demo/visualization.py`가 matplotlib `Figure`만 반환한다. 연구 로직을
  복제하지 않고 이미 계산된 값만 그린다. 렌더 전후 `pre_state_hash`·`scene_hash` 불변을
  테스트로 고정한다 — live `SimExecutor`를 넘기는 경로가 유일한 실질 위험이라 가능하면
  checkpoint를 입력으로 받는다.
- **결정론적 layout.** 같은 graph → 같은 그림. force-directed는 쓰지 않는다. 이 도메인의
  graph는 zone recon 집합 + incident별 선형 chain이라 행=incident, 열=workflow 단계 격자로
  충분하고, 새 incident가 새 행이 되어 online update가 눈에 띈다. 발표 그림 재현성과 테스트
  가능성이 여기에 함께 걸려 있다.
- **DAG의 node·edge 집합 == `TaskGraph`의 것.** 검토 의견의 "graph hash 변화가 그림에 반영"은
  그림 안에 hash를 적으라는 뜻이 될 수 있어 이렇게 바꿔 적는다. 집합 일치가 곧 "online update가
  재렌더에서 즉시 보인다"의 근거다.
- **`viz` 미설치 시 UI degrade.** matplotlib은 기존 optional extra이므로, 없으면 UI가 죽지 않고
  §18.12의 표로 돌아가야 한다(검토 의견에 없던 항목).
- **발표 그림도 같은 renderer.** UI와 슬라이드가 서로 다른 그리기 경로를 갖지 않게 한다(§14
  재현성의 연장). 검토 의견은 "가능하면"이었으나 게이트 항목으로 올린다 — 두 경로가 갈라지면
  발표에 나가는 그림이 검증 대상 밖이 된다.

함수 분할(`render_task_graph` / map 계열 3종 등)은 계약에 고정하지 않는다. 계약이 요구하는
것은 **무엇이 구분돼 보여야 하는가**(plan-time / paused runtime / completed execution)이며,
그것을 함수 3개로 할지 인자 하나로 할지는 §16 "단순함이 먼저다"에 따른 구현 판단이다.

**영향** 신규 `demo/visualization.py`, `demo/app.py`(연결 + degrade 경로),
`tests/test_visualization.py`(신규), `tests/test_demo_app.py`. `core/`·`allocation/`·
`execution/`·`interaction/`·`evaluation/` 무변경. 새 지표·새 주장 없음, P9 수치 불변,
`VALIDATOR_VERSION` 1.4 불변.

## D-044: D-043 보정 — 데이터 모델과 결정론 기준 정합 (계약 v1.41)

**D-043을 보정한다.** 방향(DAG + 정적 2D, 애니메이션 제외, 순수 view)은 그대로이고, 구현 전에
계약이 실제 데이터 모델과 어긋난 다섯 곳을 고친다. 전부 코드로 재현·확인했다.

1. **`TaskStatus`는 5종이 아니라 6종이다.** `core/enums.py`에 `CANCELLED`가 있다. §10에서
   cancellation이 미지원이라 정상 시나리오엔 안 나오지만 Validator와 checkpoint가 지원하는 유효
   상태다. 색 표를 6종으로 정의하고(`CANCELLED` 진한 빨강), **enum을 순회하며** 검사해 나중에
   멤버가 늘면 renderer보다 테스트가 먼저 깨지게 한다.

2. **UGV polyline을 그릴 공개 API가 없다.** `RouteGraph`는 `shortest_path_distance()`와
   `is_reachable()`만 제공하고 경유 node를 주지 않는다. 이대로면 view가 Dijkstra를 재구현해야
   하는데 그것이 바로 "연구 로직 비복제" 위반이다. 따라서 D-043의 "core 무변경"을 **"할당·실행
   의미는 불변, 시각화용 read-only 최단경로 조회 API 추가만 허용"**으로 완화한다. 요구사항은
   기존 API와 같은 tie-break, 모든 node 쌍에서 누적 weight == 거리, graph 불변, 결정론,
   도달 불가 시 일관된 반환, 그리고 **P3/P4 골든(359.8 / 257.9) 불변**. `VALIDATOR_VERSION`은
   1.4 그대로다 — 판정 규칙이 아니다.

3. **paused runtime의 "현재 위치"는 존재하지 않는다.** `SimExecutor._advance()`는 task가
   **완료될 때만** `agent.position`(UGV는 `access_nodes`)을 갱신하므로, RUNNING 중인 agent를
   현재 state에서 읽으면 출발 위치가 나온다. 애니메이션·보간이 범위 밖인데 "현재 위치를
   표시한다"고 쓴 것은 모순이었다. **마지막 확정 위치 + RUNNING target + dashed in-progress
   leg**로 정의하고 UI 레이블도 `Last confirmed position` / `RUNNING target` /
   `In-progress leg`로 쓴다. 물리 pose 보간을 주장하지 않는다 — 보간은 UGV route 상의 거리 기반
   보간까지 끌고 와 범위를 넘긴다.

4. **"동일 Figure"는 테스트 기준이 될 수 없다.** 실측: `Figure == Figure`는 identity 비교라
   **False**다. PNG·PDF 바이트는 이 환경(matplotlib 3.10.9)에선 우연히 일치했지만 버전·font·
   backend·metadata·antialiasing에 따라 환경마다 달라질 수 있어 계약 기준으로 부적합하다.
   결정론의 대상을 **`RenderSpec`**(node id → 좌표·색·모양, edge 목록)으로 옮긴다. 공개
   렌더러는 계속 `Figure`를 반환하고, spec을 만드는 helper를 테스트한다. artist `gid`에
   task·edge id를 넣어 발표 그림을 사후 대조할 수 있게 한다.

5. **degrade는 모듈 import 실패까지 견뎌야 한다.** `demo/app.py`가 `demo/visualization.py`를
   top-level에서 import하고 그 모듈이 top-level에서 matplotlib을 import하면, degrade 분기에
   닿기도 전에 앱이 죽는다. 함수 호출 실패가 아니라 **matplotlib 부재를 흉내 낸 import 실패**
   상태에서 UI가 기동되는지를 테스트로 고정한다.

**영향** `core/route_graph.py`(read-only 경로 API 1개 추가), 신규 `demo/visualization.py`,
`demo/app.py`, `tests/test_route_graph.py`, 신규 `tests/test_visualization.py`,
`tests/test_demo_app.py`. `allocation/`·`execution/`·`interaction/`·`evaluation/` 무변경.
새 지표·새 주장 없음, P3/P4/P9 수치 불변, `VALIDATOR_VERSION` 1.4 불변.

구현 순서: D-044 → DAG `RenderSpec` → DAG `Figure` → DAG UI 연결 → `RouteGraph` 경로 API →
2D `RenderSpec`/`Figure` → 발표 PNG/PDF.

## D-045: `gid` 감사 문구 정정 (계약 v1.42, 문서 전용)

**D-044의 한 문장을 정정한다.** D-044 본문은 append-only 규칙에 따라 그대로 둔다.

**배경** P8.5b 구현 중 확인된 사실. D-044 §18.14는 "그림의 artist에는 task id·edge id를
`gid`로 넣어 **발표 그림을 사후에 대조**할 수 있게 한다"고 썼다. 이는 기술적으로 사실이
아니다 — `gid`는 메모리상의 matplotlib artist 속성이고 **PNG는 이를 보존하지 않으므로**,
저장된 발표 그림 파일을 파싱해 node·edge를 감사할 수 없다.

실제로 검증 가능하고 P8.5b가 구현한 경계는 다르다: **저장 직전 `Figure`의 artist `gid` 집합을
그 그림을 만든 `RenderSpec`과 대조**하는 것이다. `tests/test_visualization.py`가 그렇게
검사한다.

**결정** 계약 v1.42. §18.14의 해당 문장을 다음 의미로 바꾼다.

> artist에 task id와 edge id를 `gid`로 부여해 저장 직전 matplotlib `Figure`의 artist 집합을
> 해당 `RenderSpec`과 대조한다. PNG는 `gid`를 보존하지 않으므로, 저장된 PNG 파일 자체를
> 파싱해 node·edge를 감사한다는 의미가 아니다. SVG는 element id를 보존할 수 있으나 SVG
> 산출은 P8.5 범위 밖이다.

§15 P8.5 게이트 행의 `gid` 항목에도 같은 한정을 붙인다.

**영향** 문서만. renderer 코드 변경 없음, 새 주장·지표 없음, `VALIDATOR_VERSION` 1.4 불변,
P3/P4 골든(359.8385 / 257.8505)과 P9 수치 불변.

## D-046: checkpoint 구간 2D playback (계약 v1.43)

**배경** P8.5 정적 지도는 계획·paused runtime·완료 실행을 정직하게 구분하지만, 발표 화면에서
UAV/UGV가 실제로 이동하는 과정과 checkpoint에서 들어온 새 명령이 다음 구간 assignment를
바꾸는 장면은 보여주지 못한다. 사용자는 숫자와 polyline뿐 아니라 움직임을 직접 확인할 수 있는
운용자 콘솔을 요구했다.

**결정** P8.5에서 제외했던 애니메이션을 P10으로 별도 추가한다. 범위는 기존 P9가 보장하는
연속 task-completion checkpoint 사이의 playback뿐이다. action 전후 frozen
`ExecutionCheckpoint`에서 simulation-time frame spec을 만들고, UAV는 직선, UGV는 기존
shortest-path polyline의 lane weight 누적 거리로 보간한다. travel과 dwell을 구분한다.

simulator는 playback보다 먼저 다음 checkpoint를 원자적으로 commit한다. playback은 그 결과를
보여주는 순수 view이며 실행 clock·할당 알고리즘·감사 event가 아니다. UI는 동기 playback 중
입력을 받지 않고, 끝난 checkpoint에서만 새 명령을 받아 기존 bidder-connected selective
release/rebid를 수행한다. 따라서 "임무 수행 중 입력"은 임의 물리 시각 interrupt가 아니라
**결정론적 completion checkpoint에서의 입력**이라는 기존 P9 경계를 보존한다.

**제외** 실제 telemetry, continuous physics, acceleration/turning dynamics, RUNNING task abort·
migration, 임의 wall-clock interrupt, background thread simulator, animation wall-clock 성능을
연구 지표로 쓰는 것. playback off/배속은 표시 선택일 뿐 실행 결과를 바꾸지 않는다.

**실패 정책** spec/renderer/matplotlib 실패는 이미 commit된 execution을 rollback하지 않는다.
오류를 표시하고 정적 Runtime 지도·표로 degrade한다. 같은 snapshot·frame 수의 결정론은 이미지
바이트가 아니라 immutable `PlaybackSpec`으로 검사한다.

**영향** 신규 `demo/animation.py`, `demo/visualization.py` playback renderer,
`demo/app.py` UI 연결, `core/route_graph.py` read-only lane weight 조회, 관련 단위/AppTest.
`allocation/`·`execution/`·`interaction/`·`evaluation/` 의미 불변. `VALIDATOR_VERSION` 1.4와
`ONLINE_POLICY_VERSION`, P3/P4/P9 수치 불변.

## D-047: playback 마지막 frame과 정적 Runtime marker 구분 (계약 v1.44)

**D-046을 보정한다.** 첫 spec 회귀 테스트에서 "마지막 frame은 after checkpoint의 정적 runtime
의미와 일치"를 agent 좌표 동일성으로 해석하자 reference 첫 checkpoint에서 바로 모순이
재현됐다. `THERMAL_RECON__FIRE_SITE_1`이 완료되는 시각에도 S2는 다른 thermal task를 계속
dwell 중이다. P8.5 정적 Runtime 지도는 보간 범위 밖이므로 S2를 출발점인 마지막 확정 위치에
두지만, P10 playback은 S2를 기록된 schedule에 따라 task target에 둔다.

마지막 frame에서 둘을 강제로 같게 만들면 S2가 target에서 출발점으로 순간이동한다. 따라서
일치 게이트는 after checkpoint의 simulation time·RUNNING task·travel/dwell activity로 좁히고,
완료 agent의 위치만 확정 target과 맞춘다. 계속 RUNNING인 agent의 보간 위치가 정적 Runtime
marker와 다른 것은 의도된 차이다. D-046의 나머지 범위와 실패 정책은 불변이다.

**영향** 계약·테스트 의미 정정. 실행/할당/감사 코드와 버전·수치 불변.

## D-048: checkpoint 재생과 끝까지 연속 재생 분리 (계약 v1.45)

**배경** P10 첫 UI는 `다음 task 완료까지 계속` 한 버튼만 제공했다. 사용자가 첫 구간을 재생해
보니 일부 agent가 목적지에 도착하기 전에 화면이 멈춘 것으로 보였다. 실제로는 전역에서 가장
이른 다른 task가 완료되어 정상 checkpoint에 도달한 것이지만, UI가 정지 원인과 계속 RUNNING인
agent를 설명하지 않아 전체 임무가 중단된 것처럼 읽혔다.

**결정** 목적이 다른 두 동작을 분리한다.

1. **다음 checkpoint까지 재생**: 기존 P9/P10 의미를 그대로 유지한다. 가장 이른 completion
   event에서 멈추고 정지 원인 task를 표시한다. 그 시각의 다른 RUNNING agent는 schedule상
   `TRAVEL` 또는 `DWELL`인지 계산해 `중 일시정지`로 표시한다. 여기서 후속 자연어 명령과
   selective release/rebid가 가능하다.
2. **끝까지 연속 재생**: 같은 `advance_online_session()`과 구간 playback을 terminal까지
   반복한다. 구간 사이 입력 control은 렌더하지 않는다. 예외·`DEADLOCK`·`STEP_LIMIT`에서
   멈추며 자동 retry하지 않는다. 기존 checkpoint/execution 감사 event는 하나도 생략하지 않는다.

두 번째 모드는 편의를 위한 presentation control이지 다른 executor나 새 연구 결과가 아니다.
중간 명령을 시험하려면 첫 번째 모드를 사용해야 한다. one-shot 버튼도 기존처럼 보존한다.

**영향** `demo/app.py`, `tests/test_demo_app.py`, README/CLAUDE UI 설명. allocation/execution/
interaction 알고리즘·감사 schema·`VALIDATOR_VERSION`·`ONLINE_POLICY_VERSION`과 모든 결과 수치
불변.

## D-049: native operator console과 별도 simulator 창 (계약 v1.46)

**배경** Streamlit UI는 P8~P10의 연구 경로와 감사 정보를 검증하기에는 충분하지만, 대화·JSON·
표·DAG·2D 지도가 한 긴 웹 문서에 쌓인다. 발표에서 가장 중요한 agent 이동과 online update의
경로 변화를 작은 embedded plot과 긴 스크롤로 보여주면 운용 시스템보다 디버그 대시보드처럼
읽힌다. 사용자는 브라우저가 아닌 운용 UI 하나를 실행하고 2D simulator가 별도 창으로 뜨는
형태를 요청했다.

**결정** P11 presentation client를 추가한다. `python3 -m desktop`은 한 Qt application에서
`Operator Console`과 `Mission Simulator` 두 top-level window를 열며, 두 창은 동일한
`MissionSession`을 공유한다. controller는 기존 P8 orchestrator, P9 online action, P10 frozen
playback spec과 감사 writer만 호출한다. simulator는 spec을 Qt graphics로 그릴 뿐 allocation,
Validator, executor clock이나 경로 탐색을 복제하지 않는다.

checkpoint 재생과 연속 재생의 의미는 D-048과 같다. frame 재생 중 command control은 잠기고,
checkpoint에 도달한 뒤에만 후속 명령을 받아 selective release/rebid한다. Streamlit은 자동
회귀·세부 감사·fallback용으로 그대로 남긴다. Qt binding은 `PySide6` 선택 dependency이며 headless/offscreen
테스트를 둔다. executable packaging, 실제 telemetry, 임의 시각 interrupt, 3D/Gazebo는 이번
범위가 아니다.

**영향** 신규 `desktop/` presentation package, `pyproject.toml` desktop extra, 데스크톱 UI
테스트와 사용 문서. `core/`·`validator/`·`allocation/`·`execution/`·`interaction/`·
`evaluation/` 의미와 `VALIDATOR_VERSION` 1.4, `ONLINE_POLICY_VERSION`, P3/P4/P9 결과는 불변.

## D-050: editable install의 PEP 660 빌드 백엔드 하한 보정 (계약 v1.46, 패키징 수정)

**배경** P11 설치 안내의 `python3 -m pip install --user -e '.[desktop]'`를 Ubuntu 22.04의
배포판 pip 22.0.2 환경에서 실행하면 editable 설치가 거부됐다. 상세 로그에서 build isolation은
setuptools 84.0.0을 설치했고 그 backend에는 실제 `build_editable` hook이 있었지만, 배포판 pip가
이를 지원하지 않는 것으로 판정했다. 별개로 기존 `[build-system]`의 `setuptools>=61` 하한도
PEP 660 editable backend를 보장하지 않았다.

**결정** `[build-system].requires`의 setuptools 하한을 PEP 660 editable 지원 경계인
`setuptools>=64`로 올린다. Ubuntu 배포판의 구형 pip 경계를 피하도록 설치 절차는 먼저
`python3 -m pip install --user --upgrade pip`를 수행한다. runtime dependency와 `desktop`
extra의 의미는 바꾸지 않는다. 사용자 pip 26.2.1에서 build isolation → editable wheel 생성 →
`llm-mrta` 설치가 실제로 완료되는지 확인한다.

**영향** `pyproject.toml` 빌드 도구 하한과 사용 문서의 최신 결정 표기만 변경한다. 연구 계약
v1.46, 알고리즘·감사 schema·Validator/online policy 버전과 P3/P4/P9 결과는 불변이다.

## D-051: LLM-driven incident contingency와 simulated observation (계약 v1.47)

**배경** P11 native UI에서 mock에 임의 문장을 입력해도 reference 12-task graph가 나와 고정
시나리오처럼 보였고, live의 "UAV 한 대로 정찰"은 resource constraint가 schema에 없어 정직하게
UNSUPPORTED됐다. 발표 목표는 (1) UAV 순찰 완료 뒤 화재 observation으로 대응 임무가 생기는
경로와 (2) 실행 중 "Warehouse에서 불이 났어" 같은 자연어 보고가 필요한 assignment를 바꾸는
경로다. 기존 계약은 자동 perception과 조건부 graph를 제외하고 REPORT를 scene-only로 고정해
이 목표를 구현할 수 없다.

**결정** 일반 perception·임의 조건식은 열지 않는다. P12에서 LLM이 `NEW_MISSION`의 초기 graph와
별도로 고정 event `FIRE_DETECTED`의 workflow prefix를 추출하고, `REPORT_INCIDENT`에서는 zone과
선택 response step을 추출한다. strict latent fixture가 `AREA_RECON` 완료 checkpoint에서 simulated
observation을 한 번만 공개한다. sensor/operator 입력은 같은 atomic incident transaction과 기존
Validator/P9 selective release를 사용한다. 초기 command·response step·reported zone을 바꾼
counterfactual Live 평가로 결과가 입력에 민감함을 보인다.

**제외** 실제 영상·열화상 인식, confidence 추정, 임의 wall-clock interrupt, RUNNING migration,
일반 event-condition language, LLM 직접 좌표·priority·agent·release 결정. 특정 agent나 agent 수
제약은 별도 계약 없이는 지원하지 않고 무시하지도 않는다.

**영향** interaction intent/session/audit 확장, strict patrol/latent fixture, 공통 incident
transaction, evaluation과 native UI. 기존 `industrial_park.yaml`, P1 reference fixture,
Validator 1.4, online policy 1.0, P3/P4/P9 결과는 불변이어야 한다.

## D-052: strict intent repair와 한국어 zone 조사 경계 (계약 v1.48)

**배경** 사전 고정한 P12 첫 Live counterfactual에서 8개 중 4개가 exact match였다. 두
`NEW_MISSION`은 model이 선택한 kind에 속하지 않는 `note`/`zone_ref`를 비-null로 채워 strict
wire cross-field validation에서 거부됐고, 두 operator report는 `Warehouse에서`와
`Tank Farm에서`를 그대로 추출해 deterministic zone grounder가 clarification했다. 이 4/8은
프롬프트와 한국어 입력 경계의 실제 첫 결과이며 숨기거나 덮어쓰면 안 된다.

**결정** strict schema는 유지한다. live/cached intent wire의 첫 `ValidationError`에만 같은
발화·context와 오류를 넣은 correction을 정확히 한 번 허용한다. 두 번째 schema 오류와 다른
예외는 `TURN_ERROR`이며, 코드가 slot을 삭제하거나 reference graph/intent로 대체하지 않는다.
mock은 exact script wiring을 검증하므로 repair하지 않는다. `normalize_zone_ref`만 끝의 위치 조사
`에서`/`에` 하나를 제한적으로 제거한 뒤 기존 zone suffix를 처리하며 incident normalization은
바꾸지 않는다. prompt/cache 의미가 달라지므로 `PROMPT_SCHEMA_VERSION`을 `p12-v2`로 올린다.

첫 Live 4/8 artifact는 역사적 결과로 영구 보존한다. 개선 후 headline은 그 결과를 보기 전에
커밋한 별도 held-out paraphrase annotation에서만 산출하고, 원 명령 재실행은 regression으로만
표시한다. 이 변경은 LLM 역할·허용 intent·Validator·CBBA·online release 의미를 넓히지 않는다.

**영향** interaction intent prompt/repair, zone-reference normalization, cache namespace,
counterfactual evaluation 문서와 테스트. `VALIDATOR_VERSION` 1.4와
`ONLINE_POLICY_VERSION`, P3/P4/P9 골든은 불변이다.
