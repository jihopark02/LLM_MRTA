# CLAUDE.md — LLM_MRTA

이 저장소에서 작업하는 Claude Code를 위한 최상위 지침이다.

**코드를 작성하거나 어떤 결정을 내리기 전에 `docs/RESEARCH_CONTRACT.md`를 반드시 먼저
전부 읽는다.** 이 문서가 단일 진실 원천이다. 설계 결정 이력은 `docs/DECISIONS.md`
(D-001부터), 이식 코드 등록부는 `docs/PROVENANCE.md`.

## 이 프로젝트가 무엇인지 (한 줄 요약)

MP4MR(김연주 외, J. ICROS 2025)을 구조적으로 참고한, 이종 UAV/UGV 재난 대응 임무에 대한
LLM 기반 task graph 생성 + 결정론적 Validator 검증 + CBBA 할당 연구. `/home/jiho/LLM_CBBA`와
**완전히 독립적인 프로젝트**다 — 그 저장소의 Git 이력, 연구 계약(SPEC/CLAUDE/AGENTS/ROADMAP/
DECISIONS), task 어휘, UAV dataclass, domain invariant, prompt, scenario, world, 결과값을
가져오지 않는다. 재사용하는 건 알고리즘 패턴뿐이고, 재사용할 때마다 `docs/PROVENANCE.md`에
왜 재사용하는지 먼저 기록한다.

## 세션 시작 체크리스트

1. `docs/RESEARCH_CONTRACT.md` 통독 — 특히 §1(연구질문), §9(Validator invariant),
   §10(MissionPatch/reconciliation), §11(CBBA epoch/scoring), §15(구현 순서/게이트)
2. `docs/DECISIONS.md`에서 최신 항목 확인 (현재 D-068, 계약 v1.64)
3. `docs/PROVENANCE.md`에서 지금까지 이식된 코드가 있는지 확인
4. `README.md`의 "현재 단계" 확인

## 지금 어디까지 왔는지 (2026-09-08 기준)

**P1~P6.5 승인 완료 (태그 `v0.6.5-baseline`, `main`은 여기서 동결). P8.0~P8.5,
P9.0~P9.4, P10, P11, P12.0~P12.7과 P13.0~P13.3 완료 (브랜치
`feature/operator-interaction`). 계약 v1.64, 최신 결정 D-068.**
`validator/`(P2) + `allocation/`(P3) + `execution/`(P4) + `llm/`(P5) + `evaluation/`
(P6 평가 + P6.5 `integration.py`) + `interaction/`(P8.1 grounder + P8.2 orchestrator).
`VALIDATOR_VERSION = "1.4"` (D-027), `λ = 0.999`. pytest 933개 통과, ruff clean.

**발표 시각화 (진행 중)**:
- `d3ad6d1` — `render_mission_map(minimal=True)` + native simulator `minimal` 뷰 = MP4MR-clean 할당 스캐터.
- D-062 (`d0828e3`) — seeded latent fire field. `scenarios/latent.py`의 `LatentFireField` /
  `SimulatedFireField`, 고정 spec `scenarios/response_district_latent.yaml`(seed 99, count 2),
  native `district-latent-fire` 프로파일. 지형은 고정, seed가 정하는 건 화재 zone뿐.
- D-063 (`f21ddee`) — 재생 중 명령을 `queued_commands` FIFO로, safe boundary마다 1건씩 소비,
  `cancel_queued`로 미소비 항목 취소.
- D-064 (`e56235b`) — P13.4 continuous tick driver. `demo.animation.SegmentView.frame_at`이
  구간 내 임의 sim-time pose를 주고, `desktop.controller.ContinuousRuntime`이 QTimer tick으로
  구동. "끝까지 연속 재생"이 이 경로, "다음 checkpoint"는 기존 frame-list 재생 유지.
- D-065 (`294693c` 계약, `98ca80f` 코드) + D-066 (`86b79dc` 계약) — §22.8 sensor 화재 감지
  승인 게이트. `SimulatedFireField`가 공개하는 `FIRE_DETECTED`는 자동 대응 안 하고
  `session.pending_approvals` FIFO 큐(zone id 순)에 들어가 무조건 운용자에게 되묻는다.
  `PendingClarification`류 resumable pending(새 phase 없음), 결정론적 승인/거절(LLM 없음 —
  사용자와 논의 후 확정). **D-066/D-067: 감지 시 clock 안 멈춤** — 운용자 답은
  `record_fire_decision`으로 기록만 되고 다음 boundary의 `apply_recorded_fire_decisions`에서
  적용(rewind 없음). **유예 = 남은 recon 전체**(D-067): 미결정 화재는 recon 진행을 안 막고,
  recon terminal에 미결정이면 그때만 halt, recon 종료 후 답하면 follow-on episode.
  `interaction/observe.py`의 `enqueue_fire_approvals` / `record_fire_decision` /
  `apply_recorded_fire_decisions` / `has_undecided_fire`, `controller.apply_pending_fire_decisions`.
  operator 창 승인 패널(진압까지/점검만/거절). 단일 `SimulatedFireSource`·운용자
  `REPORT_INCIDENT`는 게이트 밖.
