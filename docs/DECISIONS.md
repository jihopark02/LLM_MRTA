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
