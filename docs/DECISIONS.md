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