- 데모 scene 3개(`patrol_park`·`response_district`·`response_district_patrol`)에서 G1·G2
  둘 다 `R_DEPOT` (`c7f2632`). `industrial_park`는 P3/P4 골든 때문에 G2@R_C 유지.
- D-068 (`bf50753` 계약, `60ae4a1` 코드) — (A) §22.7.1 상시 운용 콘솔: terminal 뒤
  `NEW_MISSION`("전체 재정찰")·`UPDATE_RESOURCES` 수용 → 새 mission episode(새 graph, UAV
  위치 이어받기, UGV 기지 재시작, 이전 `ExecutionAudit` 보존). "임무 완료" 종착점 제거, UI는
  "대기" 표시. 반복 순찰 task는 여전히 미구현. (B) §3 `IncidentStatus.RESOLVED` — 
  `GROUND_SUPPRESSION` 완료 시 incident RESOLVED, 지도에서 흐린 회색 X.
- 후속: 없음. 발표 리허설 + 지도교수·Codex 리뷰 — 커밋은 `de61780`(v1.57 재-baseline)부터 순서대로.

**D-060+D-061 re-baseline (아래 D-060/D-061 항목 참조)**: fleet 동일 UAV 3대 + UGV 2,
vocabulary 3종(`AREA_RECON` / `GROUND_INSPECTION` → `GROUND_SUPPRESSION`). 결정론적 골든
(P3 150.766 / P4 149.920 / P9 0·3·4)과 전체 테스트·계약 커밋 완료(`de61780` = 계약, 후속
= 코드). LLM 평가(P6 / P8.4 / P12 counterfactual / P13)는 **아직 새 어휘로 재실행하지
않았다** — 기존 `docs/P6_RESULTS`·`P8_4_RESULTS`·`P12_RESULTS`·`p12_counterfactual*`·
`P9_RESULTS` 본문은 5종/fleet v1 기록이다.

P12 (§22, D-051/D-052): 자연어 `NEW_MISSION`이 초기 graph와 별도 future-incident response
policy를 만들고, strict simulated `FIRE_DETECTED` 또는 실행 중 자연어 `REPORT_INCIDENT`가
같은 atomic incident transaction → Validator → P9 selective reallocation으로 수렴한다.
첫 Live engineering-feedback set은 4/8이고 보존한다. 그 결과 뒤 별도로 사전 커밋한 held-out
paraphrase는 `gpt-5-mini-2025-08-07`에서 8/8 exact, 실행 case 전부 COMPLETED·위반 0이다.
같은 시험의 전후 개선으로 주장하지 않는다. D-052는 live/cached intent wire의 첫 strict
`ValidationError`에만 1회 schema correction을 허용하고 zone reference의 `에서`/`에`를
제한적으로 처리한다. strict schema·LLM 역할·Validator/CBBA 의미는 불변이며 cache prompt
schema는 D-055 이후 `p12-v4`. D-053은 intent repair attempted/recovered를 각 `TurnAudit`에 기록한다.
`docs/P12_RESULTS.md` 참고.

P12.6 (§22.6, D-054): native UI는 initial commit 뒤 자동으로 checkpoint segment를 재생한다.
재생 중 자연어 한 건은 presentation queue에만 들어가며 LLM/turn을 아직 소비하지 않는다. frozen
segment 종료 후 같은 safe checkpoint의 sensor observation을 먼저 반영한 상태에서 기존
`handle_turn`으로 정확히 한 번 처리하고, 성공이면 다음 segment를 자동 재생한다. 일반 UAV/UGV
platform 표현은 workflow 설명으로 허용하지만 agent id·대수·배제 제약은 계속 UNSUPPORTED다.

P12.7 (§22.7, D-055): 유한 recon-only graph가 online `COMPLETED`로 끝난 뒤에도 terminal
checkpoint가 보존돼 있으면 새 `REPORT_INCIDENT`와 그 incident의 canonical UPDATE를 받는다.
scene-only report는 terminal을 유지하고, response task가 commit되면 기존 COMPLETED prefix·
simulation time·agent 위치를 보존한 채 `EXECUTION_PAUSED`로 새 episode를 열어 native auto-run이
재생한다. 이전 `ExecutionAudit`은 event stream에 남는다. one-shot/실패 terminal/NEW는 계속
거부한다. `정찰만`은 future-fire policy가 아니며 intent prompt와 cache를 `p12-v4`로 격리했다.

