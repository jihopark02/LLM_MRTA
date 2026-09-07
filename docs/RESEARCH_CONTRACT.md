# RESEARCH_CONTRACT.md — 단일 진실 원천

버전 v1.42 (D-045). 이 문서와 코드가 충돌하면 이 문서가 우선한다. 변경 시 이 문서를 먼저 고치고
`docs/DECISIONS.md`에 이유를 append한다.

- v1.42 (D-045): D-044의 `gid` 문구 정정(문서 전용). "발표 그림을 사후에 대조"는 기술적으로
  사실이 아니다 — PNG는 artist `gid`를 보존하지 않으므로 저장된 파일을 파싱해 node·edge를
  감사할 수 없다. 실제로 가능하고 P8.5b가 구현한 경계는 **저장 직전 `Figure`의 artist 집합을
  그 `RenderSpec`과 대조**하는 것이다. renderer 코드 변경 없음, 새 주장·지표 없음.
  `VALIDATOR_VERSION` 불변(1.4).
- v1.41 (D-044): D-043 보정 5건 — 구현 전에 계약과 데이터 모델의 충돌을 없앤다. ①
  `TaskStatus`는 **6종**(`CANCELLED` 포함)이므로 renderer가 enum 전체를 처리한다. ②
  `RouteGraph`에 경유 node를 돌려주는 **read-only 조회 API**를 예외적으로 허용한다 — 없으면
  view가 Dijkstra를 재구현해야 해서 "연구 로직 비복제"와 충돌한다. ③ paused runtime의
  "현재 위치"는 정의되지 않는다(`agent.position`은 완료 시에만 갱신) — **마지막 확정 위치 +
  RUNNING target + dashed in-progress leg**로 표현하고 물리 pose 보간을 주장하지 않는다. ④
  결정론 기준을 Figure·이미지 바이트가 아니라 **`RenderSpec`**(node/edge/좌표/색/모양)으로
  옮긴다. ⑤ `viz` degrade는 **모듈 import 실패**까지 견뎌야 한다. `VALIDATOR_VERSION` 불변(1.4).
- v1.40 (D-043): P8.5 착수. 비어 있던 §15 P8.5 게이트를 채우고 §18.14(시각화)를 신설한다.
  범위는 **TaskGraph DAG + 정적 2D 임무 지도까지**이며 **애니메이션은 범위 밖**. 순수 view —
  `demo/visualization.py`가 matplotlib `Figure`만 반환하고 mission state를 바꾸지 않는다.
  **결정론적 layout**(같은 graph → 같은 그림)을 요구하고, 같은 renderer가 UI와 발표 그림의
  단일 진실 원천이 된다. `viz` extra 미설치 시 UI는 기존 표로 degrade한다(죽지 않는다).
  새 연구 주장 없음 — 이미 얻은 결과의 전달 수단이다. `VALIDATOR_VERSION` 불변(1.4).
- v1.39 (D-042): D-041 정정 2건. ① suffix 실증 범위를 **과도하게 단정**했다 — "모든
  reachable path에서 섞인 bundle이 불가능"은 증명되지 않았다. `build_chain_patch`는 신규
  incident의 전체 chain뿐 아니라 **기존 incident의 부분 workflow 연장**도 하므로, 예컨대
  `THERMAL_RECON`이 COMPLETED인 incident를 `SUPPRESSANT_DROP`까지 늘리면 신규 READY의 bidder는
  R1/R2가 되고 `AREA_RECON`은 비영향이 되어 S-agent bundle이 섞일 여지가 생긴다. 실제 도달
  가능성은 확인하지 않았으므로 "검증된 경로에서 관측되지 않았다"로만 쓴다. ② §19.1 표에
  `EXECUTION_FAILED` + `execution` **있음** + `runtime` 있음(온라인 `DEADLOCK`/`STEP_LIMIT`
  종료) 행이 빠져 있었고, 그 결과 재시도 게이트가 이 terminal 상태까지 재개해 phase를
  `EXECUTION_PAUSED`로 되돌리고 기록된 종료 결과를 지웠다. 재시도 조건을 **`execution is
  None`까지 포함**해 좁힌다. `VALIDATOR_VERSION` 불변(1.4).
- v1.38 (D-041): P9 재검토 반영. §19.3 정책명을 **bidder-connected selective release**로
  바꾸고 bundle suffix를 "mixed bundle 상태를 위한 보수적 구현 규칙"으로 격하 — 현재
  canonical online update는 새 incident의 `THERMAL_RECON`만 즉시 READY로 만들고, 그 bidder
  union은 UAV 전체이므로 어떤 agent도 영향/비영향이 섞인 bundle을 가질 수 없다. 따라서
  `released == directly_affected`가 되어 suffix 확장은 **실증되지 않았다**. §19.5의
  "bundle 길이가 suffix 차이를 만들지 못하는 checkpoint는 실험 fixture로 사용하지 않는다"는
  현재 fixture와 모순이므로 삭제하고, `suffix_extra_release_count`를 원시 지표로 보고한다.
  §19.1에 online 재시도 lifecycle(`EXECUTION_FAILED` + runtime 보존 → checkpoint 재개)과
  `(phase, execution, runtime)` 조합의 의미를 명문화. §19.5에 평가 fixture strict schema
  원칙 추가(D-023과 동일). `VALIDATOR_VERSION` 불변(1.4).
- v1.37 (D-040): P9 감사의 `preserved active assignment`를 **release되지 않았고 전후 owner도
  같은 commitment**로 명확히 한다. release 후 같은 agent가 다시 낙찰한 경우는 owner change
  0이지만 preserved로 세지 않는다. P9.4 고정 fixture·세 정책 결과와 온라인 Streamlit 경로를
  기록한다. whole-graph 판정 규칙은 불변이므로 `VALIDATOR_VERSION`은 1.4 그대로다.
- v1.36 (D-039): P8.4 완료 후 선택 확장 RQ4/P9를 추가한다. 실행은 결정론적 task-completion
  event에서 pause/resume하며, COMPLETED와 현재 RUNNING task는 보존한다. 새로 READY가 된
  task와 bidder set을 공유하는 아직 시작하지 않은 ASSIGNED task를 찾고, agent별 최초 영향
  task부터 bundle suffix만 release/rebid한다. 이는 결정론적 선택 정책이지 전역 최소·최적
  재할당 주장이 아니다. 신규 task type 없이 canonical incident chain 확장만 사용한다.
  `VALIDATOR_VERSION`은 1.4 그대로다.
- v1.35 (D-037): P8.4 patch gold에 §18.11이 원래 요구한 `accepted`와
  `directly_released_tasks`를 필수 필드로 명문화한다. canonical chain update의 정답은
  `accepted=true`, release 빈 목록이며 loader가 암묵 기본값 없이 이를 강제한다.
  `VALIDATOR_VERSION`은 1.4 그대로다.
- v1.34 (D-036): P8.4 gold에 `initial_graph`를 필수화한다. `final_graph`만 두면 첫
  `NEW_MISSION` 정답을 후속 patch에서 역산해야 해 생성 오류와 patch 오류를 독립적으로
  판별할 수 없다. strict loader는 initial/final graph를 각각 검증하고 기대 patch 합집합이
  두 graph의 정확한 diff인지 확인한다. `VALIDATOR_VERSION`은 1.4 그대로다.
- v1.33 (D-035): P8.4 interaction 평가의 12개 dialogue 구성을 고정한다. P6의
  A/B/C mission profile마다 `NEW-only`/`REPORT+UPDATE`/`QUERY`/`ambiguous-selection`
  한 건씩 두며, gold schema·strict loader·분모 규칙을 §18.11에 명시한다. 구조화된 후보
  선택은 operator/audit turn에는 포함하지만 LLM intent·slot 정확도 분모에서는 제외한다.
  Validator 판정 규칙은 바뀌지 않으므로 `VALIDATOR_VERSION`은 1.4 그대로다.
- v1.32 (D-034): P8.3 실제 API 검증에서 OpenAI structured output이 Pydantic
  discriminated union의 중첩 `oneOf`를 거부함을 재현했다. 내부 진실 원천은 기존의 strict
  `OperatorIntent` discriminated union으로 유지하되, API 경계에는 모든 slot을 nullable
  필수 키로 가진 평면 `IntentWireEnvelope`를 사용한다. wire schema의 kind별 slot 일관성을
  검증한 뒤 결정론적으로 내부 union으로 변환하며, 변환 전에는 grounder를 호출하지 않는다.
  `VALIDATOR_VERSION`은 불변(1.4), interaction prompt/schema cache version은 갱신한다.
- v1.0 (D-001): 초판.
- v1.1 (D-002): §15 P1 완료 게이트를 P1 구현 범위 전체를 검사하도록 강화하고, reference
  fixture의 고정 형상(task 12 / edge 6 / 초기 READY 6)을 §3에 명시.
- v1.2 (D-003): §7에 compiler 입력 경계(신뢰된 목록만; raw candidate는 Validator 선행)를
  명시. §6의 enum 직렬화 서술을 정정(`safe_dump` 불가, 경계에서 `.value`). incident
  `status: RESPONSE_REQUIRED`를 scene 데이터 필수 필드로 명시(§3).
- v1.3 (D-004): §8의 `travel_time` 예시를 `scene.agent_access_nodes` 기반으로 정정(core
  Agent에 `access_node` 없음). §8에 scene 로드 시점 검증 4종(incident access_node 존재,
  UGV 시작 node 존재, UGV task 도달성, `agent_id` 유일)을 명시.
- v1.4 (D-005): §10의 "operation 순서 무관" 주장을 정정 — diff reconciliation은 순서
  독립성을 보장하지 않는다. patch raw op 목록 self-일관성 검증(`E_PATCH_CONFLICT`) + canonical
  적용 순서(`AddTask → RemoveEdge → AddEdge`)를 추가. CANCELLED predecessor의 frontier
  의미를 P4로 명시 유보.