P13.1 (§23, D-056): `NEW_MISSION`의 Live intent wire가 UAV/UGV exact·min·max와
required/excluded agent를 strict하게 보존한다. `allocation/team.py`는 LLM이 assignment를
정하지 못하게 하고, 가능한 active-team subset을 기존 `allocate()`로 전수 검증해 결정론적으로
선택한다. 불가능하거나 scene에 없는 agent 제약은 full fleet fallback 없이 거부한다. 제약 없는
명령은 기존 full-fleet allocation과 정확히 같은 경로를 사용한다.

P13.2 (§23, D-057): 별도 `UPDATE_RESOURCES` 또는 `REPORT_INCIDENT`와 함께 resource request를
받는다. session/runtime `MissionState.agents`는 전체 scene fleet roster를 보존하고,
`active_team`은 새 CBBA 입찰·dispatch 자격만 나타낸다. resource 변경은 checkpoint clone에서
잔여 mission을 rollout해 feasibility를 확인한 뒤 현재 checkpoint만 atomic commit한다. 제외된
RUNNING agent는 현재 commitment를 마치지만 즉시 새 입찰에서 빠지며, 관련 미시작 bundle suffix만
release/rebid한다. 실패하면 runtime·clock·graph·policy identity가 보존된다. cache namespace는
`p13-v2`.

D-060 (§5, 계약 v1.56) + D-061 (§4, 계약 v1.57): **대규모 re-baseline**. D-060은 UAV를
동일 기체 3대로 통합(Scout/Response 분리 폐기, agent id S1/S2/R1/R2 → U1/U2/U3). D-061은
task vocabulary를 5종 → **3종**으로: `THERMAL_RECON`(승인 게이트가 대체)·`SUPPRESSANT_DROP`
(UAV는 정찰 전담) 제거. workflow는 `GROUND_INSPECTION → GROUND_SUPPRESSION` 2단계.
capability: UAV `{AERIAL_RECON}`, UGV 불변. `VALIDATOR_VERSION` 1.4 유지. 이종성 = UAV(공중
정찰, 직선) vs UGV(지상 대응, route graph). 새 골든: P3 allocate 150.766 / P4 exec 149.920 /
P9 release no-reset 0·selective 3·full-reset 4. `industrial_park`·`patrol_park`·`reference_fixture`
·`response_district*`·prompts·schemas·enums·compiler·workflow·whole_graph·P6 annotation 9개·
P8.4 dialogue 12개·p12 fixture 갱신. pytest 899 green, ruff clean. **P6/P8.4/P12/P13 LLM
평가는 아직 새 어휘로 재실행하지 않음** — 기존 RESULTS는 5종/fleet v1 기록.

D-059 (§3.1, 계약 v1.55): 발표·CBBA 시각화용 확장 reference scene을 허용한다. 동일
vocabulary·fleet 2/2/2·workflow·Validator 규칙, zone·incident·route node 수만 증가.
`scenarios/response_district.yaml`(8 zone / 5 incident) + `_fixture.yaml`(task 28)로 §18.14
그림을 뽑고(`presentation/render_scene_figures.py`), incident-empty 변형
`response_district_patrol.yaml`은 native UI의 `dynamic-district` world profile로 라이브 데모에
쓴다. `industrial_park`·P3/P4 골든·게이트·기본 profile(`patrol_park`)은 불변. 이 scene에서 평가
수치를 만들지 않는다.

P13.3 (§23.3.1, D-058): native 기본값은 `dynamic-world + live`다. `patrol_park`의 zone·fleet·
route만 로드하고 incident, initial graph, latent fixture, mock script를 넣지 않는다. scripted
sensor/operator/reference profile과 mock mode는 재현용으로 명시 선택한다. Live API/network/schema
실패는 TURN_ERROR/REJECTED로 감사하며 mock/reference mission으로 fallback하지 않는다. 다음은
P13.4 continuous runtime이고 P14 Gazebo는 미구현이다.

**P8 = Operator–LLM Planning Session (§18, D-027)**: 최초 범위는 실행 개시 전 다중 턴
자연어 계획 세션이며, 후속 P9가 이를 task-completion checkpoint의 온라인 명령으로 확장했다.
6종 대화 행위(NEW_MISSION/REPORT_INCIDENT/UPDATE_MISSION/UPDATE_RESOURCES/
QUERY_STATUS/UNSUPPORTED). LLM은
intent 분류 + slot 추출만, 결정론적 grounder가 referent 해석·clarification·canonical
MissionPatch 생성, `apply_patch`(P2 기존 엔진)가 atomic commit/rollback. 실행 중 patch·선택적
재할당은 P9에서 구현했고 recheck 어휘는 여전히 후속이다. 신규 `interaction/*` +
`demo/app.py`(Streamlit). P8.0~P8.4의 연구 경계는 기존 core/allocation/execution 의미를
바꾸지 않으며, P8.5는 시각화용 `RouteGraph` read-only 조회만 추가했다. 게이트는 §15.

P8.1 구조 (D-027, D-028):
- `interaction/schemas.py`: 내부 진실 원천은 strict·`kind` discriminated
  `OperatorIntent`(6종) + `IntentEnvelope`. 실제 API 경계는 D-034의 평면
  `IntentWireEnvelope`를 거쳐 결정론적으로 내부 union으로 변환한다(OpenAI가 중첩 `oneOf`
  거부). `NewMissionIntent`는 incident policy와 P13 resource request 외 graph 슬롯이 없고
  raw utterance는 `generate_mission`으로 전달된다.
  슬롯은 전부 optional(부분 추출), **CLARIFICATION 멤버 없음**.
- `interaction/session.py`: `SessionPhase`{PLANNING,EXECUTED,EXECUTION_FAILED},
  `ReferentKind`/`Referent`(scene 멤버십 검증), `MissionSession`(plan·execution 분리),
  referent window K=3, `fresh_session_state`(scene의 mutable Agent 비공유),
  `build_context_summary`(결정론). `known_incident_ids`·context는 **derived**.
- `interaction/workflow.py`: `WORKFLOW_CHAIN` + Validator `WORKFLOW_PREDECESSOR`와 import 시
  일관성 assert.
- `interaction/scene_mut.py`: `register_incident` — ID `FIRE_SITE_<max n+1>`(malformed는
  카운터 제외·충돌 검사 포함), priority 고정 7, zone response point 사용, **원본 Scene 불변**.
- `interaction/ground.py`: **fail-closed** grounder(D-028) — zone alias 3형태, incident 해석
  5단계 우선순위, **허용 지시어 allowlist**(계약 §18.5 고정), 정규화 충돌 → clarification,
  정규화가 비는 ID는 명시 매칭에서 제외. `build_chain_patch` = canonical 연장만, 이미
  완성이면 **NO_CHANGE**(중복 AddTask·빈 patch commit 금지).
- Validator 1.4(P8.1b atomic cut): `AddTask` op `{task_type,target}`, field schema/conflict
  분리, `patch_hash`+`pre_state_hash`, zone response point가 `scene_hash`에 포함.

P8.2 구조 (D-029, D-030):
- `interaction/audit.py`: `TurnAudit`/`ExecutionAudit`/`GroundingAudit`/`PatchAudit`/
  `GenerationAudit`/`PlanAssignmentChanges` typed schema (`turn_log`은 event stream에서 파생한
  read-only tuple).
- `interaction/orchestrator.py`: `handle_turn` — **턴 전체** 예외 격리(backend가
  `generate_mission` Step1/2/repair나 `allocate` 안에서 죽어도 `TURN_ERROR`, 세션 불변),
  NEW/UPDATE는 candidate state+plan을 만든 뒤 **한 번에** 교체, `resolved_models`는 그 턴
  모든 backend 호출, 지시어 QUERY는 referent window 미갱신(D-029). backend mode는
  `_mode_of`가 `backend.mode`를 읽음(클래스명 비교 X) — 미선언은 배선 버그라 turn 소비 전
  `ValueError`.
- `interaction/audit_io.py`: `session_audit_payload`/`session_audit_json`/
  `write_session_audit` → `data/interaction_runs/<session_id>.json`. `event_type`으로
  구분되는 event stream(P8.3 `ExecutionAudit` 동일 스트림), `ensure_ascii=False`,
  `sort_keys`로 결정론.
- `llm/backend.py`: `LLMBackend` Protocol에 `mode: str`, `MockBackend`="mock",
  `OpenAIBackend`="live".
- `interaction/session.py`: `SESSION_ID_PATTERN` + `valid_session_id`(fullmatch) — id가
  파일명이 되므로 생성자에서 강제(D-030), `audit_path`도 공유.

P8.4 (§18.11): 사전 고정 12-dialogue / 36-turn 평가. grounder-only dialogue exact 12/12,
실제 `gpt-5-mini-2025-08-07` end-to-end 6/12. clarification recall 3/3·wrong guess 0/3이나
precision 3/11이며, 한국어 조사 포함 slot과 금지 `note` 출력이 주 실패 원인이다.
`docs/P8_4_RESULTS.md`와 `data/eval_results/p8_4_*` 참고. 같은 12개를 사후 튜닝 결과의 새
headline으로 재사용하지 않는다.