- v1.5 (D-006): §10에 reconciliation release 경로(ASSIGNED release / E_RUNNING_LOCKED /
  terminal outgoing 재배선)가 RQ3(P8) 전에는 end-to-end로 도달하지 않음을 명시(고정 5종
  어휘 + §9 #10의 결과). P2는 이를 단위테스트로 검증한다.
- v1.6 (D-007): §10에 assignment consistency invariant(§10 7단계) 명시. §7에 schema
  검증이 허용 키를 정확히 제한함을 명시(`E_SCHEMA`). graph_hash payload에 `priority` 포함,
  MissionPatch operation의 필드 schema를 런타임 검증(둘 다 P2 Codex 2차 지적).
- v1.7 (D-008): §7 `priority` 범위를 1..10으로 고정(`E_SCHEMA`). §10 assignment invariant에
  참조 무결성(규칙 6) 추가. §14에 `validator_version` bump 규칙과 rejected patch `graph_hash`
  범위 명시(P2 Codex 3차 지적).
- v1.8 (D-009): §11에 `λ = 0.999` 고정, 보상은 스케일 없는 `priority`, tie-break는 정확히
  같은 bid에서 `agent_id`→`task_id` 사전순, `bundle` 무제한을 명시(P3 구현).
- v1.9 (D-010): P3 Codex 검토 반영 — §13에 plan-time topological-wave barrier 모델(READY
  이전 이동 금지, utilization busy = travel+dwell만), §11에 tie-break를 `1e-9` 허용오차로
  명시(정확 상등 아님), §11·§10에 bundle/path 관계를 CBBA postcondition으로 확정.
- v1.10 (D-011): §11에 rolling epoch의 `held` commitment(미완료 할당은 재경매 안 함) +
  task lifecycle(ASSIGNED→RUNNING→COMPLETED) 명시, §14에 P4 구현체 `SimExecutor`의
  deadlock 판정 절차 명시(P4 구현).
- v1.11 (D-012): P4 Codex 검토 반영 — §14에 종료 사유 분리(`COMPLETED`/`DEADLOCK`/
  `STEP_LIMIT`), 실행 중 epoch 입찰의 residual-path 규칙, COMPLETED 시 assignment 정리
  명시. §10에 cancellation을 P1~P7 미지원·P8 유보로 확정.
- v1.12 (D-013): P4 Codex 재검토 — §11에 rolling epoch의 `availability_delay`(실행 중
  agent의 남은 시간)를 입찰 누적 시작값으로 명시, §14에 마지막 step 완주 시 `COMPLETED`
  판정 + precedence violation을 `task_departure` 기준으로 판정. availability-aware 후
  reference mission workload가 다시 균형(D-012의 "집중이 정상" 서술 철회).
- v1.13 (D-014): §14에 `STEP_LIMIT` 실행의 `makespan`/`agent_utilization`은 평가 지표로
  쓰지 않음을 명시(busy는 dispatch 시 예정치를 더하므로 미완 실행에서 util > 1 가능;
  `agent_utilization`은 빈 dict 반환).
- v1.14 (D-015): §14의 `patch_hash` 정리를 "P5 전"에서 "P8로 유보"로 변경 — MissionPatch는
  P5 candidate 검증에 쓰이지 않고 RQ3(P8)에서 실제 사용되므로 P8 문서 개정 시 확정.
- v1.15 (D-016): **task 어휘 변경** — `HAZARD_MARKER_DEPLOY` → `GROUND_SUPPRESSION`(symbolic),
  `Capability.MARKER_DISPENSER` → `SUPPRESSANT_APPLICATOR`, "Safety UGV" → "Ground Response
  UGV"(ID G1/G2 유지). §2·§3·§4·§5·§7·§9 #12·§15 P1 게이트 개정. `VALIDATOR_VERSION`
  1.1 → 1.2. reference fixture의 GROUND_SUPPRESSION priority = incident priority(F1 9 / F2 7).
  P3/P4 골든값 재산출.
- v1.16 (D-017): §12에 LLM 파이프라인 구현 명시 — `generate_mission`, pydantic 구조화
  출력, `LLMBackend` Protocol, `GenerationResult` 지표, `failure_category` 집합, schema
  오류는 즉시 명시적 거부.
- v1.17 (D-018): 실제 LLM backend를 OpenAI로 확정 — `OpenAIBackend`(`chat.completions.parse`,
  `OPENAI_API_KEY`, 선택적 repo-root `.env`). 평가 모델은 `gpt-5-mini`로 pin(reasoning
  model → `temperature` 미전달)하고 결과 표에 기록(§14). `llm` extra는 `openai`.
- v1.18 (D-019): P5 Codex 검토 반영 — §12에 Step 1→Step 2 순서 강제(Step 1이 schema
  통과 전에는 Step 2 호출 안 함), pydantic schema `extra="forbid"`+`strict=True` 명시,
  backend의 `ValidationError`를 명시적 SCHEMA 거부로 변환, `raw_candidate`/`raw_validation`과
  최종 `candidate`/`validation`을 분리 보존 명시.
- v1.19 (D-020): §12에 prompt task glossary(의미+담당 platform) 포함을 명시 — P6 결과가
  task 이름의 영어 의미 추측 능력이 아니라 임무 분해 능력을 재도록.
- v1.31 (D-033): D-032의 실행 전제를 §18.1 lifecycle과 정렬한다. 실행은 `PLANNING`뿐 아니라
  `EXECUTION_FAILED`에서도 같은 graph 재시도를 허용하며, `EXECUTED`에서만 거부한다.
  `VALIDATOR_VERSION` 불변(1.4).
- v1.30 (D-032): P8.3 구현 전 D-031의 남은 경계를 닫는다. `GroundingOutcome`과 감사 로그에
  `ClarificationReason`을 추가해 **실제 entity ambiguity**와 unknown/missing 조건을 구분하고,
  `PendingClarification`은 `AMBIGUOUS_ENTITY`이면서 재개에 필요한 나머지 slot이 완전할 때만
  만든다. 후보 선택·잘못된 후보·pending 중 자연어·취소의 턴/감사/보존 의미와 LLM 없는
  action의 명시적 `mode` 입력을 고정한다. 세션의 private append boundary가 통합 event 순서를
  소유하며, 실행 action의 성공·실패/예외 감사 의미를 확정한다. `VALIDATOR_VERSION` 불변(1.4).
- v1.29 (D-031): P8.3 착수 전 계약 확정. §18.9의 turn 감사 스토리지를 통합
  `event_log`(`TurnAudit | ExecutionAudit`)로 바꾸고 **list 순서를 event 순서의 유일한
  진실 원천**으로 고정 — `event_seq`는 직렬화 시 파생. 신규 §18.13(구조화된 clarification
  후보 선택): 후보 클릭은 LLM 없는 결정론적 입력이지만 감사되는 새 턴이며, `PendingClarification`은
  **entity ambiguity에서만** 생성되고, pending 중에는 후보 선택·취소만 허용되며 실행 버튼은
  비활성이다. §18.10 — scene YAML·`register_incident` 경로는 정규화가 비는 incident id를
  만들지 않는다(공유 `scenarios/naming.py`). §18.12에 pending 표시·실행 비활성 추가. §15 P8.3
  게이트 확장. `VALIDATOR_VERSION` 불변(1.4).
- v1.28 (D-030): P8.2 재검토 반영. §18.9에 `session_id` 문법을 고정 — 이 값이 곧 파일명이므로
  경로 구분자·상대 경로 요소가 섞이면 감사 기록이 계약이 고정한 `data/interaction_runs/` 밖에
  쓰인다. `MissionSession` 생성 시점에 강제한다. `VALIDATOR_VERSION` 불변.
- v1.27 (D-029): P8.2 검토 반영. §18.9의 turn 감사 레코드를 실제 `TurnAudit` 형상과 정렬 —
  `grounding`을 incident·zone 공통으로 일반화(`entity_kind`/`entity_id`/`via`), `patch_result`
  → `patch`, `up_to_step` 등 slot은 `extracted_slots`에 위치, `outcome`·`scene_changed`·
  `state_changed`·`referent_noted`·`answer` 명시, `TURN_ERROR` 원인을 영구 기록에 남기는
  `error_type`·`error_detail` 추가, `resolved_models`는 그 턴의 **모든** backend 호출
  (NEW_MISSION의 Step1/Step2/repair 포함). §18.5 — **지시어로 해석된 `QUERY_STATUS`는
  referent window를 갱신하지 않는다**(자기참조로 K=3 만료가 무한 연장되는 것을 막는다);
  명시 id QUERY와 `UPDATE_MISSION`은 갱신한다. `VALIDATOR_VERSION` 불변.
- v1.26 (D-028): P8.1d 검토 반영. §18.5에 incident referent 해석 우선순위를
  **fail-closed**로 명시 — 해석 불가능한 비어 있지 않은 표현은 최근 referent나 단일
  incident로 흘러내리지 않고 항상 clarification. 허용 지시어 목록을 계약에 고정(목록 확장은
  계약 개정으로만). 정규화 형태가 충돌하는 incident id는 조용히 하나를 고르지 않고
  clarification. 단일 incident 자동 선택을 명시적 정책으로 기록(§18.11 clarification gold의
  전제). 새 알고리즘 없음, `VALIDATOR_VERSION` 불변.
- v1.25 (D-027): P8 착수. §1 RQ3 재서술(증분 graph 수정 + 결정론적 재검증 + atomic
  commit/rollback + 올바른 clarification; "동적/선택적 재할당"은 후속). 신규 §18
  (Operator–LLM Planning Session — **실행 개시 전 다중 턴 계획 세션**으로 범위 고정, 5종
  대화 행위, session lifecycle, referent 규칙, NO_CHANGE, LLM/결정론 경계, interaction
  eval). §10 `AddTask` op을 `{task_type, target}`로(D-022 정렬). §14 `VALIDATOR_VERSION`
  1.3 → 1.4 + `scene_hash` zone payload에 incident response point 2필드 +
  `patch_hash`/`pre_state_hash` 정의(D-015 유보 해제). §15 P8.0~P8.5. §17 "P0~P7" →
  "P0~P6.5"(내부 모순 정정). `core/`·`allocation/`·`execution/`·
  `validator/{validate,whole_graph}.py`·`llm/pipeline.py`·`evaluation/` 무변경.
- v1.24 (D-026): P6.5 재검토 반영. §15 P6.5의 "→ 순차 파이프라인" 서술을 **fork 구조**로
  정정(`SimExecutor`는 내부에서 CBBA를 재수행하며 실행하므로 `allocate` 결과를 받지 않는다).
  P6.5 게이트에 annotation exact-match(`score_graph`)·`termination == COMPLETED`·
  실제 graph/graph_hash/scene_hash/validator_version/resolved_models/plan·exec assignment을
  담은 감사 JSON을 추가. 새 알고리즘 없음.
- v1.23 (D-025): §15에 P6.5(통합 runner) 게이트 추가 — NL 명령을 `generate_mission`(RQ1)
  → `allocate`·`SimExecutor`(RQ2)에 연결해 대표 명령 1~3개로 시연. 새 알고리즘 없음.
- v1.22 (D-023): P6 재검토 반영. §7 — incident `priority` 1..10 강제를 **scene loader**로
  이동(D-022는 compiler 파생만 명시해 scene 입력 경계가 비어 있었음 — `int()` 강제 변환으로
  잘못된 값이 Validator를 통과 후 compile에서 크래시). D-022 본문의 "annotation 명시형
  schema에 int·범위 검사 복원" 서술 정정 — annotation도 `{task_type, target}`만 허용하고
  priority 키를 거부한다. 문서: `python` → `python3` 통일, `core/task.py`·`CLAUDE.md` 옛
  LLM schema 서술 갱신. VALIDATOR_VERSION 불변(scene load 경계, 판정 규칙 아님).
- v1.21 (D-022): P6 Codex 검토 반영. §7 — LLM 출력에서 `priority` 제거, task entry는
  `{task_type, target}`; `derive_priority`(incident → incident.priority, AREA_RECON →
  상수 4)가 파생. §1 RQ1을 "구조 생성"으로 재서술. §9 — candidate 경로는 invariant
  #1~#12만("14개" 서술 금지), #13~#14는 patch 전용. §14 `VALIDATOR_VERSION` 1.2 → 1.3.
  §12 — 결과 JSON에 raw·final 후보 내용·graph_hash·error_codes 저장(감사, 축소 금지),
  `X/N` 동적 분모, family B edge P/R은 N/A, repair attempted/recovered 분리,
  하네스 예외는 `harness_error`로 분리. 감사 필드 추가 후 9개 라이브 재실행.
- v1.20 (D-021): §12에 P6 평가 하네스 설계 고정 — reference annotation 파일 형식/위치
  (`data/reference_annotations/<id>.yaml`, LLM 첫 호출 전 커밋), `task_key=(task_type,target)`
  기준 비교, `allowed_graphs` 중 (task F1, edge F1) 최대인 것과 대조, raw·final 후보 둘 다
  측정, `X/9` 집계 + family 분해 + 재현성 필드(scene_hash/validator_version/resolved_models).

이 프로젝트는 `/home/jiho/LLM_CBBA`(이하 "이전 저장소")와 Git 이력을 공유하지 않는 독립
연구다. 이전 저장소의 earthquake/vehicle-inspection/fire-patrol 연구 계약, D-xxx 결정, task
어휘, UAV 전용 dataclass, domain invariant, prompt, scenario, world, 골든값은 이 프로젝트의
근거로 쓰지 않는다. 이전 저장소에서 재사용하는 것은 알고리즘 패턴뿐이며, 재사용할 때마다
`docs/PROVENANCE.md`에 원본 경로·커밋·재사용 이유를 기록한다.

---

## 0. 제목과 성격

국문: LLM 기반 복합 재난 임무 분해 및 CBBA 이종 무인체계 임무 할당
영문: LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소(LLM structured
output, CBBA, 결정론적 Validator)를 통합하고 재현 가능하게 시연·평가하는 연구다.

---

## 1. 연구 질문

**RQ1 (필수)**: LLM이 고수준 복합 재난 대응 명령과 semantic scene으로부터 실행 가능한 task
graph의 **구조**(어떤 task_type을 어떤 target에, 그리고 task 간 dependency edge)를 생성할 수
있는가? 좌표·priority·capability·duration은 LLM이 만들지 않고 결정론적 compiler가 semantic
scene과 고정 매핑에서 resolve한다(§7) — RQ1은 그 구조 생성 능력을 §12 지표로 측정한다.

**RQ2 (필수)**: 결정론적으로 검증된 task graph를 CBBA가 UAV/UGV의 capability와 플랫폼별
이동비용을 고려하여 이종 무인체계에 실행 가능하게 할당할 수 있는가?

**RQ3 (후속, 선택)**: 실행 개시 전 다중 턴 자연어 계획 대화에서, 운용자의 후속 명령과 상황
보고를 대화 문맥·현재 임무 상태에 grounding하여 (a) 검증 가능한 atomic graph 증분
(MissionPatch)으로 변환하고, (b) 결정론적 whole-graph Validator로 재검증하며, (c) 승인 시
commit / 거부 시 원본 완전 보존하고, (d) 의미가 불명확하면 추측하지 않고 clarification을
요청할 수 있는가?

RQ3는 RQ1/RQ2의 모든 통과 조건이 충족되고 발표 가능한 정량 결과·시각화가 확보된 이후에만
착수한다(P8, P0~P6.5 완료 후). RQ3를 구현하지 못해도 실패로 간주하지 않으며, 후속 연구로
명시한다. RQ3가 구현되기 전에는 제목·초록·결론·발표자료 어디에도 "동적 재할당" 또는
"dynamic reallocation"을 완료된 결과로 주장하지 않는다. P8의 검증 범위는 실행 개시 전의
계획 세션이다.

**RQ4 (선택 확장)**: 실행 중 결정론적 checkpoint에서 운용자의 명시적 상황 보고·후속 명령을
받아, 이미 완료됐거나 실행 중인 commitment를 훼손하지 않고 영향받은 미시작 task만 선택적으로
release/rebid한 뒤 같은 시뮬레이션 시각·로봇 위치에서 임무를 재개할 수 있는가?

RQ4는 P8.4 결과까지 동결한 뒤 P9에서만 다룬다. P9의 release 집합은 §19.3의 결정론적
`bidder-connected bundle suffix` 정책으로 정의하며, 전역적으로 가장 작은 reset 또는 최적
재계획이라고 주장하지 않는다. D-006의 기존 서술은 **predecessor diff에 의한 Validator
reconciliation만으로는** release가 일어나지 않는다는 뜻으로 유지한다. P9는 새 READY task가
기존 미시작 task와 같은 bidder를 두고 경쟁한다는 별도 allocation 정책이므로 recheck task
type 없이도 release/rebid가 가능하다.

---

## 2. MP4MR과의 관계

참고 논문: 김연주 외, "임무 계획 자율화를 위한 LLM 기반 임무 분할 및 생성 기법" (J. ICROS
2025, 한국항공대+LIG넥스원). 이 논문의 구조(고수준 자연어 → LLM Task Generator → Critic 검증
→ BP 기반 이종 UAV/UGV 할당 → ROS2/Gazebo 시연)를 구조적으로 참고한다. 원문 재확인 완료:
Actor 1~4 단계, Critic 2/3/4a(feasibility)/4b(grammar), task 11종(표3), 실시간 피드백·동적
갱신 미구현·후속과제 명시 — 전부 확인됨.

**그대로 복제하지 않는 것**: WATER_LOAD, OBSTACLE_CLEAR, RELAY_DEPLOY, TARGET_TRACK,
인명·물자 적재/하적, MP4MR의 A~G 체계 분류. 새 시나리오는 "MP4MR-inspired"로 명시한다.

**GROUND_SUPPRESSION에 대하여(D-016)**: §4의 `GROUND_SUPPRESSION`은 지상 무인체계가 incident
접근 지점에서 수행하는 **symbolic task**다 — 위치 도달 + dwell로만 완료를 판정하고, 물리적
소화 성공이나 소화 소요시간을 산출하거나 주장하지 않는다(`SUPPRESSANT_DROP`과 같은 성격).
MP4MR의 UGV suppression과 유사한 단계가 있으나, 이 연구의 독창성 주장은 task 어휘가 아니라
**결정론적 whole-graph Validator + CBBA 축**에 둔다(아래 "핵심 차별점"). task 어휘 변경만으로
독창성을 주장하지 않는다.

**핵심 차별점**: LLM이 생성한 임무 그래프의 실현 가능성과 도메인 제약을, 또 다른 LLM Critic
호출이 아니라 **결정론적 whole-graph Validator**로 검증한다. 동일한 후보 그래프에는 항상
동일한 검증 결과가 나오며, 검증을 통과한 그래프만 CBBA와 simulator에 전달한다. MP4MR보다
우수하다고 주장하려면 동일 조건의 직접 비교가 필요하므로, 이 연구에서는 구조적 차이와
재현성 특성만 설명하고 우열을 주장하지 않는다. CBBA와 BP의 비교도 마찬가지로 주장하지 않는다.
task 명칭 변경이나 BP→CBBA 교체만으로 독창성을 주장하지 않는다 — 그 자체는 부차적 차이다.

---

## 3. 시나리오

약 200~250m 규모의 가상 산업단지 화재 대응 환경.

**구역**: ZONE_A(Warehouse), ZONE_B(Processing Area), ZONE_C(Utility Yard), ZONE_D(Tank
Farm).

**incident**: FIRE_SITE_1(ZONE_B, priority 9), FIRE_SITE_2(ZONE_D, priority 7). 초기 상태
`RESPONSE_REQUIRED` — reference scene에서 이미 대응이 필요한 것으로 주어지며, LLM이나 agent가
화재 여부를 판정하지 않는다. False alarm과 perception 기반 조건부 graph는 범위 밖이다. 이
`status`는 주석이 아니라 scene 데이터의 필수 필드로 명시하고 loader가 검증한다(`IncidentStatus`).

화재 위치·상태는 semantic scene 또는 운용자·외부 시스템 보고로만 시스템에 진입한다. 실제
영상 분석, 화재 탐지, 화재 안정성 판정은 구현하지 않는다. Task 완료는 위치 도달과 dwell
time으로만 판정한다.

**reference fixture 고정 형상** (P1~P4에서 쓰는 canonical full-response graph, §12 Family A에
대응). 이 값은 게이트 기준이며 LLM이 개입하기 전까지 사람이 손으로 고정한다:

| 항목 | 값 | 구성 |
|---|---|---|
| task | 12 | `AREA_RECON` 4 (ZONE_A~D) + incident workflow 4단계 × incident 2 = 8 |
| edge | 6 | incident 체인당 3 (§4 workflow) × incident 2 |
| 초기 READY | 6 | predecessor 없는 task = `AREA_RECON` 4 + `THERMAL_RECON` 2 |
| 초기 PENDING | 6 | `SUPPRESSANT_DROP` 2 + `GROUND_INSPECTION` 2 + `GROUND_SUPPRESSION` 2 |

READY/PENDING은 fixture YAML에 적지 않고 graph의 predecessor 상태에서 계산한다(§7, §9).

---

## 4. Task vocabulary

5종으로 고정한다. 추가 제안은 하지 않는다.

| task_type | 의미 | 완료 조건 |
|---|---|---|
| `AREA_RECON` | Scout UAV가 지정 구역을 정찰 | 위치 도달 + dwell |
| `THERMAL_RECON` | 이미 보고된 incident 위치에 UAV가 접근해 대응 전 열원 확인 절차를 수행하는 symbolic task. 열분포 지도, 새 좌표, 센서 데이터를 산출하지 않는다 | 위치 도달 + dwell |
| `SUPPRESSANT_DROP` | Response UAV가 사전 탑재한 대응 payload를 투하. 완료는 물리적 화재 진압 성공을 의미하지 않는다 | 위치 도달 + dwell |
| `GROUND_INSPECTION` | SUPPRESSANT_DROP workflow 완료 후 Ground Response UGV가 incident 접근 지점으로 이동해 지상 상태 점검 | 위치 도달 + dwell |
| `GROUND_SUPPRESSION` | GROUND_INSPECTION 완료 후 Ground Response UGV가 incident 접근 지점에서 지상 진압을 수행하는 symbolic task. 완료는 물리적 소화 성공·소화 소요시간을 의미하지 않는다(D-016) | 위치 도달 + dwell |

`THERMAL_RECON`을 `THERMAL_MAPPING`으로 부르지 않는다 — "mapping"은 위치를 도출하는 것처럼
들리는데 실제로는 아무 데이터도 산출하지 않는다.

**정적 incident workflow** (Phase 1, 조건부 규칙 — 아래 항상 강제되는 게 아님에 주의):

```
THERMAL_RECON → SUPPRESSANT_DROP → GROUND_INSPECTION → GROUND_SUPPRESSION
```

이 규칙은 "downstream task가 **존재하면** 같은 incident의 올바른 predecessor가 필요하다"는
조건부 규칙이지, "모든 incident가 반드시 4단계를 전부 생성해야 한다"는 강제가 아니다. 어떤
NL 명령이 THERMAL_RECON까지만 요청했다면 그 부분 graph도 구조적으로 유효하다. "이 부분
graph가 의도된 것인지 덜 만들어진 것인지"는 Validator의 역할이 아니라 §12 평가 하네스의
mission profile로 별도 판정한다(§9 참고).

`AREA_RECON`은 이 incident 대응 chain의 predecessor가 아니다 — 구역 정찰은 독립적으로
수행한다.

**dwell duration은 symbolic scenario parameter다**(D-016): 각 task_type마다 하나의 고정값을
`TASK_TABLE`에 두며, 물리적 소요시간(비행시간·소화시간 등)이라고 주장하지 않는다.
`GROUND_SUPPRESSION`의 duration도 마찬가지로 하나로 고정한다.

---

## 5. Agent 구성

총 6대, 2/2/2 고정.

| Agent | 대수 | capability |
|---|---|---|
| Scout UAV (S1, S2) | 2 | `AERIAL_RECON`, `THERMAL_SENSOR` |
| Response UAV (R1, R2) | 2 | `THERMAL_SENSOR`, `SUPPRESSANT_PAYLOAD` |
| Ground Response UGV (G1, G2) | 2 | `GROUND_MOBILITY`, `SUPPRESSANT_APPLICATOR` |

Task별 eligible bidder: `AREA_RECON`=Scout 2, `THERMAL_RECON`=Scout+Response 4,
`SUPPRESSANT_DROP`=Response 2, `GROUND_INSPECTION`=Ground Response UGV 2,
`GROUND_SUPPRESSION`=Ground Response UGV 2. 모든 task type에 eligible bidder ≥2 — UGV 전용
task에서도 CBBA가 G1/G2 중 winner를 결정한다.

Response UAV의 payload는 사전 탑재된 것으로 가정한다. `WATER_LOAD`, suppressant 잔량·재보급,
same-agent resource coupling은 구현하지 않는다.

**모든 agent가 반드시 하나 이상의 task를 받아야 한다는 제약은 두지 않는다.** 대기하는 것도
비용상 합리적인 결과일 수 있다. 대신 다음을 측정한다: agent utilization, idle-agent count,
workload distribution, task별 eligible bidder 수, Response UAV의 실제 참여 여부. Response
UAV가 계속 유휴 상태라면 이는 즉시 실패가 아니라 capability 구성·bid 가중치·task 수가 의도한
이종 할당 실험을 만드는지 재검토할 근거로 취급한다.

---

## 6. Generic Agent 모델

이전 저장소의 `UAV` dataclass를 복사하지 않는다. PX4 전용 필드(`mpc_xy_vel_max` 등)를 core
model에 넣지 않는다.

아래 코드는 예시다. `StrEnum`은 Python 3.11+ 전용이므로, 3.10 환경에서는 `class X(str, Enum)`
패턴으로 구현한다. 이 경우 enum 값이 bare string과 `==` 비교되므로 YAML **읽기**는 커스텀
loader가 필요없다. 단 `yaml.safe_dump`는 이 값을 직렬화하지 못하므로(RepresenterError),
직렬화가 필요한 경계에서는 항상 `member.value`를 쓴다.

```python
class PlatformKind(StrEnum):
    UAV = "UAV"
    UGV = "UGV"

class Capability(StrEnum):
    AERIAL_RECON = "AERIAL_RECON"
    THERMAL_SENSOR = "THERMAL_SENSOR"
    SUPPRESSANT_PAYLOAD = "SUPPRESSANT_PAYLOAD"
    GROUND_MOBILITY = "GROUND_MOBILITY"
    SUPPRESSANT_APPLICATOR = "SUPPRESSANT_APPLICATOR"

@dataclass(slots=True)
class Agent:
    agent_id: str
    platform_kind: PlatformKind
    capabilities: frozenset[Capability]
    initial_position: tuple[float, float]
    position: tuple[float, float]
    speed: float
    bundle: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    current_task: str | None = None
```

플랫폼 전용 설정(PX4 velocity parameter, Gazebo model, UGV route node, differential-drive
parameter)은 core `Agent`가 아니라 별도 platform adapter(`execution/px4_adapter.py`,
`execution/ugv_adapter.py`, P7에서 실제 구현)에 둔다.

---

## 7. Task 데이터 모델

```python
@dataclass(slots=True)
class Task:
    task_id: str
    task_type: TaskType
    target: str                                   # area_id 또는 incident_id
    position: tuple[float, float]
    priority: int                                 # 1..10 (D-008), 클수록 우선
    required_capabilities: frozenset[Capability]   # 복수 — 예: GROUND_SUPPRESSION은 GROUND_MOBILITY+SUPPRESSANT_APPLICATOR 둘 다 필요
    eligible_platforms: frozenset[PlatformKind]
    duration: float
    status: TaskStatus
    assigned_agent: str | None = None
```

**LLM은 `position`, `priority`, `required_capabilities`, `duration`, `eligible_platforms`,
`task_id`를 직접 생성하지 않는다(D-022).** LLM 출력은 `task_type` + `target`(landmark/incident
참조)만 포함한다. 나머지는 결정론적 compiler가 semantic scene과 기본 매핑 테이블에서
resolve한다. LLM이 좌표나 priority를 직접 생성하면 semantic scene과 이중 진실 원천이 생긴다.
schema 검증(§9 #1)은 이를 강제한다 — top-level 키는 정확히 `{tasks, edges}`, task entry
키는 정확히 `{task_type, target}`여야 하며, 그 외 키(`priority`, `assigned_agent` 등)가
있으면 `E_SCHEMA`로 거부한다.

**priority 파생 규칙(D-022)**: compiler(`scenarios/compiler.py`의 `derive_priority`)가
결정한다.
- incident를 target으로 하는 task(`THERMAL_RECON`/`SUPPRESSANT_DROP`/`GROUND_INSPECTION`/
  `GROUND_SUPPRESSION`) → 그 incident의 `priority`(§3: FIRE_SITE_1 = 9, FIRE_SITE_2 = 7).
- `AREA_RECON`(zone target) → 고정 상수 `AREA_RECON_PRIORITY = 4`. zone은 사건 심각도가
  없으므로 균일하며, 두 incident priority(7·9)보다 낮아 CBBA가 진행 중 사건 대응을 zone
  정찰보다 앞세운다.

incident priority의 진실 원천은 semantic scene이므로, **scene loader가 로드 시점에**
각 incident `priority`가 정수 **1..10**임을 강제한다(D-023 — bool·문자열 `int()` 강제
변환 없음). compiler는 scene을 신뢰하므로 이 검사가 없으면 Validator가 승인한 graph가
compile 단계에서 깨질 수 있다. `core/task.py`의 `Task.__post_init__`가 최종 방어선으로
같은 범위를 재확인한다(D-008 — CBBA 보상이 0·음수에서 음수 bid·미할당을 내지 않도록).
파생된 priority는 audit hash(§14 `graph_hash`)의 node payload에 포함된다.

MissionPatch(`AddTask`, §10)의 priority 처리: §10이 `AddTask = {task_type, target}`로
확정했다(D-027). P8.0 문서 시점의 코드에는 `AddTask.priority`가 임시로 남아 있으나, **P8.1
게이트에서 제거하고 `derive_priority`로 정렬한다.** P8.1 완료 후 patch schema의 진실 원천은
§10이다.

`Task.status`는 YAML에 독립적으로 기록하지 않고 graph의 predecessor 상태로부터 계산한다
(§9의 whole-graph recompute).

**입력 경계**: 결정론적 compiler는 **신뢰된** task 목록만 받는다 — 손으로 작성한 reference
fixture, 그리고 §12 파이프라인에서 이미 whole-graph Validator를 통과한 LLM 출력. compiler는
구조적으로 깨진 입력(존재하지 않는 edge 끝점, 중복 edge)에 대해 조용히 버리지 않고 예외를
던진다. raw LLM candidate의 E_UNKNOWN_REF/E_DUPLICATE_EDGE 판정은 compile 이전에 Validator가
자체 candidate 표현 위에서 수행한다(§9, §12).

---

## 8. 이동비용

`agent.access_node`는 core `Agent`(§6)에 없다 — UGV 시작 node는 `scene.agent_access_nodes[agent_id]`로
조회한다.

```python
def travel_time(agent, target_pos, scene) -> float:
    if agent.platform_kind is PlatformKind.UAV:
        return math.dist(agent.position, target_pos) / agent.speed
    start = scene.agent_access_nodes[agent.agent_id]
    dist = scene.route_graph.shortest_path_distance(start, target_access_node(target_pos))
    if dist is None:
        raise UnreachableError(agent.agent_id, target_pos)
    return dist / agent.speed
```

- UAV: 2D 또는 3D Euclidean distance / speed.
- UGV: 사전 정의된 lane/waypoint graph의 Dijkstra 최단경로 거리 / speed. 임의 좌표를 직접
  Dijkstra에 넣지 않고, target마다 `access_node_id`를 scene에 명시한다.
- **scene 로드 시점 검증(전부 실패 시 시나리오 로드 거부)**: (a) 모든 incident의 `access_node`가
  route graph node로 존재, (b) 모든 UGV agent의 시작 node가 route graph node로 존재, (c) 모든
  UGV 대상 task 위치가 route graph에서 모든 UGV 시작 node로부터 도달 가능, (d) `agent_id` 유일.
  (c)는 task 목록이 필요하므로 fixture/candidate 로드 시점에, (a)(b)(d)는 scene 로드 시점에
  검사한다. CBBA 입찰 단계까지 가지 않는다.
- 2D simulator와 향후 Gazebo가 동일한 route semantics를 공유해야 한다.

이 함수는 이전 저장소의 `travel_time()`을 그대로 이식하지 않고 `platform_kind` 분기를 새로
추가한 것이다 — §14 PROVENANCE 참고.

---

## 9. Deterministic Whole-Graph Validator

**주장 범위**: Validator는 LLM graph의 구조적·도메인적 실행 가능성을 결정론적으로 검증한다.
자연어 의미 충실도(사용자 명령에 필요한 task가 빠짐없이 생성됐는가)는 코드만으로 판정할 수
없으므로 Validator의 역할이 아니다 — 이건 §12에서 task/edge precision·recall로 별도 평가한다.
"결정론적 Validator가 LLM graph의 정확성을 보장한다"는 과장된 주장을 하지 않는다.

**mission profile**: `FULL_RESPONSE`/`AERIAL_ONLY`/`SELECTIVE_RESPONSE`는 런타임 Validator가
아니라 §12 평가 하네스의 개념이다. 실험 입력별 expected profile을 LLM 출력을 보기 전에
고정하고, 그 profile에 맞는 reference annotation과 대조해 recall을 측정한다. 런타임
Validator는 이 두 출력을 구별하지 못한다: (a) 의도적으로 THERMAL_RECON까지만 생성한
aerial-only 임무, (b) full-response 명령인데 나머지 task를 누락한 불완전 임무. 둘 다 구조적으로
유효하면 Validator는 승인한다 — 이 한계는 §12의 recall 지표로 측정한다.

**invariant 목록**:

| # | 검사 | 범위 | 오류코드 |
|---|---|---|---|
| 1 | schema 유효성 | patch 전체 | E_SCHEMA |
| 2 | task_id 유일 | 전체 graph | E_DUPLICATE_ID |
| 3 | task_type ∈ 허용집합(5종) | task별 | E_TYPE_NOT_ALLOWED |
| 4 | target이 존재하는 area/incident 참조 | task별 | E_UNKNOWN_REF |
| 5 | edge 양끝이 존재하는 task 참조 | edge별 | E_UNKNOWN_REF |
| 6 | self-loop 금지 | edge별 | E_SELF_LOOP |
| 7 | 중복 edge 금지 | 전체 graph | E_DUPLICATE_EDGE |
| 8 | DAG(비순환) | 전체 graph | E_CYCLE |
| 9 | capability 충족 agent 존재(≥1) | task별 | E_INFEASIBLE |
| 10 | incident workflow: downstream이 존재하면 같은 incident의 정확히 그 predecessor 타입을 정확히 1개 가짐(조건부, §4 참고) | incident 체인별 | E_WORKFLOW |
| 11 | cross-incident edge 금지 | workflow edge별 | E_CROSS_INCIDENT |
| 12 | UGV 대상 task 위치가 route graph에서 도달 가능 | GROUND_INSPECTION/GROUND_SUPPRESSION | E_UNREACHABLE |
| 13 | **종결(COMPLETED/CANCELLED) task는 상태·결과·target·incoming edge가 불변. 단, 아직 RUNNING이 아닌 successor를 향한 outgoing edge는 같은 atomic patch 안에서 유효한 workflow로 재배선할 수 있다** | 전체 | E_TERMINAL_IMMUTABLE |
| 14 | patch 거부 시 원본 완전 보존(트랜잭션) | patch 전체 | (부분 commit 없음) |

이 표는 **최종 후보 graph** 위에서 도는 whole-graph Validator다. patch의 raw operation 목록
self-일관성 검사(중복 op, 같은 edge Add+Remove 등, 오류코드 `E_PATCH_CONFLICT`)는 이 검증
이전 단계이며 §10 처리 절차 2단계에서 별도로 수행한다.

**적용 범위**: §12 LLM candidate 경로(P5/P6)가 받는 검사는 **#1~#12**다(그중 #1은 candidate
schema — top-level `{tasks, edges}`, task entry `{task_type, target}`). **#13~#14는
MissionPatch 경로 전용**이며 RQ3(P8) 전에는 end-to-end로 도달하지 않는다(D-006). "승인된
candidate graph가 14개 invariant를 만족한다"고 서술하지 않는다 — "#1~#12를 만족한다".

**#13의 outgoing 재배선 허용은 미래 일반 patch를 위한 경계**다. P9의 canonical chain
extension은 기존 edge를 재배선하지 않으므로 이 예외를 사용하지 않는다. P9의 선택적 release는
whole-graph Validator가 아니라 승인된 patch 뒤의 allocation 정책(§19.3)에서 발생한다.

**멀티 트랜잭션 우회 테스트 필수**: invariant는 단일 patch뿐 아니라 여러 patch에 걸친 edge
추가·삭제 시퀀스로도 테스트한다(이전 저장소 D-079에서 실제로 겪은 교훈: 검사 대상을 그
transaction에서 새로 생긴 것으로 한정하면, 다른 종류의 patch로 기존에 이미 검증된 것을
나중에 깨는 우회가 가능해진다 — 매 patch마다 최종 후보 graph 전체를 처음부터 다시 검사해야
막힌다).

---

## 10. MissionPatch와 diff 기반 reconciliation

**operation**: `AddTask`, `RemoveEdge`, `AddEdge` 세 가지로 고정한다. `AddTask`는
`{task_type, target}`만 담는다(D-027 — D-022 정렬). priority는 `apply_patch`가
`derive_priority`(§7)로 파생한다. `ReleaseAssignment` 같은 명시적 release operation은
만들지 않는다.

**처리 절차**:

1. 현재 `MissionState`를 clone한다.
2. **raw operation 목록을 self-일관성 검증한다** (D-005). 이 검사는 operation을 TaskGraph에
   넣기 전에 raw 목록(list) 위에서 한다 — set/graph에 들어가면 중복 정보가 사라진다.
   - 각 operation의 schema 유효성 (E_SCHEMA)
   - 같은 `task_id`에 대한 AddTask ≥2 (E_PATCH_CONFLICT)
   - 같은 edge에 대한 AddEdge ≥2, 또는 RemoveEdge ≥2 (E_PATCH_CONFLICT)
   - 같은 edge를 한 patch에서 AddEdge와 RemoveEdge 둘 다 (E_PATCH_CONFLICT)
   - 원본에도 없고 이 patch의 AddEdge도 아닌 edge에 대한 RemoveEdge (E_PATCH_CONFLICT)
3. 검증을 통과하면 canonical 순서 **`AddTask → RemoveEdge → AddEdge`**로 clone에 적용한다.
   2단계에서 self-충돌·중복을 제거했으므로 최종 후보 graph는 operation 나열 순서와 무관하게
   유일하다. (diff 기반 reconciliation은 lifecycle 부수효과만 정리할 뿐 최종 graph 자체의
   순서 의존성은 없애지 못한다 — 순서 독립성은 2·3단계가 보장한다.)
4. 최종 후보 graph 전체를 §9 invariant로 검증한다.
5. **원본 graph와 최종 candidate graph의 predecessor-set diff를 계산한다** — patch 도중의
   중간 상태가 아니라 시작과 끝만 비교한다. (서로 다른 edge를 제거·추가하는 RQ3 재배선에서
   중간 상태가 불필요한 release를 유발하지 않게 하려는 것이 "AddEdge 시점 즉시 release" 대신
   diff 기반을 쓰는 이유다.)
6. diff로 predecessor 집합이 바뀐 task에 대해 lifecycle/assignment를 reconciliation한다:
   - PENDING(새 unmet predecessor 추가): 그대로 PENDING
   - READY → PENDING
   - ASSIGNED → PENDING, assignment/bundle/path/winner-bid 기록 제거
   - RUNNING: **patch 전체를 거부**(이번 범위에서 RUNNING task의 predecessor 변경은 지원하지
     않음 — abort는 executor handshake까지 설계해야 하는 후속 과제)
   - COMPLETED/CANCELLED: 그 task 자신의 상태·결과·target·incoming이 바뀌는 diff면 거부;
     outgoing만 바뀌는 diff는 §9 #13에 따라 허용
   - predecessor 제거로 모든 조건이 충족된 PENDING: READY로 재계산. **frontier 계산은
     COMPLETED predecessor만 "충족"으로 취급한다**(D-012 확정): P1~P7에서 cancellation은
     지원하지 않으며 RQ3(P8)로 유보한다. 만약 CANCELLED predecessor가 존재하면 그 successor는
     영원히 blocked로 남고 executor는 이를 deadlock으로 보고한다 — 이게 의도된 현재 의미다.
     P8에서 cancellation을 도입할 때 cascade cancel vs blocked를 이 문서 개정으로 확정한다.
7. reconciliation 결과에 대해 state/assignment invariant를 재검사한다.
8. 유효하면 patch 전체를 commit, 아니면 전체 rollback한다. 중간 상태는 절대 외부에 노출하거나
   실행하지 않는다.

**reconciliation release 경로의 도달성(D-006)**: 고정 5종 task 어휘 + 엄격한 §9 #10 하에서는
어떤 **유효한** patch도 기존 task의 predecessor 집합을 바꾸지 못한다(workflow task는 항상
정확히 canonical predecessor 1개를 가져야 하므로). 따라서 6단계의 ASSIGNED→PENDING release,
E_RUNNING_LOCKED, terminal outgoing 재배선은 구현·단위테스트하되, RQ3(P8)가 recheck 계열
task를 도입하기 전에는 end-to-end로 도달하지 않는다. #13의 terminal incoming 불변은 P2에서
도달 가능하다.

**assignment consistency invariant(§10 7단계, D-007)**: MissionState가 commit될 때마다 검사한다.

1. `task.assigned_agent`가 설정돼 있으면 그 값은 fleet에 존재하는 agent다.
2. task가 `ASSIGNED` 또는 `RUNNING` ⟺ `assigned_agent`가 설정됨.
3. `ASSIGNED`/`RUNNING` task는 정확히 한 agent의 `bundle ∪ path`에 나타나고, 그 agent가
   `assigned_agent`다.
4. `PENDING`/`READY`/`COMPLETED`/`CANCELLED` task는 어떤 agent의 `bundle`/`path`에도 없고
   `winning_bids`에도 없다.
5. `bundle`/`path`의 세부 관계는 §11의 CBBA postcondition(D-010)으로 확정했다 — Validator
   invariant는 아니므로 여기서 `E_SCHEMA`로 강제하지 않는다. P2는 위 1~4만 강제한다.

6. **참조 무결성(D-008)**: 모든 `bundle`/`path` task_id와 모든 `winning_bids` key는 graph에
   존재하는 task를 가리킨다. `state.agents`의 dict key는 해당 `Agent.agent_id`와 일치한다.

이 invariant를 어긴 상태를 만드는 patch는 `E_SCHEMA`로 거부한다(별도 stale-assignment
오류코드는 두지 않는다).

**PatchResult**: `accepted`, `added_tasks`, `added_edges`, `removed_edges`,
`directly_released_tasks`, `status_changes`, `rejection_errors`를 기록한다.
`directly_released_tasks`(안전을 위한 필수 release)와 §16의 B0~B3류 downstream suffix reset
(비교 전략의 선택)은 서로 다른 개념이며 섞지 않는다 — 전자는 Validator/reconciliation이
구조적으로 강제하는 것이고, 후자는 실험 전략이 그 위에 추가로 선택하는 것이다.

이 설계는 이전 저장소 fire-patrol에서 얻은 교훈("release를 caller가 깜빡하면 안 된다")은
재사용하지만, 구현 세부(AddEdge 즉시 부수효과, RUNNING 자동 abort)는 그대로 복사하지 않는다.

---

## 11. CBBA 할당 방식

**Rolling READY-frontier epoch**: CBBA는 매 scheduling epoch에서 현재 READY 상태인 task만
할당 대상으로 삼는다. PENDING task는 아직 입찰 대상이 아니다. dependency가 해제되어 새 task가
READY가 되면 새 epoch를 시작한다. (precedence-aware 선점 번들링은 구현 난도만 올리고 RQ1/RQ2
검증에 필요하지 않으므로 채택하지 않는다.)

이 방식에서 Response UAV가 초기에는 대기하다 `SUPPRESSANT_DROP`이 READY가 된 뒤 투입되는 것도
정상 동작이다.

**rolling epoch의 held commitment(D-011)**: 새 epoch는 아직 완료되지 않은 기존 할당을
`held`(task → winner, bid)로 넘겨받아 재경매하지 않는다. 이게 없으면 task가 하나씩 staggered
로 READY가 될 때마다 매 epoch를 빈 bundle로 다시 경매해서 같은 agent가 연달아 이기고, 다른
동종 agent가 계속 유휴 상태가 된다. task lifecycle은 `ASSIGNED`(경매 낙찰) → `RUNNING`(agent가
이동 시작) → `COMPLETED`(위치 도달 + dwell 완료, §3).

**Bid/score**:

```
PathUtility(path) = Σ priority(task_j) × λ^projected_completion_time(task_j)
bid = max_insertion[ PathUtility(path_with_candidate) − PathUtility(current_path) ]
```

`projected_completion_time`은 현재 agent 위치, 플랫폼별 이동시간(§8), 선행 task들의 dwell
duration, 후보 task duration을 누적한 값이다. **rolling epoch에서 아직 task를 실행 중인
agent는 남은 실행시간(`availability_delay = max(0, finish_at − now)`)을 누적 시작값으로
쓴다**(D-013) — 위치는 그 task의 도착 지점으로 투영하고, 실행 중인 task 자체는 residual
path에서 제외한다. P3 `allocate`는 모든 `availability_delay = 0`으로 기존 동작을 유지한다. `λ = 0.999`로 고정한다(D-009, 이전 저장소
`DEFAULT_LAMBDA` 재사용) — 모든 조건에서 동일하게 쓴다. `priority(task_j)`는 §7의 정수
1..10을 스케일 없이 그대로 쓴다(이전 저장소의 `10·priority`가 아님). 동점 처리(D-010):
두 bid의 차가 `1e-9` 이내면 동점으로 보고 `agent_id` 사전순으로 작은 쪽이 이긴다(그 다음
`task_id` 사전순). 부동소수점 안정성을 위해 정확한 상등이 아니라 이 허용오차를 쓴다 —
코드의 `EPSILON`과 동일해야 한다. `bundle` 길이에는 상한을 두지 않는다(§17).

**bundle / path 관계(D-010, CBBA postcondition — Validator invariant 아님)**: `bundle`은
bid 획득 순서, `path`는 실행 순서. epoch 수렴 후 둘은 중복 없는 **동일 task 집합**이다. 각
task는 최종 winner 한 명의 `bundle`/`path`에만 존재한다. P3 plan-time에서 `current_task`는
`None`이다. epoch 종료 후 `bundle`/`path`는 임시 산출물이며 전체 계획의 기준은
`AllocationResult.assignments`다.

이 보상형태(우선순위×이동시간 할인)는 새로 고안한 게 아니라 이전 저장소 CBBA의 검증된 보상
구조를 재사용한 것이다 — §14 PROVENANCE 참고. bundle/consensus/tie-break 핵심 로직만
재사용하고, 이동비용 계산은 §8처럼 platform-aware로 새로 작성한다.

CBBA를 새로운 알고리즘 기여로 표현하지 않는다.

---

## 12. LLM 파이프라인과 평가

**파이프라인**:

```
자연어 명령 → Step 1(task 목록: task_type/target만) → schema validation
→ Step 2(dependency edge 제안) → whole-graph Validator → 구조화 오류 기반 repair 최대 1회
→ 전체 재검증 → 승인 또는 명시적 거부(reference로 조용히 fallback하지 않음)
```

repair 후에도 실패하면 해당 mission을 명시적 실패로 집계한다.

**구현(D-017, D-018, D-019)**: `llm/pipeline.py`의 `generate_mission(command, scene, backend)`.
Step 1/2/repair는 pydantic 구조화 출력(`llm/schemas.py`)이고, backend는 `LLMBackend`
Protocol이다 — `OpenAIBackend`(`chat.completions.parse`, `OPENAI_API_KEY`, 평가 모델
`gpt-5-mini` 고정)와 `MockBackend`(스크립트 응답). P5 게이트 테스트는 전부 `MockBackend`로
돌아 네트워크·API 키가 필요없다. 실제 LLM 평가(P6)는 §14 재현성을 위해 모델을 결과와 함께
기록한다.

**순서 강제(D-019)**: Step 1 출력은 **Step 2를 호출하기 전에** 자체적으로 schema 검증한다
(task-only `MissionCandidate.from_raw` + 중복 id 검사). Step 1이 schema를 통과하지 못하면
Step 2 backend 호출 자체가 일어나지 않는다 — mock 테스트는 이 경우 backend 호출 횟수가
정확히 1임을 검증한다.

**schema는 정확히 제한한다(D-019)**: `llm/schemas.py`의 모든 pydantic 모델은
`model_config = ConfigDict(extra="forbid", strict=True)`를 쓴다. 모델이 허용 안 된 키를
내거나(`priority`, `position`, top-level `notes` 등) 타입을 벗어나면(`target=123` 등)
조용히 버리거나 강제 변환하지 않고 `pydantic.ValidationError`로 거부되어야 한다.

**backend 예외는 명시적 SCHEMA 거부로 변환한다(D-019)**: Step 1/2/repair 중 어느 backend
호출에서든 `pydantic.ValidationError`가 나면 파이프라인이 예외로 죽지 않고
`GenerationResult(approved=False, failure_category="SCHEMA")`를 반환한다. 네트워크·인증
오류 등 다른 예외는 그대로 전파한다(P6 평가 하네스가 별도로 기록·재시도한다).

**raw와 최종을 분리 보존한다(D-019, §16)**: `GenerationResult`는 `raw_candidate`/
`raw_validation`(repair 이전, Step 1+2 직후의 후보와 검증 결과)과 `candidate`/`validation`
(최종 — repair가 있었으면 그 결과, 없었으면 raw와 동일 객체)을 둘 다 갖는다.
`raw_schema_valid`/`raw_whole_graph_valid`는 항상 raw 기준이고, `repaired_schema_valid`/
`repaired_whole_graph_valid`는 repair를 실제로 시도했을 때만 값이 있고(`repaired=True`),
시도하지 않았으면 `None`이다. "raw output과 validated output 비교"(§16)는 이 필드들로 한다.
`failure_category` ∈ {SCHEMA, WORKFLOW, STRUCTURE, REFERENCE, FEASIBILITY, OTHER}. 승인된
candidate만 `compile_reference_graph`로 실행 graph화한다(D-003 경계).

**P6 평가 하네스(D-021)**: §12의 "P6 하네스 구현" 참고. 9개 명령의 목록·family·profile은
`docs/DECISIONS.md` D-021에 고정한다.

**prompt에 task glossary를 포함한다(D-020)**: `llm/prompts.py`의 scene facts는 task_type
이름·target 종류뿐 아니라 각 task의 의미와 담당 platform을 설명하는 glossary를 포함한다.
이게 없으면 P6 결과가 LLM의 임무 분해 능력이 아니라 task 이름의 영어 의미 추측 능력을 재는
꼴이 된다. `GROUND_INSPECTION`(점검)과 `GROUND_SUPPRESSION`(진압)처럼 이름이 비슷한 쌍은
특히 구분해 설명한다.

**평가**: 최소 9개 명령(family당 3개), 시간이 있으면 18개(family당 6개)로 확장.

- Family A(full industrial response): 전체 구역 정찰 + 두 incident 전체 workflow
- Family B(aerial-focused): AREA_RECON/THERMAL_RECON만 요청 — SUPPRESSANT_DROP/UGV task가
  생성되면 안 됨
- Family C(selective incident response): 특정 incident만 전체 대응, 다른 incident는 정찰
  또는 THERMAL_RECON까지만

각 명령의 LLM 출력을 보기 전에 사람이 canonical reference annotation을 고정한다.
`task_key = (task_type, target)`, `edge_key = (predecessor_task_key, successor_task_key)`.
정답이 여러 개 가능한 경우 LLM 결과를 본 뒤 정답을 바꾸지 않고, 실험 전에 허용 가능한
reference graph를 복수로 고정한다.

**지표**: schema-valid count, raw whole-graph-valid count, repair 후 whole-graph-valid
count, task precision/recall, edge precision/recall, exact graph match, failure category,
latency. `unnecessary_task_rate`는 별도 지표로 안 쓴다 — 정답에 없는 task는 task precision의
false positive로 처리한다. 소표본 결과는 백분율만 말고 원시 개수를 함께 제시한다(예:
"7/9 valid", "family A: 2/3").

**P6 하네스 구현(D-021)**:

- **reference annotation**: `data/reference_annotations/<id>.yaml` — `id`, `family`(A/B/C),
  `profile`(FULL_RESPONSE/AERIAL_ONLY/SELECTIVE_RESPONSE), `command`, `rationale`(reference를
  이렇게 고정한 근거), `allowed_graphs`(허용 정답 복수). 각 graph는 shorthand
  `recon_zones: [...]` + `incident_chains: {FIRE_SITE_x: [<§4 workflow의 연속 prefix>]}` 또는
  명시적 `tasks`/`edges`로 적는다. **LLM을 처음 호출하기 전에 커밋한다** — git 이력이 순서를
  증명한다.
- **task_key/edge_key 비교**: `task_key = (task_type, target)` — LLM 출력이 이제
  `{task_type, target}`뿐이므로(D-022) 이게 곧 LLM이 생성하는 것 전부다. 예측 graph를
  `allowed_graphs` 중 (task F1, edge F1) 최대인 것 하나와 대조해 task/edge precision·recall·
  exact match를 낸다. 정답이 없는 예측 task는 task precision의 FP, 정답에 있는데 없는 예측은
  recall의 FN. 정답 edge가 0개인 case(family B)의 edge precision/recall은 백분율 대신 **N/A
  (0 reference edges)**로 표기하고 성공 여부는 exact match로 본다.
- **raw와 final 둘 다 측정**: `raw_candidate`(repair 이전)와 최종 `candidate` 각각에 대해
  지표를 낸다. schema 실패로 candidate가 없으면 그 지표는 N/A(집계에서 분모 제외).
- **감사 기록(§14, §16 — 축소 금지)**: 결과 JSON에 case별로 raw·final 후보의
  `tasks`(task_type/target/파생 priority)·`edges`, raw·final `graph_hash`, `accepted`,
  `error_codes`, `repaired_schema_valid`를 저장한다. 제3자가 `task_type`/`target`만으로
  precision·recall·exact match를 독립 재계산할 수 있어야 한다. 가능하면 모델의 structured
  output 원문도 남긴다.
- **집계**: schema-valid·raw/repair 후 whole-graph-valid·approved를 `X/N`(N = 실행한 case
  수, 하드코딩 금지)로, task·edge precision/recall은 candidate가 있는 case의 평균 + 원시
  분자/분모, exact match count, failure category 히스토그램, latency(초) 통계, family별 분해.
  repair는 "attempted / recovered / first-pass approved"를 분리해 적는다(attempted 0이면
  "repair는 mock·negative 테스트로만 검증"이라고 명시).
- **재현성**(§14): 결과에 `scene_hash`, `validator_version`, 명령별 `resolved_models`(실제
  `completion.model`), backend 종류를 기록한다. 하네스 자체 예외(네트워크·인증·backend
  raise)는 `failure_category`(모델 출력 실패 분류)와 섞지 않고 별도 `harness_error`로 적는다.
- **위 감사 필드를 저장하지 않은 실행은 결과로 인정하지 않는다** — 필드를 추가한 뒤 9개
  라이브 평가를 다시 실행한다.
- 실제 LLM 평가는 `OpenAIBackend`, 하네스 self-test는 `MockBackend`(스크립트 응답).

---

## 13. CBBA/실행 평가

allocation success, unassigned task count, capability violation count, precedence violation
count, total route distance, estimated makespan, agent utilization, workload distribution,
idle-agent count, CBBA consensus rounds, 동일 입력 재실행 결정성. capability/precedence
violation은 정상 실행에서 항상 0이어야 한다.

**P3 plan-time schedule 모델(D-010)**: P3은 실제 event loop가 아니라 계획 평가다.
topological-wave barrier로 계산한다 — epoch 1 시작 0, 각 epoch의 frontier task를 계획 실행,
epoch 종료 시각 = 그 frontier의 최대 completion, 다음 epoch agent 출발 시각 =
`max(agent_free_at, epoch_start)`, 그다음 travel → task_start → dwell 순서. **agent는
task가 READY가 되기 전에 이동을 시작하지 않는다**(barrier 이전 이동 금지). `agent_utilization`
의 busy time은 **실제 travel + dwell만** 포함하고 predecessor 대기시간은 제외한다.
event-driven 방식(predecessor 완료마다 즉시 새 epoch)은 P4 executor 범위이므로 P3에서는 안 쓴다.

작은 toy fixture에서 exact allocation과 비교할 수 있으나, 이는 CBBA 구현 자체의 sanity check일
뿐 전체 시나리오에서의 최적성이나 BP 대비 우월성의 근거로 쓰지 않는다.

---

## 14. 재현성 주장의 범위와 PROVENANCE

"같은 graph에는 항상 같은 검증 결과"라는 주장은 다음이 고정됐을 때만 성립한다: Validator·규칙
버전, semantic scene hash, task vocabulary, configuration, 입력 graph canonicalization.
Validator 실행 결과에는 최소한 `graph_hash`, `scene_hash`, `validator_version`, `accepted`,
`error_codes`를 기록한다.

**`validator_version` bump 규칙(D-008)**: 판정 규칙이 바뀌면(invariant 추가·제거·의미 변경,
schema 허용 범위 변경, hash payload 형식 변경) 반드시 올린다. 같은 버전 아래에서 동일 입력의
`accepted`/`error_codes`가 달라지면 안 된다. 테스트는 의도한 버전 literal을 확인한다.
현재 `VALIDATOR_VERSION = "1.4"` — 1.3 → 1.4 (D-027): (i) MissionPatch `AddTask` op schema
`{task_type, target, priority}` → `{task_type, target}`, priority는 `apply_patch`가
`derive_priority`로 파생, (ii) `scene_hash`의 zone payload에 `reported_incident_position`·
`reported_incident_access_node` 추가(§18.10 신규 incident 등록에 필요), (iii) `patch_hash` +
`pre_state_hash` 정의(아래, D-015 유보 해제). candidate 경로(#1~#12)의 판정은 불변이나 patch
schema와 scene payload가 바뀌었으므로 bump. **baseline 태그 `v0.6.5-baseline`의 P6/P6.5
결과는 Validator 1.3 / 옛 `scene_hash`
(`0e8f098cd95aba26f1384fc6ad5c89ad047ec84912cf595936a7b56d75672c6d`)로 보존하고 라이브
재실행하지 않는다. P8부터 1.4 / 새 `scene_hash`로 기록한다.** 1.2 → 1.3 (D-022): candidate
schema task entry 키가 `{task_type, target, priority}` → `{task_type, target}`. `graph_hash`
node payload는 여전히 `(task_type, target, priority)` triple이며 priority는 `derive_priority`가
채운다.

**rejected patch의 `graph_hash` 범위(D-008)**: `E_SCHEMA`/`E_PATCH_CONFLICT`로 whole-graph
단계 이전에 거부된 patch는 최종 graph가 존재하지 않으므로 `graph_hash`가 빈 문자열이다. 이
경우 `scene_hash` + `validator_version` + `error_codes`가 감사 기록이다.

**`patch_hash` / `pre_state_hash`(D-027 — D-015 유보 해제)**:

- `patch_hash` = sha256 canonical of `{base_graph_hash, pre_scene_hash,
  operations(canonical 정렬), validator_version}`. **op의 field-level schema 검증을 통과한
  patch 시도에만** 생성한다(schema-invalid op은 안전한 canonical 직렬화가 불가능).
- `pre_state_hash` = sha256 canonical of `{ per task: (task_id, status, assigned_agent);
  per agent(agent_id 정렬): (agent_id, bundle, path, current_task) — **bundle·path 내부
  순서는 보존한다**(순서가 CBBA 실행 의미이므로 정렬 금지); winning_bids(task_id 정렬);
  float 직렬화 고정규칙 }`. patch 판정은 graph 구조뿐 아니라 대상 task의 status에 의존하므로
  (READY → 승인·release, RUNNING → `E_RUNNING_LOCKED`, COMPLETED → terminal 규칙)
  `patch_hash`만으로는 판정을 재현할 수 없다.
- 기록 정책:
  - field-level schema 오류 → `patch_hash = null`, `pre_state_hash`는 선택.
  - field-level schema 통과(이후 conflict든 통과든) → `patch_hash`·`pre_state_hash` **둘 다** 기록.
  - `E_PATCH_CONFLICT` / whole-graph 거부 / reconciliation 거부 / accepted → 둘 다 기록.
  - `validate_patch_ops()`가 현재 schema 오류와 conflict를 한 함수에서 처리하므로, 구현 시
    hash 생성 시점을 field-level validation과 conflict 검사 **사이**로 분리한다.


이전 저장소에서 재사용하는 것은 전부 `docs/PROVENANCE.md`에 원본 경로·source commit·재사용
이유를 기록한다. 재사용 후보: TaskGraph 연산 패턴, 상태 전이(READY/PENDING recompute) 패턴,
CBBA consensus/bundle 핵심과 보상형태, event logger 패턴, SimExecutor event-loop 패턴,
structured-output backend 패턴, environment/reference 분리 패턴, 도메인 독립 테스트
유틸리티. 가져오지 않는 것: 이전 연구 계약, 기존 task enum, UAV 중심 타입, 기존 domain
invariant, 기존 prompt, 기존 scenario/world, 기존 결과값, 기존 테스트 파일 내용(패턴만 배우고
새로 작성).

**알려진 이식 시 위험**: 이전 저장소 `execution/mission_runner.py`는 "매 iteration 시작
시점에 계산해둔 ready_ids를, 그 iteration의 완료 이벤트 처리 이후에도 stale한 채로 deadlock
판정에 쓰는" 버그가 있었고, 자매 파일 `tools/run_urban_px4_mission.py`에는 이 버그가 아직
안 고쳐진 채 남아 있다(확인됨). 이 프로젝트의 `execution/mission_runner.py`를 작성할 때는
deadlock 판정 직전에 반드시 recompute를 한 번 더 하는 패턴으로 **처음부터** 작성하고, 최소
재현 테스트(단일 agent, A→B 체인)를 P4 게이트에 넣는다 — 옛 테스트 파일을 복사하지 않고
독립적으로 새로 작성한다.

P4 구현체는 `execution/executor.py`의 `SimExecutor`다(D-011). "아무도 작업 중이 아니고
dispatch할 것도 없다"고 판단하기 직전에 `recompute_ready()`를 호출한 뒤 epoch를 한 번 더
시도하고, 그래도 진전이 없으면 남은 task 목록과 함께 종료한다(무한 루프 없음). 최소 재현·
부분진전 후 deadlock·정상 완주 테스트가 P4 게이트다.

**종료 사유 분리(D-012)**: `ExecutionResult`는 `termination` ∈ {`COMPLETED`, `DEADLOCK`,
`STEP_LIMIT`}을 기록한다. `deadlocked`는 `termination == DEADLOCK`일 때만 참이다. `max_steps`
소진(`STEP_LIMIT`)은 deadlock이 아니다 — §13의 deadlock 집계에 섞이면 안 된다. **마지막
허용 step에서 모든 task가 완료되면 `COMPLETED`로 판정한다**(D-013) — loop 종료 후 최종
상태를 다시 확인한다.

**precedence violation 판정(D-013)**: agent가 predecessor 완료 전에 목적지로 **출발**했는지로
본다 — `task_completion[p] > task_departure[s]`이면 위반. 도착 시각(`task_start`)이 아니라
출발 시각(`task_departure`)과 비교해야 "READY 전 이동 금지"의 의미가 맞다.

**STEP_LIMIT 결과의 지표(D-014)**: busy time은 dispatch 시점에 예정 travel+dwell 전체를
더하므로, 실행 중 task가 남은 채 `STEP_LIMIT`으로 끝나면 `agent_utilization`이 1을 넘을 수
있다(미래 busy가 분자에, 완료 시각까지만 분모에). `STEP_LIMIT` 실행의 `makespan`·
`agent_utilization`은 평가 지표로 쓰지 않는다 — `agent_utilization`은 빈 dict로 반환한다.
`COMPLETED`/`DEADLOCK`에서는 실행 중 agent가 없으므로 정상이다.

**실행 중 새 epoch의 입찰(D-012)**: 이미 RUNNING인 task는 그 agent의 residual path scoring에서
제외한다(도착 지점으로 위치 투영 + RUNNING task는 path에서 임시 제거). 아직 시작 안 한
held task만 residual path에 남긴다. 경매 후 RUNNING task를 실제 실행 path 선두에 다시
병합한다. RUNNING task를 residual path에 남기면 그 이동·dwell·reward가 이중 계산돼 winner가
바뀐다.

**assignment 정리(D-012)**: task를 COMPLETED로 바꿀 때 `task.assigned_agent = None`,
`agent.current_task = None`, bundle/path에서 제거한다(§10 assignment invariant). 과거 winner는
`ExecutionResult.assignments`에만 보존한다. 완주 후 내부 MissionState는 §10 assignment
invariant를 통과해야 한다.

---

## 15. 구현 순서와 게이트

| 단계 | 내용 | 완료 게이트 |
|---|---|---|
| P0 | 독립 저장소, 이 계약 확정 | 이 문서 커밋 |
| P1 | semantic scene, Agent, TaskGraph, route graph, reference fixture | 아래 P1 게이트 전 항목 |
| P2 | deterministic whole-graph Validator + MissionPatch reconciliation | 단일 트랜잭션 + 다중 트랜잭션 우회 테스트 전부 통과 |
| P3 | platform-aware CBBA, rolling READY-frontier epoch | reference fixture에서 capability/precedence violation 0, 모든 UGV bid가 route distance 사용 확인 |
| P4 | 2D executor, end-to-end reference mission | 완주 + 위반 0 + deadlock 최소 재현 테스트 통과 |
| P5 | LLM Step1/Step2/repair(mock 테스트) | mock 기반 파이프라인 테스트 통과 |
| P6 | 최소 9개 입력 평가 + 결과 시각화 | precision/recall/원시개수 표 산출 |
| P6.5 | 통합 runner: 검증된 LLM graph를 plan-time CBBA(`allocate`)와 event-driven executor(`SimExecutor`)로 **각각** 실행 (fork — allocate 결과는 executor에 전달되지 않음) | 대표 명령 A1/B1/C1: annotation exact-match + 무위반 완주(`termination == COMPLETED`) + graph/hash/model/assignment 감사 JSON (D-025, D-026) |
| P7 (선택, 보류) | Gazebo integration | 20~30초 대표 클립 |
| P8.0 | RQ3 계약: §1 재서술, §18, `VALIDATOR_VERSION` 1.4 + `patch_hash`/`pre_state_hash`, zone response point + priority 7, `allocate` 사용 규정, §17 정정 | v1.25 / D-027 커밋 |
| P8.1 | interaction schema + `Referent` state + 결정론적 grounder + `register_incident`(scene 트랜잭션) + canonical patch builder + `AddTask` op priority 제거 | referent 해석 단위테스트 / 모든 (incident, step)에 유효 `MissionPatch` / `register_incident`가 Validator-loadable Scene + **원본 Scene 불변 검증**(scene_hash·모든 필드) / `VALIDATOR_VERSION == "1.4"` / 전체 단위테스트 green |
| P8.2 | orchestrator + intent interpreter (게이트 `MockBackend`) | I1~I8 headless / session lifecycle·NO_CHANGE·referent 규칙 강제 / CLARIFICATION·QUERY·UNSUPPORTED 턴에 `session.state`·`session.scene` identity 불변 / 턴별 감사 JSON |
| P8.3 | 최소 Streamlit UI + 통합 `event_log` + 구조화된 후보 선택 (D-031, D-032) | 자동: private append boundary가 보존하는 `event_log` 순서 = event 순서 유일 진실 원천, `event_seq` 직렬화 파생, `t1 t2 EXECUTION t3` JSON 순서 일치, execution이 `turn_count` 미소비 / `ClarificationReason`이 ambiguity와 unknown·missing을 구분 / `select_clarification_candidate`는 LLM 호출 0·`input_kind=CANDIDATE_SELECTION`·`resumed_from_turn_id` 기록 / pending은 `AMBIGUOUS_ENTITY`이면서 나머지 필수 slot이 완전할 때만 생성, pending 중 자유 입력은 LLM 미전달·실행 비활성, 잘못된 후보는 pending 유지, 취소는 graph·scene·referent 불변 / 실행 성공·비정상 종료·예외가 모두 `ExecutionAudit`로 기록 / scene 로더가 정규화 빈 incident id 거부 / `VALIDATOR_VERSION == "1.4"` / 전체 단위테스트 green. 수동: §18.12 최소 표시 항목(1~14) 전부 렌더 / 실제 API 3턴 / PLANNING↔EXECUTED↔EXECUTION_FAILED / 실행은 결정론 버튼 / live 실패 시 cached·mock + 모드 배너(cached를 live로 표시 금지) |
| P8.4 | N=12 정량 평가 (live) | grounder-only + end-to-end 표 / dialogue + turn + 지표별 분모 보고 / gold 사전 커밋 / 감사 JSON |
| P8.5 | UI TaskGraph DAG + 정적 2D 임무 지도 (D-043, D-044) | 순수 view(렌더 전후 `pre_state_hash`·`scene_hash` 불변) / `RenderSpec`의 node·edge 집합이 `TaskGraph`와 정확히 일치 / **`TaskStatus` 6종 전부**(`CANCELLED` 포함) 고정 색, enum 순회로 검사 / UAV·UGV task 구분 / 같은 입력 → 같은 `RenderSpec`(Figure·이미지 바이트가 아님) / artist `gid`에 task·edge id, 저장 직전 Figure를 spec과 대조(PNG 파싱 아님) / UAV 직선 vs UGV route-graph polyline 구분 / `RouteGraph` 경로 API가 모든 node 쌍에서 `shortest_path_distance`와 일치, P3/P4 골든 불변 / plan-time·paused runtime·completed execution 구분 / paused는 마지막 확정 위치 + RUNNING target + in-progress leg(보간 주장 금지) / online update 후 재렌더에 신규 task 반영 / headless(Agg) 테스트 통과 / **matplotlib import 실패를 흉내 내도 UI 기동** / 발표 그림도 같은 renderer 산출 / 애니메이션 범위 밖 / P9 수치와 기존 테스트 불변 |
| P9.0 | RQ4 온라인 명령·선택적 재할당 계약 | v1.36 / D-039 커밋 |
| P9.1 | `SimExecutor` checkpoint/resume | P4 one-shot 골든 불변 / task-completion event pause / checkpoint→restore 결과가 중단 없는 실행과 동일 / 상태·시각·위치·경로·누적 지표 보존 |
| P9.2 | bidder-connected bundle-suffix release + incremental CBBA | COMPLETED/RUNNING 불변 / 영향 없는 ASSIGNED 보존 / release suffix 일관성 / 재경매 뒤 assignment invariant·capability·precedence 위반 0 |
| P9.3 | paused-session REPORT/UPDATE/QUERY + typed audit | 턴 전체 atomicity / accepted update에서만 runtime 교체 / clarification·거부·오류 시 runtime identity·hash 불변 / 온라인 assignment 변화와 release 집합 감사 / advance 예외 뒤 runtime 보존 + checkpoint 재개 가능(D-041) |
| P9.4 | Streamlit checkpoint·계속·온라인 명령 UI + 비교 실험 | 명령 전/후 assignment·release·현재 시각 표시 / 대표 scenario 완주 / no-reset·full-reset·selective 원시 지표 비교 + `suffix_extra_release_count` 보고 / fixture strict schema / 실패 후 재개 버튼(D-041) |

**P1 완료 게이트** (v1.1, D-002 — 전 항목 통과해야 P1 완료 선언 가능):

1. `Agent`, `Task`, `TaskGraph`, `RouteGraph` 단위테스트 통과.
2. semantic scene과 reference fixture가 오류 없이 로드됨.
3. reference fixture가 §3 고정 형상과 일치: task 12, edge 6, 계산된 초기 READY 6, 초기
   PENDING 6.
4. fixture의 모든 task_id 유일, 모든 target이 존재하는 area/incident 참조, 모든 edge 양끝이
   존재하는 task 참조, cycle 없음.
5. route graph 도달가능성 전수 검증 통과 — 모든 UGV 대상 task(`GROUND_INSPECTION`,
   `GROUND_SUPPRESSION`)의 `access_node_id`가 route graph에 존재하고 모든 UGV 시작
   노드에서 도달 가능(§8).

---

## 16. 시간 부족 시 cut-order

1. Gazebo 통합(P7)
2. exact solver 비교
3. 반복 LLM 호출
4. 18개 입력을 최소 9개로 축소
5. 시각화 애니메이션 폴리싱
6. RQ3(P8) 전체

**절대 자르지 않음**: canonical reference graph, deterministic whole-graph Validator,
heterogeneous capability allocation, platform-aware travel cost, 2D end-to-end 실행, 최소
9개 LLM 평가, raw output과 validated output 비교.

---

## 17. 명시적 범위 제외

실제 RGB/thermal perception, 자동 화재 탐지, 물리적 화재 안정성 판정, `WATER_LOAD`,
suppressant 잔량과 재보급, same-agent resource coupling, obstacle removal, relay deployment,
target tracking, 일반 조건부 task graph, SLAM, 동적 장애물 회피, 일반 road planner, LLM 직접
agent 할당, 새로운 CBBA 알고리즘 제안, P0~P6.5 완료 전 RQ3 구현(P7 Gazebo는 RQ3의
선행조건이 아님 — §16 cut-order·§15·§1 참고, D-027), MP4MR A~G 체계 복제, 모든
agent가 최소 1개 task를 받아야 한다는 제약, bundle 길이 ≥2를 Phase 1 invariant나 완료 게이트로
쓰는 것(P8에서는 실험 precondition으로 재검토 가능 — §15 P8), 임의 wall-clock 시점의 강제
중단, RUNNING task abort·migration, 실행 후 terminal graph 수정, 자동 perception event,
P9 정책의 전역 최소성·최적성 주장.

---

## 18. Operator–LLM Planning Session (P8, D-027)

### 18.1 범위

실행 개시 전의 다중 턴 임무 계획 세션. 대화·graph 수정·incident 등록은 전부 실행 전.
"실행" 버튼(결정론적 UI 동작, LLM intent 아님) 이후 첫 버전에서: graph 수정 불가, incident
추가 불가, `NEW_MISSION`/`REPORT_INCIDENT`/`UPDATE_MISSION` 전부 `UNSUPPORTED`, 저장된
`ExecutionResult` 조회(`QUERY_STATUS`)만 가능. 실패 시 동일 graph 재시도만 허용하고 graph
변경은 금지한다.

P8 결과만으로는 "임무 실행 중 자연어 업데이트"를 주장하지 않는다. 이는 P9 §19의 별도
checkpoint/resume 게이트를 모두 통과한 경우에만 선택 확장 결과로 주장한다. perception·자동
화재 탐지 없음(§3 재확인) — 신규 incident는 운용자의 명시적 보고로만 시스템에 진입한다.
고정 5종 task 어휘에서는 어떤 유효 patch도 기존 task의 predecessor 집합을 바꾸지 못하므로
(D-006), 정상 대화에서 기존 assignment의 release·재할당은 발생하지 않는다.

### 18.2 지원 대화 행위 (5종 고정)

`NEW_MISSION` / `REPORT_INCIDENT` / `UPDATE_MISSION` / `QUERY_STATUS` / `UNSUPPORTED`.
미지원(→ `UNSUPPORTED`, 고정 템플릿 응답): 자유 채팅, task/incident 취소·삭제, 재우선순위,
agent 지정 할당, 비-canonical graph 편집, incident 위치 변경, mid/post-execution patch.

### 18.3 파이프라인

```
LLM intent classifier (API-compatible flat wire schema로 kind + slot 추출)
→ strict discriminated OperatorIntent로 결정론적 변환
→ 결정론적 grounder (referent 해석, slot 완전성 → RESOLVED | CLARIFICATION_REQUIRED)
→ NEW: generate_mission(raw utterance) / REPORT: register_incident /
  UPDATE: canonical patch builder → apply_patch / QUERY: MissionState·Result 읽기
→ graph 변경 턴이면 allocate() plan-time re-analysis
→ TurnResult + 감사 로그
```

`context_for_llm()`은 원문 대화 전체가 아니라 structured session에서 매번 생성한 요약
(scene + 현재 상태 + `recent_referents`)만 넘긴다.

### 18.4 session lifecycle

| intent | 전제 | 위반 시 | commit |
|---|---|---|---|
| NEW_MISSION | `state is None` AND `phase == PLANNING` | 기존 mission 있음 → CLARIFICATION(교체 안 함) / 실행됨 → UNSUPPORTED(새 session 안내) | 성공 시 `state` 최초 설정 |
| REPORT_INCIDENT | zone_ref가 scene zone에 매칭. mission 무관 / `phase == PLANNING` | 미지 zone → CLARIFICATION / 실행됨 → UNSUPPORTED | 성공 시 `scene`만 |
| UPDATE_MISSION | `state ≠ None` AND incident grounding됨 AND `phase == PLANNING` | mission 없음 → CLARIFICATION / 모호 → candidate 목록 / 실행됨 → UNSUPPORTED | `apply_patch` accepted 시 `state`만 |
| QUERY_STATUS | 없음 (mission·실행 무관) | — | 없음 |
| UNSUPPORTED | — | 고정 템플릿 응답 | 없음 |

- 한 턴 = 최대 한 commit(scene 또는 graph, 둘 다 아님). 무효 턴 = 어떤 것도 commit 안 함.
  이전 등록 incident는 유지.
- 같은 zone에 incident 복수 등록 허용. ID = `FIRE_SITE_<next n>` 결정론 생성.
- `CLARIFICATION_REQUIRED`·`QUERY_STATUS`·`UNSUPPORTED` 턴은 `apply_patch`/`generate_mission`/
  `register_incident`/`allocate`를 호출하지 않는다(명시 invariant + `session.state`·
  `session.scene` identity 불변 테스트).
- entity ambiguity로 인한 `CLARIFICATION_REQUIRED`는 세션에 `PendingClarification`을 저장한다
  (§18.13). pending이 있는 동안 자유 자연어 입력은 LLM에 전달되지 않고(후보 선택·취소만
  허용), 실행 버튼은 비활성이다. pending은 세션당 최대 1개.

### 18.5 referent 규칙

`recent_referents`(K = 3, 최근 3턴)에 추가: 성공한 `REPORT_INCIDENT` / 정상 grounding된
`UPDATE_MISSION`(commit 또는 `NO_CHANGE`) / **명시 id로 지칭한** `QUERY_STATUS`. 추가 안 함:
clarification, unsupported, 모호 referent, 미지 zone·incident, 실패한 REPORT·UPDATE, 그리고
**지시어로 해석된 `QUERY_STATUS`**. 같은 최신 턴에 후보 ≥2 → 무조건 `CLARIFICATION_REQUIRED`.

**지시어 QUERY가 window를 갱신하지 않는 이유(D-029)**: 갱신하면 "거기 상태 알려줘"를 반복하는
것만으로 K=3 만료가 무한히 연장되어, window가 "언제 도입됐는가"가 아니라 "window 자신을 통해
언제 다시 언급됐는가"를 재는 자기참조가 된다. 읽기 전용 조회는 새 지칭이 아니다. 명시 id로
부른 QUERY는 새 지칭이므로 갱신한다. `UPDATE_MISSION`은 해석 경로와 무관하게 갱신한다 —
graph를 실제로 바꾸는(또는 이미 충족됐음을 확인하는) 행위이므로 그 incident는 실제로 최근이다.

**incident referent 해석 우선순위(D-028)** — grounder는 **fail-closed**다. 해석되지 않는
비어 있지 않은 표현은 절대 최근 referent나 단일 incident로 흘러내리지 않는다:

1. 표현이 알려진 incident id와 정규화 매칭 → **RESOLVED**. 정규화 형태가 같은 id가 2개
   이상이면(예: `FIRE_SITE_1`과 legacy `FIRE SITE 1`) 조용히 하나를 고르지 않고
   **CLARIFICATION_REQUIRED**.
2. 표현이 **명시적으로 허용된 지시어**(아래 목록)가 아니면 → **CLARIFICATION_REQUIRED**.
   "FIRE_SITE_9.", "FIRE-SITE-9", "북쪽 화재"처럼 구체적이지만 해석 불가능한 표현이 여기
   해당한다. 이것이 fail-closed의 핵심이며, §18.11의 "잘못된 추측 비율"을 0으로 유지하는
   장치다.
3. 등록된 incident가 없음 → **CLARIFICATION_REQUIRED**(그 사실을 알린다).
4. 최근 live 턴의 referent 후보: 정확히 1개 → **RESOLVED**, 2개 이상 → **CLARIFICATION**.
5. live referent 없음: 등록 incident가 **정확히 1개면 RESOLVED**(고를 대상이 없으므로
   모호성이 존재하지 않는다), 2개 이상이면 **CLARIFICATION**.

**허용 지시어 목록(D-028)**: 표현이 없거나(`None`/공백), 또는 정규화 후 다음 중 하나와
일치할 때만 4·5단계의 fallback을 시도한다 — `거기`, `그것`, `그거`, `그 화재`, `그 화재 지점`,
`해당 화재`, `해당 화재 지점`, `이 화재`, `저 화재`, `현장`, `그 현장`, `there`, `it`,
`that`, `that fire`, `this fire`, `the fire`, `the incident`, `that incident`.
목록에 없는 표현은 2단계에서 걸러진다. 목록 확장은 이 계약 개정으로만 한다.

**5단계(단일 incident 자동 선택)는 명시적 정책이다**: 표현이 없거나 허용 지시어인데 등록된
incident가 하나뿐이면 되묻지 않고 그것으로 해석한다. §18.11의 clarification precision/recall
gold는 이 규칙을 전제로 작성한다.

**후보 선택은 이 우선순위를 다시 타지 않는다(D-031)**: grounder가 entity ambiguity로
CLARIFICATION을 낸 뒤 운용자가 후보를 클릭하면, 선택된 `entity_id`는 이미 검증된 scene id이므로
`select_clarification_candidate`가 grounder를 재경유하지 않고 그대로 resolved로 주입한다(§18.13).

### 18.6 NO_CHANGE

`UPDATE_MISSION` 요청의 task·edge가 이미 전부 존재 → `NO_CHANGE`: 중복 `AddTask` 생성 안 함,
"빈 patch commit" 아님, `state` identity 유지, `allocate` 재호출 안 함, "해당 대응 단계는
이미 계획에 포함돼 있습니다" 응답. 요청 step이 현재 chain보다 낮음(task 제거 필요) → 첫
버전엔 제거 없음 → `NO_CHANGE`, chain 축소 안 함.

### 18.7 LLM / 결정론 경계

**interaction intent classifier**의 LLM 역할은 kind 분류와 slot 추출로 제한한다 —
state·scene·graph 미변경, task_id·agent·priority·좌표·MissionPatch·CLARIFICATION 미생성.
내부 schema의 진실 원천은 `kind` discriminator를 가진 strict `OperatorIntent` 5종이다.
다만 OpenAI structured-output API는 이 union이 생성하는 중첩 `oneOf`를 받지 않으므로(D-034),
API 호출에는 평면 `IntentWireEnvelope`를 쓴다. wire 출력은 `kind`와 모든 slot 키를 갖고 쓰지
않는 slot은 `null`이어야 한다. `extra="forbid"`·`strict=True`와 kind별 cross-field 검증으로
무관한 slot의 비-null 값을 거부한 뒤, 결정론적 adapter가 해당 `OperatorIntent` 하나로
변환한다. 이는 LLM 역할이나 허용 intent를 넓히지 않는 transport compatibility 계층이다.
단 `NEW_MISSION`으로 확정된 경우에는 기존 **RQ1 `generate_mission()`**(§12)이 별도로
task_type·target·dependency edge를 생성한다(이건 P5/P6에서 이미 검증된 경로이며 그대로
재사용).

결정론적 코드: grounder(referent — scene zone_id + name alias 매칭), canonical patch builder,
`register_incident`(response point는 zone 사전 정의값), `apply_patch`, `allocate`.
clarification·NO_CHANGE·거부·UNSUPPORTED 응답은 전부 결정론적 코드의 결과다. 운용자가
미지원 graph 변경을 요구하면 intent classifier/grounder 단계에서 `UNSUPPORTED` 또는
clarification으로 끝나야지, invalid patch를 만들어 Validator에 전달하지 않는다.

### 18.8 session 상태 경계

Scene = 환경 + fleet 정의(interaction 과정에서 불변 취급). `MissionSession.state`는
`interaction/session.py`의 `fresh_session_state(graph, scene)`로 생성 — graph·fleet 명시
복제, scene의 mutable `Agent` 객체 공유 금지(`core/`는 `Scene`을 몰라야 하므로 이 helper는
interaction 계층에 둔다). `phase` ∈ {`PLANNING`, `EXECUTED`, `EXECUTION_FAILED`}.
`plan: AllocationResult | None`과 `execution: ExecutionResult | None`을 분리 저장. 실행
실패 시 `EXECUTED`로 두지 않고 `EXECUTION_FAILED`.

`register_incident`는 새 `incidents` dict만 만들고 `zones`·`route_graph`·`fleet`은 구조적으로
공유할 수 있다. 단 이 객체들은 interaction 과정에서 불변으로 취급하며, **호출 후 원본 Scene의
`scene_hash`와 모든 필드가 변하지 않았음을 테스트한다.** `MissionSession`의 `Agent`만
`fresh_session_state`가 별도 복제한다.

### 18.9 감사 로그 (`data/interaction_runs/<session_id>.json`)

`session_id`는 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`를 만족해야 하며, `MissionSession` 생성
시점에 강제한다(D-030). session id는 파일명이 되므로 이것이 자유 문자열이면 `../`나 절대
경로가 위 디렉터리 밖의 파일을 덮어쓸 수 있다 — 즉 이 문법 제약이 "감사 기록은 항상
`data/interaction_runs/` 안에 있다"는 위 경로 보장의 근거다.

**event 순서(D-031, D-032)**: 세션은 turn과 execution을 **단일 event stream**에 실제 발생
순서대로 append한다. 저장소는 private `_event_log: list[TurnAudit | ExecutionAudit]`이며,
`MissionSession.append_event()`만 append할 수 있다. 이 경계는 event 타입과
`event.session_id == session.session_id`를 검사한다. 외부에는 tuple인 read-only
`event_log` property를 노출한다. `handle_turn`은 `TurnAudit`을, 실행 함수는 실행이 끝나는 즉시
`ExecutionAudit`을 append하며, 실행 후 `QUERY_STATUS`는 그 뒤에 `TurnAudit`을 append한다.
**append된 list의 순서가 event 시간 순서의 유일한 진실 원천이다** — 병합 정렬용 index를
따로 저장하지 않는다. `event_seq`(0..N-1)는 dataclass 필드가 아니라 직렬화 시 `enumerate`로
파생한다(감사 파일에서 순서를 확인하기 위한 파생값이지 두 번째 상태가 아니다). execution은
`turn_count`를 소비하지 않는다. `turn_log`는 `event_log`에서 `TurnAudit`만 거르는 read-only
tuple property다. writer는 순서를 만들어내지 않고 이미 append된 순서와 session id만 검증한다.

`write_session_audit`가 검증하는 것: 모든 event의 `session_id == session.session_id` /
직렬화된 `event_seq`가 `0..N-1` / append 후에도 기존 event의 상대 순서 불변 /
`t1 → t2 → EXECUTION → t3` 실제 순서가 JSON에서 동일 / execution이 `turn_count` 미소비.

턴별(`event_type: TURN`) — `TurnAudit`(D-029): `session_id`, `turn_id`, `utterance`,
`mode`(live|cached|mock), `outcome`(COMMITTED|NO_CHANGE|ANSWERED|CLARIFICATION|UNSUPPORTED|
REJECTED|TURN_ERROR), `intent_kind`, `extracted_slots`(추출된 slot 원문 — `up_to_step`·
`zone_ref`·`target_phrase`가 여기 들어간다),
`grounding`{`status`, `entity_kind`, `entity_id`, `via`, `clarification`, `candidates`},
`pre_scene_hash`, `post_scene_hash`, `pre_graph_hash`, `post_graph_hash`, `pre_state_hash`,
`patch_hash`,
`patch`{accepted, error_codes, added_tasks, added_edges, directly_released_tasks,
status_changes},
`generation`{approved, failure_category, graph_hash, error_codes, repaired}|null(NEW_MISSION),
`plan_assignment_changes`{`added`, `removed`, `changed`},
`scene_changed`, `state_changed`, `referent_noted`, `answer`, `resolved_models`,
`error_type`·`error_detail`(`TURN_ERROR`일 때 원인 — 영구 기록에 남긴다),
`input_kind`(`NATURAL_LANGUAGE` | `CANDIDATE_SELECTION` | `CLARIFICATION_CANCEL`),
`resumed_from_turn_id`(후보 선택 턴이 재개한 clarification 턴의 `turn_id`, 그 외 null),
`selected_entity_id`(후보 선택으로 확정된 id — LLM 추출값이 아니므로 `extracted_slots`에
섞지 않고 별도 필드; D-031).

`grounding`에는 `reason`(`ClarificationReason` 또는 null)을 추가한다(D-032). 고정 값은
`AMBIGUOUS_ENTITY`, `UNKNOWN_ENTITY`, `MISSING_ENTITY`, `NO_ENTITIES`, `MISSING_MISSION`,
`MISSING_STEP`, `ACTIVE_MISSION`, `PENDING_SELECTION`, `INVALID_SELECTION`이다. 후보 목록이
있다는 사실만으로 ambiguity라고 간주하지 않는다 — unknown 표현에도 재설명을 돕기 위한 known
entity 목록이 들어갈 수 있다. 오직 `reason == AMBIGUOUS_ENTITY`인 결과만 구조화 선택 pending의
후보다.

`grounding`은 incident뿐 아니라 zone 해석에도 쓰이므로 `entity_kind` + `entity_id`로 일반화한다.
`via` ∈ {`explicit`, `referent`, `sole_incident`}는 §18.5 우선순위의 어느 단계로 해석됐는지를
기록한다 — clarification 평가(§18.11)에서 "명시 지칭"과 "지시어 해석"을 구분하는 데 필요하다.

`resolved_models`는 **그 턴에 발생한 모든 backend 호출**을 담는다 — intent 분류 1회뿐 아니라
`NEW_MISSION`이 유발하는 Step1/Step2/repair 호출까지 포함한다(§14 재현성).

실행(`event_type: EXECUTION`): `pre_graph_hash`, `pre_scene_hash`, `plan_assignments`,
`execution_termination`, `execution_assignments`, `makespan`, `capability_violations`,
`precedence_violations`, `mode`, `started_at`, `finished_at`, `error_type`, `error_detail`.
결정론적 진입점은 `execute_session(session, *, mode)`이며 `mode`를
`live|cached|mock` 중 하나로 명시적으로 받는다. `COMPLETED` → `phase = EXECUTED`;
`DEADLOCK`·`STEP_LIMIT` 또는 executor 예외 → `phase = EXECUTION_FAILED`. 예외도
`execution_termination = ERROR`와 원인을 감사하고 밖으로 전파하지 않는다. 실행 전제(state와
plan 존재, phase가 `PLANNING` 또는 `EXECUTION_FAILED`, pending 없음) 위반은 UI 배선 오류이므로
실행 event를 만들기 전에 `ValueError`로 거부한다. `EXECUTION_FAILED`에서의 재호출은 §18.1의
"동일 graph 재시도"이며 새 `ExecutionAudit`을 append하고 최근 실행 결과를 교체한다.
`EXECUTED`에서는 재실행하지 않는다. 실행은 graph·scene·plan을 바꾸지 않는다.

- `plan_assignment_changes`: `added`(이전 plan에 없고 새 plan에 존재), `removed`(이전에
  있고 새 plan에 없음), `changed`(둘 다 존재하나 agent가 달라짐). **이는 실행 중 재할당이
  아니라 두 plan-time 분석 결과의 차이다.** "reassigned"라는 표현은 쓰지 않는다.
- `directly_released_tasks`는 `PatchResult` 값이며 정상 시나리오(canonical chain 연장)에서는
  항상 빈 목록이다.
- hash 정책은 §14 참고. cache key = `model` + `prompt/schema version` + `context hash` +
  `utterance`(동일 문장이라도 session context가 다르면 응답이 달라진다).

### 18.10 신규 incident 등록

`REPORT_INCIDENT(zone_ref)` → grounder가 scene `zone_id` + name alias를 결정론적으로 매칭 →
그 zone의 사전 정의 `reported_incident_position`(UAV target)과
`reported_incident_access_node`(UGV route node)를 compiler가 선택한다. **LLM은 좌표를 만들지
않는다.** ID = `FIRE_SITE_<next n>`. priority = **고정 7**(NL urgency 추출은 후속 평가 항목).
zone별 response point는 `scenarios/industrial_park.yaml`에 사전 고정하고 `scene_hash`의 zone
payload에 포함한다(§14). 무효 `REPORT` → scene 불변.

**정규화가 비는 id 방지(D-031)**: scene YAML 로더는 `normalize_identifier(incident_id)`가
빈 문자열이 되는 incident id(예: `"!!!"`)를 거부한다. `register_incident`는 `FIRE_SITE_<n>`을
생성하므로 항상 문자열 핸들이 있다. 정확한 주장은 "**지원되는 scene YAML 로딩 경로와
`register_incident()` 경로에서는 정규화가 비는 incident id가 생성되지 않는다**"이며,
"구조적으로 불가능"은 아니다(로더를 우회해 `Scene`을 직접 구성할 수 있다). 이 규칙이
§18.13의 후보 선택이 항상 재매칭 가능한 id만 제시하도록 보장한다.

정규화 함수는 계층 역전(`scenarios/scene.py`가 `interaction/`을 import)을 피하기 위해
`scenarios/naming.py`에 둔다: `normalize_identifier()`(대문자화 + 영숫자만),
`normalize_zone_ref()`(한국어 `구역`/`지역` 접미사 제거 후 `normalize_identifier`). scene
loader와 incident grounder는 `normalize_identifier`를, zone grounder는 `normalize_zone_ref`를
공유한다. incident id 매칭은 더 이상 zone 접미사를 제거하지 않는다(incident id는 접미사를
갖지 않는다).

### 18.11 평가 (interaction eval — P6/P6.5와 별개 실험)

`data/interaction_dialogues/*.yaml` — N = 12(family당 4: NEW-only / REPORT+UPDATE / QUERY /
ambiguous), 2~5턴. **LLM 첫 호출 전 gold 커밋.** 턴별 gold: 기대 intent kind, 기대 slots,
기대 grounding(RESOLVED+incident 또는 CLARIFICATION), 기대 patch ops, 기대 `apply_patch`
판정, 기대 released(canonical chain이면 항상 없음).

**12개 구성과 gold schema(D-035)**: family는 P6의 mission profile을 그대로 뜻한다.
`A=FULL_RESPONSE`, `B=AERIAL_ONLY`, `C=SELECTIVE_RESPONSE`이며, 각 family에 아래 네 dialogue
shape를 정확히 하나씩 둔다: (1) NEW-only 뒤 read-only 확인, (2) NEW→REPORT→UPDATE,
(3) NEW 뒤 QUERY, (4) NEW 뒤 entity ambiguity→구조화된 후보 선택. 따라서 id는
`A1..A4`, `B1..B4`, `C1..C4`이고 각 파일은 2~5 operator turn이다.

각 YAML은 top-level `id`, `family`, `profile`, `shape`, `rationale`, `turns`, `initial_graph`,
`final_graph`만 허용한다. 자연어 turn은 `input_kind=NATURAL_LANGUAGE`, `utterance`,
`intent`(kind와 기대 slot),
`outcome`, 선택적 `grounding`, 선택적 `patch`를 가진다. 후보 클릭 turn은
`input_kind=CANDIDATE_SELECTION`, `entity_id`, `outcome`, `grounding`, 선택적 `patch`를
가지며 LLM intent를 갖지 않는다. `patch`는 `accepted`, `added_tasks`, `added_edges`,
`directly_released_tasks`를 정확히 고정한다. canonical update의 release 정답은 빈 목록이다.
`initial_graph`와 `final_graph`는 P6 annotation과 같은 `recon_zones` + incident별 연속
workflow prefix다. initial은 첫 `NEW_MISSION`의 정답, final은 모든 turn 이후 정답이다.
loader는 알 수 없는 키·중복 id·family/profile/shape 불일치·2~5 turn 위반을 거부하고,
두 graph를 각각 scene 기준 whole-graph Validator로 self-check한다. 신규 incident가 있는
final은 gold REPORT를 결정론적으로 적용한 scene으로 검사한다. 모든 turn의 기대 patch에서
`added_tasks`/`added_edges`를 합친 집합은 `final_graph - initial_graph`와 정확히 같아야 한다.

operator/audit turn 수에는 자연어와 후보 선택을 모두 포함한다. **LLM intent classification과
slot extraction 분모에는 `NATURAL_LANGUAGE` turn만 포함**하고, 후보 선택은 LLM 0회인
결정론적 interaction 결과로 별도 집계한다. end-to-end 도중 앞선 실패 때문에 뒤 turn의 전제가
사라져도 그 turn을 숨기지 않고 실제 결과대로 오답/실패로 집계한다. dialogue별 session과
backend context는 분리한다.

두 평가:
- **grounder-only**: gold intent + gold slot 입력 → referent resolution accuracy,
  grounder-only clarification precision/recall, canonical patch op exact-match(**compiler
  회귀 게이트**이며 LLM 성능 지표가 아니다 — grounder가 결정론적이므로 ≈1.0).
- **end-to-end**: raw utterance(실제 LLM) → intent classification accuracy, slot extraction
  accuracy, end-to-end clarification precision/recall, 잘못된 추측 비율, state-mutation 없이
  끝난 clarification 비율, final graph exact match.

발표 헤드라인 = **end-to-end**. `invalid-update rejection correctness`는 헤드라인 지표가
아니다 — Validator fault-injection 회귀 테스트 + orchestrator 방어 테스트로 다룬다(정상
end-to-end 경로에서 canonical builder는 invalid patch를 만들지 않는다).

표본 보고: `12 dialogues / 총 XX turns / intent 평가 XX / referent 평가 XX /
clarification-positive XX / clarification-negative XX` — 지표별 분모를 전부 명시한다.
소표본이므로 원시 개수를 함께 제시한다.

### 18.12 UI 최소 표시 항목 (P8.3 게이트)

Streamlit UI는 최소한 다음을 표시한다(순수 view — orchestrator만 호출, 연구 로직 복제
금지):

1. 운용자–LLM 대화 기록
2. 현재 semantic scene(zones) + known incidents(id, zone, status)
3. 현재 TaskGraph(task_type/target, incident별 workflow 진행 단계)
4. 이번 utterance의 intent kind + 추출된 slot
5. grounder 결과: RESOLVED(적용 incident id 명시) 또는 CLARIFICATION_REQUIRED(질문 + 후보)
6. MissionPatch 적용 전후 diff(추가된 task/edge) 또는 NO_CHANGE
7. Validator 판정: accepted / rejected + error code
8. plan-time CBBA 할당 표(task → agent) + estimated makespan
9. `plan_assignment_changes`(added/removed/changed — "이전 계획 대비 차이", 재할당 아님)
10. `phase`(PLANNING / EXECUTED / EXECUTION_FAILED) 명시 표시
11. 실행 버튼(결정론적 동작) — 최종 graph를 P6.5 방식으로 실행
12. 실행 후: `ExecutionResult`(termination, task → agent, makespan, violation 수)
13. 실행 모드 배너(live / cached / mock) — cached·mock을 live로 표시하지 않는다
14. pending clarification이 있으면: 질문 + 후보 버튼(각 버튼 = 구조화된 `entity_id` 제출) +
    취소 버튼. pending 동안 자유 입력 창과 **실행 버튼은 비활성**(§18.13)

### 18.13 구조화된 clarification 후보 선택 (D-031)

grounder가 **entity ambiguity**로 `CLARIFICATION_REQUIRED`를 반환하면 세션에
`PendingClarification`을 저장하고, 운용자는 제시된 후보 중 하나를 **클릭**해 해소한다.
클릭한 문자열을 새 자연어 발화로 되먹이지 않는다 — 정규화가 비는 incident id(§18.10 이전
데이터)나 정규화 충돌이 있는 두 id는 재입력해도 명시 매칭이 안 되기 때문이다.

**`PendingClarification`(typed, frozen)**: `source_turn_id`, `intent_kind`,
`extracted_slots`, `unresolved_slot`(`zone_ref` | `target_phrase`), `entity_kind`
(`ReferentKind`), `candidates: tuple[str, ...]`, `original_utterance`.

**생성 조건 — entity ambiguity만(D-032에서 기계적으로 판별 가능하게 보강).** grounder는 모든
clarification에 위 §18.9의 `ClarificationReason`을 붙인다. pending은
`reason == AMBIGUOUS_ENTITY`이고 후보가 2개 이상이며, **선택 후 원래 처리를 재개하는 데 필요한
다른 slot이 모두 완전할 때만** 만든다. 특히 `UPDATE_MISSION`은 `up_to_step`까지 있어야 한다.
후보를 골라도 즉시 다시 다른 slot을 물어야 하는 턴은 pending으로 잠그지 않는다.

pending을 만드는 clarification:
- incident 후보 ≥ 2 (`UPDATE_MISSION`, 또는 `target_phrase`를 가진 `QUERY_STATUS` —
  지시어·명시 지칭 무관)
- zone 후보를 구조적으로 고를 수 있는 경우 (`REPORT_INCIDENT`)

pending을 만들지 **않는** clarification(후보 선택으로 풀 수 없음 → 자연어로 다시 말해야 함):
mission 자체가 없음 / `up_to_step` 누락 / 활성 mission이 있는데 `NEW_MISSION` / 등록 incident
0개 / fail-closed 2단계(해석 불가 표현) / `UNSUPPORTED`. **첫 버전의 구조화 선택은 entity
모호성만 해소한다** — 누락된 workflow step을 UI 선택으로 채우는 것은 별도 설계다.

**진입점 — LLM 없는 결정론 함수**
`select_clarification_candidate(session, entity_id, *, mode) -> TurnResult`:
(1) pending 존재 확인 (2) `entity_id in pending.candidates` (3) 그 entity가 현재 scene에도
존재 (4) 보류된 intent·slot 복원 (5) 선택 id를 이미 resolved된 값으로 주입 (6) 원래
`UPDATE`/`QUERY`/`REPORT` 처리 재개 (7) 성공 시 pending 제거.

**후보 선택도 감사되는 새 operator turn이다**: `turn_count` +1, 새 `TurnAudit`, LLM 호출 0,
`resolved_models = []`, `mode`는 현재 UI 실행 모드, `input_kind = "CANDIDATE_SELECTION"`,
`resumed_from_turn_id = pending.source_turn_id`, `selected_entity_id` 기록. grounding은
`via` = `explicit`이다 — 운용자가 후보를 직접 골랐으므로 지시어 해석이 아니라 명시 지칭이다.
`mode`는 backend에서 추론할 수 없으므로 caller가 `live|cached|mock` 중 하나를 명시한다.
referent window는 그 결과 §18.5의 **명시 지칭** 규칙을 따른다: `UPDATE_MISSION`과
`QUERY_STATUS` 모두 갱신, `REPORT_INCIDENT`는 새 incident를 추가. (원래 발화가 지시어였더라도
클릭으로 확정된 시점에는 명시 지칭이 된다.)

**pending 중 다른 입력.** pending 상태에서는 후보 선택 또는 취소만 허용한다. 일반 자연어
입력은 **LLM에 보내지 않고**, 새 감사 턴(`outcome=CLARIFICATION`,
`reason=PENDING_SELECTION`)으로 "후보를 선택하거나 취소해 주세요"라고 응답한다. pending과
graph·scene·state·plan·referent는 그대로다. 후보 목록에 없는 id 선택도 LLM 없이 새 감사 턴
(`reason=INVALID_SELECTION`)으로 남기고 pending을 유지한다.

`cancel_clarification(session, *, mode) -> TurnResult`는 UI의 결정론적 버튼이다. 취소도
`turn_count`를 1 소비하는 감사 턴이며 `input_kind=CLARIFICATION_CANCEL`,
`resumed_from_turn_id`를 기록하고 `outcome=CLARIFICATION_CANCELLED`로 끝난다. LLM 호출 0,
graph·scene·state·plan·referent 불변, pending만 제거한다. 후보 선택·취소의 `mode`도
`live|cached|mock` 중 하나를 caller가 명시한다. pending 동안 실행 버튼은 비활성이다.

**pending 제거 시점**: 성공한 `COMMITTED`·`NO_CHANGE`·`ANSWERED` / 명시적 취소 / phase 변경 ·
새 session → 제거. 후보가 아닌 id 선택 / Validator·`allocate`·기타 처리 실패 → **유지**
(재시도 가능). 한 세션에 pending은 최대 1개.

---

### 18.14 시각화 (P8.5, D-043)

지금까지의 UI(§18.12)는 전부 표와 숫자다. P8.5는 **이미 얻은 결과를 전달하기 위한 그림**을
추가한다 — 새 연구 주장이 아니고, 어떤 지표도 이 절에서 생기지 않는다.

**범위**: TaskGraph DAG + 정적 2D 임무 지도. **애니메이션은 범위 밖이다** — timestamp로
재구성은 가능하나 agent별 보간, dwell/travel 분리, online update 전후 assignment 연결,
Streamlit rerun 상태 관리, 발표 환경 성능이 모두 따라붙는다. 정적 그림에 순서와 상태를
표시하는 것으로 충분하다.

**순수 view 경계.** 렌더러는 `demo/visualization.py`에 두고 matplotlib `Figure`만 반환한다.
`core/`·`allocation/`·`execution/`·`interaction/`의 **할당·실행 의미는 바꾸지 않으며**, 연구
로직을 복제하지 않고 이미 계산된 값(`MissionState`, `AllocationResult`, `ExecutionResult`,
executor checkpoint)만 그린다. **예외 하나(D-044)**: `RouteGraph`에 최단경로의 **경유 node를
돌려주는 read-only 조회 API**를 추가하는 것은 허용한다 — 현재 `shortest_path_distance()`는
거리만 주므로, 이것 없이 UGV polyline을 그리려면 view가 Dijkstra를 재구현해야 하고 그것이야말로
"연구 로직 비복제" 위반이다. 요구사항: 기존 `shortest_path_distance()`와 **같은 tie-break**,
반환 경로의 누적 weight가 그 거리와 **모든 node 쌍에서 일치**(테스트), 입력 graph 불변, 동일
입력 동일 경로, 도달 불가 시 기존 API와 일관된 반환. **P3/P4 골든 makespan(359.8 / 257.9)은
불변이어야 한다.** **렌더 전후로 `pre_state_hash`와 `scene_hash`가 변하지 않음을 테스트로 고정한다** —
live `SimExecutor`를 넘길 때가 유일한 실질 위험이므로, 가능하면 checkpoint(이미 frozen deep
snapshot)를 입력으로 받는다.

**결정론은 `RenderSpec`으로 판정한다(D-044).** matplotlib `Figure`는 equality 의미가 없고
(`Figure == Figure`는 identity 비교라 항상 False), PNG·PDF 바이트는 matplotlib 버전·font·
backend·metadata·antialiasing에 따라 환경마다 달라질 수 있다. 따라서 결정론 게이트의 대상은
이미지가 아니라 **그림의 의미 명세**다 — node id → (좌표, 색, 모양), edge 목록처럼 그리기 직전의
구조화된 값. 공개 렌더러는 계속 `Figure`를 반환하되 그 `RenderSpec`을 만드는 helper를 따로 두고
테스트한다: 같은 입력 → 같은 `RenderSpec`, `RenderSpec`의 node 집합 == `TaskGraph`의 node 집합,
edge도 마찬가지. 그림의 artist에는 task id·edge id를 `gid`로 부여해 **저장 직전 `Figure`의
artist 집합을 그 `RenderSpec`과 대조**한다(D-045). PNG는 `gid`를 보존하지 않으므로 이것은
**저장된 PNG 파일 자체를 파싱해 node·edge를 감사한다는 뜻이 아니다**. SVG는 element id로
보존할 수 있으나 SVG 산출은 P8.5 범위 밖이다.

force-directed 배치처럼 실행마다 흔들리는 layout은 쓰지 않는다 — 위 결정론이 곧 발표 그림의
재현성이다. 이 도메인의
graph는 구조가 규칙적이므로(zone recon 집합 + incident별 선형 chain) **행 = incident, 열 =
workflow 단계**의 결정론적 격자로 충분하고, 새 incident가 새 행으로 나타나 online update가
눈에 띈다.

**DAG가 표시할 것**: task type 축약명, dependency 화살표, **`TaskStatus` 6종 전부**의 고정 색
(`PENDING` 회색 / `READY` 파랑 / `ASSIGNED` 보라 / `RUNNING` 주황 / `COMPLETED` 초록 /
`CANCELLED` 진한 빨강), UAV task와 UGV task의 모양 또는 테두리 구분. `CANCELLED`는 §10에서
cancellation이 미지원이라 정상 시나리오에 나타나지 않지만 Validator와 checkpoint가 지원하는
유효 상태이므로, renderer는 enum 전체를 안전하게 처리한다 — 색 표를 `TaskStatus`를 순회하며
검사해, 나중에 멤버가 늘면 테스트가 먼저 깨지게 한다(D-044). **그려진 node·edge 집합은 `TaskGraph`의 것과
정확히 일치해야 한다** — 이것이 online update가 재렌더에서 즉시 보인다는 보장의 근거다
(그림 안에 graph hash를 적으라는 뜻이 아니다).

**2D 지도가 표시할 것**: zone·incident 위치, agent 초기 위치, agent별 고정 색, task 위치와
수행 순서 번호. **UAV 이동은 직선, UGV 이동은 route graph를 따르는 polyline**으로 구분한다
(§8의 이종 이동 모델이 그림에서 드러나야 한다). plan-time 분석과 실제 실행을 **한 그림에
겹치지 않고** 분리해 보여준다. 완료 후에는 전체 실행 경로를 그린다.

**paused runtime의 위치는 정의되지 않는다(D-044).** `SimExecutor`는 task가 완료될 때만
`agent.position`(UGV는 `access_nodes`)을 갱신하므로, RUNNING 중인 agent를 현재 state에서 읽으면
**출발 위치**가 나온다. 애니메이션과 보간이 범위 밖인 이상 "현재 위치"를 그릴 방법이 없다.
따라서 pause 상태에서는 **마지막 확정 위치 + RUNNING target + 둘을 잇는 dashed in-progress
leg**로 그리고 남은 assignment를 함께 표시한다. UI 레이블도 `Current position`이 아니라
`Last confirmed position` / `RUNNING target` / `In-progress leg`를 쓴다. **task 수행 중 실제
물리 pose를 보간했다고 주장하지 않는다** — 보간은 UAV 직선뿐 아니라 UGV route 상의 거리 기반
보간까지 필요해져 P8.5 범위를 넘긴다.

**의존성.** matplotlib은 기존 `viz` extra이며 headless(Agg) 렌더여야 한다(§12 `plots.py`와
동일). **`viz`가 없으면 UI는 죽지 않고 §18.12의 표로 degrade한다.** 이때 견뎌야 하는 것은 함수
호출 실패가 아니라 **모듈 import 실패**다(D-044) — `demo/app.py`가 `demo/visualization.py`를
top-level에서 import하고 그 모듈이 top-level에서 matplotlib을 import하면, degrade 분기에
닿기 전에 앱 전체가 죽는다. lazy import든 `ImportError` 포착이든 방식은 구현 판단이되,
**matplotlib이 없는 상태를 흉내 내 앱이 기동되는지**를 테스트로 고정한다.

**발표 그림.** 슬라이드용 PNG/PDF는 이 렌더러가 생성한다. UI와 발표 자료가 서로 다른 그리기
경로를 갖지 않게 하려는 것이며, 이는 §14 재현성의 연장이다.


## 19. Online command injection and selective reallocation (P9, D-039)

### 19.1 범위와 lifecycle

P9는 P8의 실행 전 planning session을 없애지 않고 그 뒤에 붙는 선택 확장이다. 운용자가 기존
계획을 먼저 만들고 온라인 실행을 시작하면, simulator가 **task completion event**까지 진행한
뒤 `EXECUTION_PAUSED`가 된다. 이때 `REPORT_INCIDENT`, `UPDATE_MISSION`, `QUERY_STATUS`를
처리하고 다시 다음 event까지 진행하거나 끝까지 실행할 수 있다. `NEW_MISSION`은 paused
상태에서 허용하지 않는다.

지원하지 않는 것: 임의 wall-clock 시각에 thread를 강제 정지, RUNNING task abort·migration,
이미 COMPLETED인 task/edge 수정, 실행 완료 뒤 graph 수정, perception이 자동으로 incident를
만드는 것. 신규 incident는 여전히 운용자의 `REPORT_INCIDENT`로만 들어온다. executor 시간은
wall-clock이 아니라 기존 2D discrete-event simulation time이다.

phase는 `PLANNING → EXECUTION_PAUSED ↔ EXECUTION_PAUSED → EXECUTED|EXECUTION_FAILED`이고,
**runtime이 보존된 `EXECUTION_FAILED`에서는 `EXECUTION_PAUSED`로 되돌아올 수 있다**(아래 재시도).
각 pause/continue action은 LLM turn이 아니며 `turn_count`를 소비하지 않는다. pending
clarification이 있으면 실행을 계속할 수 없다. P8의 one-shot `execute_session()`은 보존하고,
P9 UI가 명시적으로 온라인 실행을 선택한 경우에만 checkpoint 경로를 사용한다.

**online 재시도(D-041, D-042 정정).** advance 도중 **예외**가 나면 세션은 마지막 정상
checkpoint를 그대로 들고 `EXECUTION_FAILED`가 되며 `execution`은 `None`으로 남는다. 이 상태는
막다른 길이 아니다 — §18.1이 one-shot에 "실패 시 동일 graph 재시도"를 허용하듯, online도
**보존된 checkpoint에서 재개**할 수 있다. 재시도가 성공하면 아직 남은 task가 있으면
`EXECUTION_PAUSED`, 완주하면 `EXECUTED`, 또 실패하면 다시 `EXECUTION_FAILED`다. 재시도는 새
실행이 아니라 같은 runtime의 재개이므로 simulation time과 완료 prefix를 되돌리지 않는다.

재시도 조건은 정확히 **`phase == EXECUTION_FAILED` AND `runtime is not None` AND
`execution is None`**이다(D-042). `execution`이 있다는 것은 executor가 예외로 죽은 게 아니라
`DEADLOCK`/`STEP_LIMIT`라는 **결과**로 끝났다는 뜻이며, 같은 상태를 재개하면 결정론적으로 같은
종료를 반복할 뿐 아니라 기록된 종료 결과를 지우고 phase를 `EXECUTION_PAUSED`로 되돌리게 된다.
그런 terminal 상태는 재개하지 않는다.

`(phase, execution, runtime)` 조합의 의미를 소비자(UI·감사 독자)가 구분할 수 있어야 한다:

| phase | `execution` | `runtime` | 뜻 | 다음 행동 |
|---|---|---|---|---|
| `EXECUTION_FAILED` | 있음 | 없음 | one-shot이 `DEADLOCK`/`STEP_LIMIT`로 끝남 | 동일 graph one-shot 재시도 |
| `EXECUTION_FAILED` | 없음 | 없음 | one-shot executor 예외 | 처음부터 one-shot 재시도 |
| `EXECUTION_FAILED` | 없음 | **있음** | online advance 예외 | **checkpoint에서 online 재개** |
| `EXECUTION_FAILED` | 있음 | 있음 | online 실행이 `DEADLOCK`/`STEP_LIMIT`로 종료 | terminal — 재개 금지, `QUERY_STATUS`만 또는 새 session |
| `EXECUTION_PAUSED` | 없음 | 있음 | 정상 일시정지 | 다음 event로 계속 |

예외 실패에 가짜 `ExecutionResult`를 만들지 않는다 — 실제로 실행 결과가 없었기 때문이며,
원인은 `ExecutionAudit`의 `error_type`·`error_detail`에 남는다.

### 19.2 checkpoint/restore 의미

`SimExecutor.checkpoint()`는 다음을 빠짐없이 복제한다: 현재 simulation time, 전체
`MissionState`(task status/assignment, agent position/bundle/path/current_task, winning bids),
UGV access node, agent별 현재 task·finish time·누적 busy time, assignments·winning bids,
task departure/start/completion 시각, consensus round history, 누적 UAV/UGV 거리, 그리고 다음
resume에서 READY frontier epoch가 필요한지 여부. bundle/path **내부 순서는 보존**한다.

`restore(checkpoint, scene)` 뒤 끝까지 실행한 결과는 같은 event에서 중단하지 않고 실행한
결과와 termination, completed, assignment, task timing, makespan, 거리, workload, violation이
같아야 한다. checkpoint는 외부가 바꿀 수 없는 deep snapshot이어야 하며 원 executor와 mutable
객체를 공유하지 않는다.

pause 지점은 `_advance()`가 가장 이른 completion 시각으로 진행하고 그 시각에 끝난 task를
모두 COMPLETED 처리한 직후다. 동시에 끝나지 않은 다른 agent task는 RUNNING인 채 보존할 수
있다. 새 READY 상태는 recompute하되 다음 CBBA epoch는 명령을 받을 기회를 주기 위해 pause
뒤 resume 또는 accepted update에서 수행한다.

### 19.3 선택적 release 정책 (bidder-connected selective release)

accepted online patch를 candidate checkpoint 복제본에 적용한 뒤 다음 순서로 release 집합을
결정한다.

1. patch로 새로 추가됐고 현재 `READY`인 task 각각의 eligible bidder set을 계산한다. bidder는
   platform과 required capabilities를 모두 만족하는 agent다.
2. 기존 `ASSIGNED`(아직 시작 안 함) task 중 bidder set이 위 새 task bidder union과 교집합인
   task를 **직접 영향 task**로 본다. COMPLETED·CANCELLED·RUNNING·새 task는 대상이 아니다.
3. 직접 영향 task를 보유한 agent별로 CBBA `bundle`에서 가장 이른 영향 task를 찾고, 그
   위치부터 뒤의 `ASSIGNED` task 전체를 release한다. 같은 task를 `path`, task owner, bid에서도
   원자적으로 제거한다. 이 bundle-suffix 확장은 **보수적 구현 규칙이지 실증된 연구 주장이
   아니다** — 아래 "suffix 확장의 실증 범위" 참고.
4. 새 READY task와 released task를 하나의 READY frontier로 `run_epoch`에 넣는다. 보존된
   ASSIGNED/RUNNING task는 `held`, RUNNING agent의 남은 시간은 기존 residual-path
   `start_delay`로 유지한다.

이 정책은 같은 상태·patch에서 항상 같은 release 집합을 만들지만, 전역 최소 reset이나 최적
makespan을 증명하지 않는다. `no-reset`(기존 held 전부 유지), `full-reset`(모든 미시작 ASSIGNED
release), `selective`를 비교할 때도 우열의 일반화가 아니라 고정 scenario의 원시 결과로만
보고한다.

**suffix 확장의 실증 범위(D-041, D-042 정정).** 3단계가 직접 영향 task 뒤의 **비**영향 task까지
추가로 release하려면 한 agent의 bundle에 영향 task와 비영향 task가 섞여 있어야 한다.

**관측된 사실**: 대표 fixture와 현재 테스트가 다루는 경로 — 신규 incident에 전체 workflow
chain을 추가하는 online update — 에서는 즉시 `READY`가 되는 것이 `THERMAL_RECON` 하나뿐이고
그 bidder union이 UAV 전체다. 그러면 모든 UAV task가 영향, 모든 UGV task가 비영향이 되고
bundle은 한 agent(UAV이거나 UGV)의 것이므로 그 경로에서는 섞인 bundle이 나오지 않았다.
따라서 이 실행들에서는 항상 `released == directly_affected`이고

    suffix_extra_release_count = |released − directly_affected| = 0

**단정하지 않는 것(D-042)**: 이것을 "도메인 전체에서 섞인 bundle이 불가능하다"로 일반화하지
않는다. `build_chain_patch`는 신규 incident의 전체 chain뿐 아니라 **기존 incident의 부분
workflow 연장**도 만든다. 예를 들어 `THERMAL_RECON`이 이미 COMPLETED인 incident를
`SUPPRESSANT_DROP`까지 늘리면 신규 READY task의 bidder는 R1/R2이고 `AREA_RECON`은 비영향이
되므로, S-agent bundle이 `THERMAL_RECON`(영향) → `AREA_RECON`(비영향) 순서를 갖는다면 suffix
확장이 발생할 여지가 있다. 그런 상태가 현재 CBBA·priority 아래에서 실제로 도달 가능한지는
**검증하지 않았다**.

따라서 P9가 실증한 것은 **"신규 READY task와 입찰자가 겹치는 기존 미시작 assignment만
release/rebid한다"**까지이고, bundle suffix 확장이 실제로 동작했다고 주장하지 않는다. 규칙을
코드에 남기는 이유는 위와 같은 다른 조합에서 bundle prefix commitment를 깨지 않기 위한
보수적 안전장치이기 때문이다 — 단위테스트로 **분기의 정확성**은 고정하되, 그것을 end-to-end
실증으로 기술하지 않는다(D-006과 같은 원칙).

### 19.4 online turn atomicity와 감사

paused turn도 기존 intent classifier·strict schema·grounder·canonical patch builder·whole-
graph Validator를 재사용한다. `REPORT_INCIDENT`는 scene만 갱신하며 그 자체로 재할당하지 않는다.
그 incident에 대한 accepted `UPDATE_MISSION`이 graph를 실제로 늘릴 때만 §19.3을 수행한다.
`QUERY_STATUS`, clarification, `NO_CHANGE`, `UNSUPPORTED`, rejected patch에는 runtime 교체나
CBBA 호출이 없다.

온라인 UPDATE는 현재 executor checkpoint를 deep clone한 candidate에서
`apply_patch → selective release → run_epoch`까지 모두 성공한 뒤에만 session runtime/state를
한 번에 교체한다. 어느 단계든 실패하면 scene·graph·task status·agent state·simulation time·
assignment와 원 runtime object identity를 전부 보존하고 `TURN_ERROR` 또는 `REJECTED`로
감사한다.

`CheckpointAudit(event_type=EXECUTION_CHECKPOINT)`은 simulation time, 이번 event에서 완료된
task, 누적 completed, RUNNING map(task/agent/finish time), READY, active assignment를 기록한다.
accepted online UPDATE의 `TurnAudit`에는 `OnlineReallocationAudit`을 포함한다: policy version,
simulation time, patch added task, directly affected task, selectively released suffix, preserved
active assignment, before/after assignment, assignment changes, 새 epoch consensus rounds.
최종 완료/실패는 기존 `ExecutionAudit`을 사용하되 전체 실행 시작 시각과 종료 시각을 기록한다.
여기서 preserved active assignment는 release 집합에 들어가지 않았고 전후 owner도 같은
commitment만 뜻한다. release된 뒤 우연히 같은 agent가 다시 낙찰한 task는 owner change는 0이지만
preserved로 세지 않는다.

### 19.5 P9 대표 실험

고정 initial graph와 고정 checkpoint event를 먼저 commit한다. 같은 checkpoint clone에 같은
incident REPORT+UPDATE를 적용해 `no-reset`, `full-reset`, `selective` 세 정책을 실행한다.
각 정책에서 다음 원시값을 저장한다: completed/RUNNING 보존 수, released 수와 id, 보존된
ASSIGNED 수와 id, 기존 task owner change 수, 신규 task assignment, 추가 consensus rounds,
최종 makespan·UAV/UGV 거리·capability/precedence violation·termination, 그리고 직접 영향 task
목록과 **`suffix_extra_release_count`**(= released − directly_affected). 마지막 값은 §19.3
3단계가 이 실행에서 실제로 동작했는지를 드러내며 **`selective`에만 정의된다** — `full-reset`은
suffix와 무관하게 모든 미시작 ASSIGNED를 release하므로 같은 차이를 계산해도 suffix의 효과가
아니고, `no-reset`은 아무것도 release하지 않는다. 두 정책은 `null`로 보고한다. 현재 대표
fixture의 `selective` 값은 0이며, 0이라는 사실을 숨기거나 suffix가 동작한 것처럼 서술하지 않는다.

평가 fixture도 연구 결과의 입력이므로 **strict schema**로 읽는다(D-023과 동일 원칙):
`str`이 와야 할 자리의 `int`를 `str()`로, `float`가 와야 할 자리의 문자열을 `float()`로
세탁하지 않는다. simulation time은 유한할 뿐 아니라 음수가 아니어야 한다. 후속 drift guard가 오염을 막더라도 오류가 늦고 불명확해지므로, 타입 위반은
로드 시점에 거부한다.

필수 안전 게이트: 세 정책 모두 같은 완료 prefix와 RUNNING commitment를 보존, 최종
`COMPLETED`, capability/precedence violation 0. selective는 full-reset보다 적어도 한 개 이상의
미시작 assignment를 더 보존해야 하며, no-reset과 달리 적어도 한 개의 기존 미시작 task를
release/rebid해야 한다. 이 조건은 알고리즘 일반 성질이 아니라 대표 fixture의 식별 조건이다.