P9 (§19, D-039~D-041): `SimExecutor` task-completion checkpoint/resume, **bidder-connected
selective release**, paused REPORT/UPDATE/QUERY, typed `CheckpointAudit`/
`OnlineReallocationAudit`, Streamlit 온라인 실행 버튼, no-reset/full-reset/selective 고정 비교까지
완료. 대표 fixture의 release 수 no-reset 0 / selective 3 / full-reset 4 (D-060+D-061), 세 정책 모두 COMPLETED·위반 0.
selective의 성능/최적성 우위가 아니라 **불필요한 release 범위 감소**만 주장한다.
**D-041/D-042**: §19.3 3단계의 bundle-suffix 확장은 **실증되지 않았다**
(`suffix_extra_release_count = 0`, `selective`에만 정의). D-061 이후 신규 incident의 즉시
READY는 `GROUND_INSPECTION`(UGV)뿐이고 recon은 UAV라, 한 agent bundle이 영향/비영향으로
섞이는 경로가 이 fleet+어휘에선 안 나온다(§19.3 재서술은 P9 재실행 시). suffix는 보수적
구현 규칙으로 남기고 단위테스트로 **분기만** 고정한다(end-to-end 실증 아님).
online advance **예외**는 runtime을 보존하므로 재개 가능하지만, `DEADLOCK`/`STEP_LIMIT` **결과**로
끝난 경우는 terminal이라 재개하지 않는다 — 재시도 조건은 `EXECUTION_FAILED` + runtime 있음 +
`execution is None`이다(§19.1 표, D-042). 평가 fixture는 strict schema로 읽는다(D-023과 동일).
`docs/P9_RESULTS.md`와 `data/eval_results/p9_online_reallocation.*` 참고.

P8.5/P10 시각화(§18.14, §20, D-043~D-047): `demo/visualization.py`가 결정론적 DAG와
plan/runtime/execution 정적 2D `RenderSpec`을 만들고, `demo/animation.py`가 연속한 frozen
`ExecutionCheckpoint` 사이의 immutable `PlaybackSpec`을 만든다. 온라인 실행은 먼저 다음
completion checkpoint를 commit한 뒤 그 구간을 재생한다. UAV는 직선, UGV는
`RouteGraph.shortest_path_nodes()` + `lane_weight()` polyline을 simulation time으로 보간하고,
task target에서 dwell한다. 재생은 순수 presentation view이고 실제 telemetry·동역학·임의
wall-clock interrupt가 아니다. 재생 중 받은 후속 명령은 queue에만 두고, 재생 완료 checkpoint에서
P9 selective release/rebid를 수행한다. matplotlib 부재/렌더 실패는 실행을 되돌리지 않고 정적
표로 degrade한다.
UI의 `다음 checkpoint까지 재생`은 가장 이른 completion마다 멈춰 정지 원인과 계속 RUNNING인
agent의 TRAVEL/DWELL 상태를 표시하고 중간 명령을 허용한다. `끝까지 연속 재생`은 같은 action을
terminal까지 반복하되 구간 사이 control을 렌더하지 않으며 오류에서 자동 retry 없이 멈춘다
(D-048).

P11 네이티브 UI(§21, D-049): `python3 -m desktop`이 하나의 `QApplication`에서 독립된 최상위
창 두 개를 연다. `desktop/window.py`는 자연어 명령·clarification·checkpoint/continuous control을
담당하는 Operator Console이고, `desktop/simulator.py`는 같은 세션의 `MapRenderSpec`과
`PlaybackSpec`만 소비하는 2D Mission Simulator다. `desktop/controller.py`는 Qt와 연구 로직
사이의 얇은 presentation controller이며 기존 `handle_turn`·candidate selection/cancel·
`advance_online_session`·audit writer만 호출한다. D-054 이후 initial commit은 자동 재생되고,
재생 중 input 한 건은 safe-checkpoint queue로 받는다. continuous 오류의 무자동재시도, terminal
경계, live/cached/mock provenance, PySide6
미설치 안내를 offscreen 테스트로 고정했다. Streamlit은 fallback으로 유지한다. P11은 새로운
할당·검증·실행 의미나 연구 주장을 추가하지 않는다.

다음은 P13.4 continuous wall-clock 2D runtime, 이후 P14 ROS2/Gazebo adapter 순서로
진행한다. P13.4 전까지 native 화면은
checkpoint schedule playback이며 robot telemetry로 주장하지 않는다.

P8.3 구조 (D-031~D-034, 계약 v1.32):
- **통합 `event_log: list[TurnAudit | ExecutionAudit]`** — list 순서가 event 순서의 유일한
  진실 원천. `event_seq`는 직렬화 시 `enumerate`로 파생(dataclass 필드 아님). `turn_log`는
  제거하고 read-only property로만. execution은 `turn_count` 미소비.
- **구조화된 후보 선택** — `PendingClarification`(typed, frozen; entity ambiguity에서만 생성).
  `select_clarification_candidate(session, entity_id)`는 LLM 없이 grounder 재경유 없이 처리하되
  감사되는 새 턴(`input_kind="CANDIDATE_SELECTION"`, `resumed_from_turn_id`, `selected_entity_id`).
  pending 중 자유 입력은 LLM 미전달·실행 버튼 비활성. 취소는 graph·scene·referent 불변.
- **`scenarios/naming.py`**(신규) — `normalize_identifier`/`normalize_zone_ref` 공유,
  계층 역전 방지. scene 로더가 정규화 빈 incident id 거부.
- P8.3 순서: 위 두 스키마 변경 먼저 → Streamlit UI → 실행 버튼 → `ExecutionAudit` 생산자 →
  live/cached/mock. §18.12 최소 표시 항목 1~14, `VALIDATOR_VERSION` 1.4 불변.
- `ClarificationReason`이 실제 entity ambiguity와 unknown/missing을 구분하며, pending은
  `AMBIGUOUS_ENTITY` + 나머지 필수 slot 완전 조건에서만 생성. 후보 선택·취소는 `mode`를
  명시적으로 받고 잘못된 선택·pending 중 자연어도 감사 턴으로 남긴다.
- 세션의 private append boundary가 event 순서를 소유한다. 실행 action은 COMPLETED뿐 아니라
  DEADLOCK·STEP_LIMIT·예외도 즉시 `ExecutionAudit`로 기록하며, `EXECUTION_FAILED`에서는
  동일 graph 재시도를 허용한다(D-032, D-033).
- `interaction/execute.py`: 결정론적 실행 버튼 경로. `llm/cache.py`: live 성공 응답 exact cache
  + cached-only 재생(모드 혼동 금지). `demo/app.py`: §18.12 14항목 Streamlit UI.
- D-034: actual API가 내부 discriminated union의 `oneOf`를 거부해 평면
  `IntentWireEnvelope`→내부 `OperatorIntent` adapter를 추가. 실제 한국어 3턴 모두 COMMITTED,
  최종 16 tasks / 9 edges, 실행 COMPLETED 404.0321 s, 위반 0/0. cached 재생도 동일.

workflow: `GROUND_INSPECTION → GROUND_SUPPRESSION` (D-061, 2단계)
(D-016, symbolic UGV 진압). 골든값 P3 makespan ~150.8 / P4 ~149.9 (D-060+D-061), violation 0.

P5 구조:
- `llm/schemas.py`: `Step1Output`/`Step2Output`/`RepairOutput` (pydantic,
  `extra="forbid"`+`strict=True` — D-019).
- `llm/backend.py`: `LLMBackend` Protocol, `MockBackend`(게이트용), `OpenAIBackend`
  (`chat.completions.parse`, `OPENAI_API_KEY` — env 또는 repo-root `.env`, `openai` 지연
  import = `llm` extra, `client` 주입 가능 — 테스트용). 평가 모델 `gpt-5-mini` 고정
  (reasoning model → `temperature` 미전달), 실제 resolved snapshot은 `resolved_models`에 기록(§14).
- `llm/prompts.py`: scene 어휘 + **task glossary(의미+담당 platform, D-020)** 주입
  Step1/Step2/repair 프롬프트.
- `llm/pipeline.py` `generate_mission`: Step1 → `from_raw` schema(오류 즉시 거부, **Step2
  호출 전**, D-019) → Step2 → `validate_candidate` → repair 1회 → 재검증 → 승인(+compiled
  graph) / 명시적 거부. backend의 `pydantic.ValidationError`는 명시적 SCHEMA 거부로 변환,
  다른 예외는 전파. `raw_candidate`/`raw_validation`과 최종 `candidate`/`validation`을
  분리 보존(D-019). reference fallback 없음.

P6 구조 (D-021, D-022):
- `data/reference_annotations/{A1..C3}.yaml`: 9개 canonical reference (LLM 호출 전
  커밋 `c3ed0f3`). family A=FULL_RESPONSE, B=AERIAL_ONLY, C=SELECTIVE_RESPONSE.
  priority 없음(D-022 파생).
- `evaluation/annotations.py`: 로더. chain은 §4 workflow 연속 prefix로 검증, 각
  allowed_graph를 로드 시 Validator로 self-check. 명시형 task는 `{task_type,target}` 엄격.
- `evaluation/metrics.py`: `task_key=(task_type,target)` = LLM이 생성하는 것 전부.
  `allowed_graphs` 중 (task F1, edge F1) 최대와 대조. `PRF.defined`(0/0 → N/A).
- `evaluation/harness.py` `run_all`: 9개 실행, `X/N` 동적 집계, raw·final 둘 다 채점 +
  `GraphSnapshot`(tasks/edges/graph_hash/accepted/error_codes 감사 저장), repair
  attempted/recovered/first-pass 분리, family 분해, 재현성 triple, backend 예외는
  `harness_error`(≠ `failure_category`).
- `evaluation/report.py`(표+감사 JSON), `evaluation/plots.py`(3-panel 그림, `viz` extra).
- 실행: `python3 -m evaluation [--mock] [--out PREFIX] [--plot]`.

P6 실측 (gpt-5-mini-2025-08-07, 2026-09-02, validator 1.3): 9/9 approved, task P/R
1.00/1.00, edge P/R 1.00/1.00(family A·C), exact match 9/9, repair 0회, latency mean
18.2s. `docs/P6_RESULTS.md`, `data/eval_results/`. 승인된 candidate는 invariant
**#1~#12** 만족(#13~#14는 patch 전용).

P6.5 (D-025, D-026): `evaluation/integration.py` `run_full` — NL → `generate_mission`
(RQ1) → 검증된 graph가 **fork**로 `allocate`(plan-time)와 `SimExecutor`(event-driven,
내부에서 CBBA 재수행 — allocate 결과 안 받음)에 각각. `FullRun`: `exact_match`(P6
`score_graph`) / `operationally_clean` / `demo_pass`. 감사 JSON = `GraphSnapshot`
(harness에서 공유) + graph_hash + resolved_models + plan·exec assignment(task→agent).
게이트(`tests/test_integration.py`): A1/B1/C1 demo_pass, A1은 graph_hash가 P1 fixture와
일치 → makespan P3/P4 골든(150.8/149.9, D-060+D-061) 일치, wrong-but-valid graph는 op-clean이나
demo_pass 아님. CLI `python3 -m evaluation.integration [--mock]`.


P4 구조:
- `execution/executor.py` `SimExecutor.run()` — clone 위 event loop: recompute → `run_epoch`
  (held 전달) → dispatch(predecessor COMPLETED면 이동) → advance(가장 이른 완료로 전진,
  arrival+dwell) → 반복. RUNNING task는 path[0]에 pin, 입찰은 착지 지점 기준. deadlock 판정
  직전 recompute 한 번 더(§14). `ExecutionResult`(§13 지표 + deadlocked).

P3 구조:
- `allocation/travel.py`: `leg_time`/`leg_distance` — UAV Euclidean, UGV route Dijkstra.
- `allocation/scoring.py`: `path_score`(Σ λ^completion·priority), `marginal_score`(best
  insertion, 비적격 → -inf). 이식(PROVENANCE), λ=0.999.
- `allocation/cbba.py`: `run_epoch` — bundle build + Table I action rule + s-vector +
  suffix release + `_beats` tie-break. 이식.
- `allocation/allocate.py`: `allocate()` — clone 위 epoch 반복(recompute→auction→plan-time
  sim→COMPLETED 표시), `AllocationResult`(§13 지표). 신규.

P2 구조:
- `validator/candidate.py`: raw candidate(list) — #1/#3 파싱, #2/#5-edge/#6/#7 consistency.
- `validator/whole_graph.py` `validate_structure(nodes, edges, scene)`: #4/#8/#9/#10/#11/#12.
  abstract (task_key, edge) view이므로 candidate와 post-patch graph 양쪽에 재사용.
- `validator/validate.py` `validate_candidate()`: LLM 파이프라인용, `ValidationResult`(§14
  graph_hash/scene_hash/validator_version).
- `validator/patch.py` `validate_patch_ops()`: §10 2단계(`E_PATCH_CONFLICT`), `post_patch_keys`.
- `validator/patch_apply.py` `apply_patch()`: §10 전체 절차, 트랜잭션(거부 시 원본 객체 그대로
  반환). `_reconcile`/`_predecessor_diff`/`_terminal_immutable_errors`는 단위테스트용 분리.
- **D-006**: reconciliation release 경로는 P2에서 단위테스트만. 고정 5종 어휘에선 어떤 유효
  patch도 기존 predecessor 집합을 못 바꾸므로 P8 첫 범위(§18)에서도 end-to-end 도달 안 함
  — recheck 계열 어휘 후속 확장 전까지는 도달하지 않는다(D-027). #13 terminal incoming
  불변은 P2에서 도달.
- **D-007**: assignment consistency invariant(§10 7단계, 규칙 1~4)를 `_assignment_invariant_errors`가
  강제. graph_hash payload에 priority 포함. `validate_patch_ops`가 op 필드를 런타임 검증.
  candidate schema가 허용 키를 정확히 제한.
- **D-008**: `VALIDATOR_VERSION "1.1"`(판정 규칙 변경 시 bump). priority 1..10 강제(§7).
  assignment 참조 무결성(§10 규칙 6 — bundle/path/winning_bids가 존재하는 task만 참조).
  rejected patch(whole-graph 전 거부)는 `graph_hash` 빈 문자열(§14).

P6 착수 시: 최소 9개 NL 입력(family당 3), family A(full)/B(aerial)/C(selective). 사람이 LLM
출력 보기 전에 canonical reference annotation을 고정(`task_key`/`edge_key`, 정답 복수 허용).
지표: schema-valid / raw·repair 후 whole-graph-valid count, task·edge precision/recall,
exact graph match, failure category, latency — 원시 개수 함께 제시. `data/reference_annotations/`.
`unnecessary_task_rate`는 별도 지표 안 씀(task precision의 FP). Validator가 "자연어 의미
충실도"를 보장한다고 서술하지 않는다(§9 — 그건 §12 precision/recall).

RQ1(LLM 복합 task graph 생성)과 RQ2(이종 UAV/UGV CBBA 할당)가 필수 범위다. RQ3(D-027):
P8 첫 범위는 **실행 개시 전 다중 턴 자연어 계획 세션**(§18) — 증분 graph 수정 + 결정론적
재검증 + atomic commit/rollback + clarification. "임무 실행 중 자연어 업데이트"와 "영향받은
commitment의 선택적 재할당"은 §18 후속(recheck 어휘 필요). 구현 전까지는 어디에도 "동적
재할당"을 완료된 결과로 쓰지 않는다.

**검토 구조**: Claude가 커밋 단위로 코드를 구현하면 Codex가 독립 검토한다. 커밋은 작게
쪼개고, 각 커밋 메시지에 어떤 게이트 항목을 만족시키는지 적는다.

## 작업 방식

**코딩 전에 생각한다.** 가정을 명시한다. 해석이 여러 개면 조용히 고르지 말고 제시한다.
더 단순한 방법이 있으면 말한다. 불명확하면 멈추고 무엇이 불명확한지 짚고 묻는다.

**단순함이 먼저다.** 문제를 푸는 최소 코드만. 요청하지 않은 기능·단일 사용처의 추상화·
설정 가능성·불가능한 시나리오의 에러 처리는 넣지 않는다. 200줄인데 50줄로 되면 다시 쓴다.
(RESEARCH_CONTRACT.md §16 cut-order, §17 범위 제외)

**수술적으로 고친다.** 건드려야 하는 것만. 인접 코드·주석·포맷을 "개선"하지 않는다.
망가지지 않은 걸 리팩터하지 않는다. 기존 스타일을 따른다. 관련 없는 dead code는 지우지
말고 언급만 한다. 내 변경으로 안 쓰이게 된 import/변수만 정리한다.

**검증 가능한 목표로 만든다.** "검증 추가" → "잘못된 입력 테스트를 쓰고 통과시킨다",
"버그 수정" → "재현 테스트를 쓰고 통과시킨다". 다단계 작업은 각 단계에 verify 기준을
붙인 짧은 계획을 먼저 말한다. §15 P1~P8 게이트가 이미 이 역할을 한다.

## 문서 갱신 트리거

- **단계 완료 시**: ① `README.md`의 "현재 단계" 갱신 → ② `CLAUDE.md`의 "지금 어디까지
  왔는지"와 최신 decision ID 갱신 → ③ 게이트 증거(테스트 결과 등)와 함께 커밋.
- **계약을 바꾸거나 아래 범위의 결정을 내릴 때**: `RESEARCH_CONTRACT.md`를 먼저 고치고
  버전을 올린 뒤 `DECISIONS.md`에 append, 코드보다 먼저 커밋.
- **`/home/jiho/LLM_CBBA`에서 코드/패턴을 재사용할 때**: `PROVENANCE.md`에 먼저 기록.

`DECISIONS.md`에 기록하는 것: 연구 질문·주장 범위, scenario/task/agent 변경, invariant,
score 수식, 평가 지표, 단계 게이트·범위 변경, 외부에 보이는 핵심 architecture 변경.

기록하지 않는 것(DECISIONS를 비대하게 만들지 않기 위해): 함수명, 파일 분리, 내부 helper
선택, 테스트 fixture 작성 방식, 포맷·사소한 구현 선택.

## 절대 하지 말 것

- `/home/jiho/LLM_CBBA`의 코드/문서 내용을 확인 없이 그대로 가져오기 — 재사용하려면 먼저
  왜 도메인 무관한 패턴인지 스스로 답하고 PROVENANCE.md에 기록
- Validator가 "자연어 의미 충실도"까지 보장한다고 서술하기 (RESEARCH_CONTRACT.md §9 참고 —
  이건 §12 평가 지표의 역할)
- RQ3 관련 기능을 P0~P6.5 완료 전에 구현하거나(D-027 — P7 Gazebo는 RQ3 선행조건 아님),
  구현 안 됐는데 구현된 것처럼 서술하기
- 실행하지 않은 실험 수치를 문서/주석에 넣기
