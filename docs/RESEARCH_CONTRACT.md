# RESEARCH_CONTRACT.md — 단일 진실 원천

버전 v1.67 (D-071). 이 문서와 코드가 충돌하면 이 문서가 우선한다. 변경 시 이 문서를 먼저 고치고
`docs/DECISIONS.md`에 이유를 append한다.

- v1.67 (D-071): §18.9 `TurnAudit`에 `timing` 필드 추가 — 턴의 wall-clock을 LLM 호출별
  (`IntentWireEnvelope`/`Step1Output`/`Step2Output`/`RepairOutput`)과 deterministic 나머지로
  분해한다. `TimedBackend` 래퍼가 `backend.complete()`를 계측하고 `handle_turn`이
  `total_s`를 잰다. 판정·결과·골든 불변. latency profiling(단일 vs single-call 비교)의 전제.
- v1.66 (D-070): D-069의 "새 episode(sim time 0 리셋, ContinuousRuntime 재시작)"를
  "**이어지는 timeline**"으로 재서술. 실행/완료 중 `NEW_MISSION`은 새 graph를 현재 sim
  time·현재 agent 위치에서 seed한 executor로 `EXECUTION_PAUSED` 상태에서 이어 실행한다.
  `ContinuousRuntime`은 boundary에서 stale segment를 버리고 같은 시각에 새 graph 재생을
  바로 이어간다(멈춤·재시작 없음). "반복 순찰 아님" 한계 명시.
- v1.65 (D-069): §22.7.1 확장 — `NEW_MISSION`을 `EXECUTION_PAUSED`(실행 중 safe
  checkpoint)에서도 받아 새 episode를 연다. 옛 mission의 미완료 task는 버려지고 `EXECUTION`
  audit을 받지 못한다(`EXECUTION_FAILED`는 여전히 거부). continuous 재생 중 `NEW_MISSION`이
  수용되면 `ContinuousRuntime`이 episode 경계에서 멈추고 native UI가 새 episode로 새
  `ContinuousRuntime`을 시작해 이어 재생한다. §23.4.1 큐 경로도 동일. 골든·Validator·allocator 불변.
- v1.64 (D-068): (A) §22.7.1 — terminal 뒤 session이 `NEW_MISSION`·`UPDATE_RESOURCES`도
  받아 새 mission episode를 연다(UAV 위치 이어받음, UGV 기지 재시작, 완료 graph에 덧붙이지
  않음). "임무 완료" 종착점 제거, phase는 EXECUTED 유지하되 UI는 "대기" 표시. 반복 순찰은
  여전히 미구현(§22.7 한계 유지). (B) §3 — `IncidentStatus.RESOLVED` 추가. `GROUND_SUPPRESSION`
  완료 checkpoint에서 incident가 `RESOLVED`로 전이, §18.14 지도에서 흐린 회색 X.
- v1.63 (D-067): §22.8 승인 유예를 "감지 직후 한 segment"에서 "남은 recon 전체"로 넓힌다.
  화재가 미결정이어도 recon은 계속 진행하고(대응 task는 승인 전 graph에 없음), recon terminal에
  도달했는데 미결정이면 그때만 halt한다. recon 종료 전 답 → mid-recon rebid, 종료 후 답 →
  follow-on episode. `ContinuousRuntime`의 pre-advance halt 검사 제거, terminal 검사에 추가.
- v1.62 (D-066): §22.8 승인 게이트를 "감지 즉시 정지"에서 "clock 계속, 결정은 기록 후 다음
  boundary에서 적용"으로 재서술한다. 감지된 화재는 그 다음 segment를 유예로 받고, 나머지
  agent는 계속 움직인다. clock이 다음 boundary에 도달했는데 미결정이면 그때만 halt.
  `PendingFireApproval`에 `decision`/`approved_scope` 추가, `resolve_fire_approval` →
  `record_fire_decision` + `apply_recorded_fire_decisions`. 결정론·골든 불변.
- v1.61 (D-065): §22.8 sensor 화재 감지 승인 게이트. `SimulatedFireField`가 공개하는
  `FIRE_DETECTED`는 자동 대응하지 않고 **무조건** 운용자에게 되묻는다. `pending_approvals`
  FIFO 큐(zone id 순), `PendingClarification`류의 resumable pending 상태(새 phase 없음),
  결정론적 승인/거절(LLM 없음), 승인 시 §22.3 transaction·거절 시 무변경. 승인 큐가
  §23.4.1 자유텍스트 큐보다 우선. 단일 `SimulatedFireSource`·운용자 `REPORT_INCIDENT`는
  게이트 밖. Validator·allocator·골든 불변.
- v1.60 (D-064): §23.4 continuous tick driver 구현. `demo.animation.SegmentView.frame_at`이
  committed segment 안의 임의 sim-time pose를 주고, `desktop.controller.ContinuousRuntime`이
  boundary마다 checkpoint commit + sensor observation + queued 명령 1건을 **동기적으로**
  처리한다(별도 thread 없음). §23.4의 "LLM 호출을 executor mutation과 분리"를 "boundary 정지
  중 동기 처리, 결과는 boundary-anchored라 latency-무관"으로 재서술. 결정론·골든 불변.
- v1.59 (D-063): §23.4.1로 P13.4 continuous runtime의 입력 queue 정책을 확정한다. 재생 중
  자유텍스트 명령은 FIFO 큐(`queued_commands`)에 쌓이고 safe boundary마다 1건씩 기존
  `handle_turn`으로 처리한다. P12.6의 단일 `queued_command` 1건 제한을 대체하되 "덮어쓰기
  금지"는 유지하고, 미소비 항목은 운영자가 취소할 수 있다(graph·scene·runtime 불변). 승인
  게이트(§22.8, 후속)가 이 큐보다 우선한다.
- v1.58 (D-062): §22.2에 seeded 다중 latent fire field를 추가한다. 단일 하드코딩 fixture
  대신 정수 `seed`로 알려진 후보 zone에서 `count`개(기본 2)를 결정론적으로 뽑아 각 zone의
  `AREA_RECON`을 trigger로 하는 latent fixture 튜플을 만든다. 지형·fleet·route는 전부
  기존대로 고정이며 오직 "어느 zone에 화재가 있는가"만 seed로 정해진다. 기존
  `LatentIncidentFixture` 단일 경로는 P12 재현용으로 유지한다. §22.2 불변식(scene·prompt·
  `scene_hash` 분리, 1회 공개, rerun 멱등)은 그대로다. 승인 게이트(§22.8)는 후속(Phase D).
- v1.57 (D-061): task vocabulary를 5종 → **3종**으로 줄인다. `THERMAL_RECON`(대응 전 열원
  확인)과 `SUPPRESSANT_DROP`(UAV 공중 투하)을 제거하고 incident workflow를
  `GROUND_INSPECTION → GROUND_SUPPRESSION` 2단계로 한다. UAV는 정찰 전담(AREA_RECON), 실제
  진압은 UGV 지상 대응만 한다. THERMAL_RECON의 "행동 전 확인"은 §22.8 승인 게이트(사람)가
  대체한다. `THERMAL_SENSOR`·`SUPPRESSANT_PAYLOAD` capability도 제거(요구하는 task 없음).
  `VALIDATOR_VERSION` 1.4 유지(판정 규칙 불변, 어휘 집합만 축소). P3/P4/P6/P9/P12/P13
  골든·평가는 D-060과 함께 재계산·재실행한다.
- v1.56 (D-060): §5의 UAV를 **동일 기체 3대**로 통합한다(Scout 2 + Response 2 분리 폐기).
  총 5대 = UAV 3 + UGV 2. agent id는 U1/U2/U3/G1/G2. (capability·workflow는 D-061에서
  추가로 축소됐다.) 결정론적 골든(P3/P4/P6.5/P9)은 재계산하고 LLM 평가(P6/P12/P13)는 새 fleet로 재실행하되
  D-060 이전 Live artifact는 "fleet v1(2/2/2)"로 보존한다.
- v1.55 (D-059): 발표·CBBA 시각화용 확장 reference scene을 §3.1로 허용한다. 동일 task
  vocabulary(5종)·fleet(6대 2/2/2)·workflow predecessor·Validator 규칙을 그대로 쓰고 zone·
  incident·route node 수만 늘린다. `industrial_park`(4 zone)과 P3/P4 골든값·P1~P6.5 게이트는
  불변이며 확장 scene은 게이트 대상이 아니다. 확장 scene도 loader의 §8 reachability·§5
  eligible-bidder(모든 task type ≥2)·§7 priority 검증을 동일하게 통과한다. incident-empty
  변형은 §23.3.1의 dynamic-world 방식대로 native UI의 선택 가능한 world profile로 등록할 수
  있고, D-058의 기본 profile(`patrol_park`)은 유지한다. 이 scene에서는 어떤 평가 수치도
  만들지 않는다.
- v1.54 (D-058): native UI의 기본 진입점을 `dynamic-world + live`로 바꾼다. 이 profile은
  zone·fleet·route만 있는 incident-empty scene을 로드하며 latent fixture, reference graph,
  mock script를 갖지 않는다. mock/cached 연구 재현 profile은 명시적으로 선택해야 하고 Live
  실패를 scripted 응답으로 fallback하지 않는다.
- v1.53 (D-057): P13.2의 실행 중 team 교체 의미를 고정한다. session/runtime의
  `MissionState.agents`는 scene 전체 fleet의 실행 이력과 마지막 확정 위치를 보존하는 roster이고,
  `active_team`은 새 입찰·dispatch에 참여할 수 있는 agent 집합이다. 제외된 RUNNING agent는 roster와
  현재 commitment에는 남되 active team에서는 즉시 빠지고, 완료 checkpoint에서 future work 없이
  idle이 된다. executor checkpoint는 active team도 함께 보존한다.
- v1.52 (D-056): P13 **dynamic natural-language mission runtime**과 P14 ROS2/Gazebo adapter를
  추가한다. 고정된 semantic world·task vocabulary·안전 규칙 위에서 Live 자연어가 초기 graph와
  검증 가능한 resource constraint를 만들며, 결정론적 allocator가 실제 active team과 assignment를
  선택한다. 실행 중 입력은 계속 움직이는 wall-clock 2D runtime에서 받되 다음 task-completion
  safe boundary에서 atomic하게 적용한다. 특정 agent·대수·배제를 무조건 UNSUPPORTED로 처리하던
  P12.6 경계는 P13에서만 supersede한다. LLM 직접 agent assignment, 좌표 생성, RUNNING task
  abort/migration은 계속 금지한다.
- v1.51 (D-055): 성공적으로 끝난 online 실행의 terminal checkpoint를 후속 incident response
  episode의 시작점으로 재사용한다. `EXECUTED`에서 `REPORT_INCIDENT`와 canonical
  `UPDATE_MISSION`을 좁게 허용해 COMPLETED prefix는 그대로 두고 새 workflow task만 추가한 뒤
  `EXECUTION_PAUSED`로 되돌려 자동 재생한다. 이는 진행 중 재할당 수치와 구분해 감사한다.
  또한 단순 초기 정찰의 `정찰만`을 future-fire policy로 오인하지 않도록 intent prompt를
  명시화하고 cache namespace를 `p12-v4`로 올린다.
- v1.50 (D-054): native 발표 UI를 명령 생성 뒤 자동 checkpoint 재생으로 전환하고, 재생 중
  자연어 입력 한 건을 대기열에 받아 현재 frozen segment가 끝나는 안전한 task-completion
  checkpoint에서 기존 orchestrator로 처리한다. 같은 checkpoint의 simulated sensor event를
  먼저 commit한 뒤 대기 명령을 처리하며, accepted 변경은 P9 selective release/rebid 후 다음
  segment부터 보인다. 이는 임의 wall-clock interrupt나 RUNNING task migration이 아니다. 일반
  platform-class 표현(UAV 정찰, UGV/지상 로봇 점검·진압)은 workflow 설명으로 허용하되 특정
  agent id·수량·배제는 계속 UNSUPPORTED다. native 기본 scenario는 sensor detection으로 둔다.
- v1.49 (D-053): D-052의 bounded intent repair 사용 여부를 제3자가 cache 파일 없이 감사할
  수 있도록 각 `TurnAudit`에 `intent_repair_attempted`와 `intent_repair_recovered`를 기록한다.
  둘은 LLM 결과나 판정이 아니라 해당 턴의 transport provenance이며, 두 번째 실패에서도
  attempted=true/recovered=false가 남는다. 기존 첫 Live·held-out Live artifact는 수정하지 않고,
  새 필드를 포함하는 cached exact replay를 별도 artifact로 둔다.
- v1.48 (D-052): P12 첫 Live counterfactual 4/8을 원시 결과로 보존한다. intent wire가
  kind와 무관한 slot을 채워 strict schema에서 거부되면 live/cached 경로에 한해 같은 발화와
  context로 **정확히 한 번** error-guided schema repair를 허용한다. 두 번째 schema 오류나 API
  오류는 그대로 `TURN_ERROR`이며 slot을 삭제하거나 reference 응답으로 대체하지 않는다. zone
  reference만 한국어 위치 조사 `에서`/`에` 하나를 제한적으로 제거한다. 개선 후 결과는 사전
  고정한 별도 held-out paraphrase로 평가하고 첫 결과를 덮어쓰지 않는다.
- v1.47 (D-051): P12 **LLM-driven incident contingency**를 추가한다. LLM은 최초 자연어에서
  초기 task graph와 별도로 `FIRE_DETECTED`/운영자 신고에 적용할 response step을 추출하고,
  실행 중 한 턴의 화재 신고에서는 zone과 명시적 response step을 추출한다. 정찰 완료가 만든
  결정론적 simulated observation과 운영자 보고는 같은 atomic incident transaction → Validator
  → P9 selective release/rebid 경로로 수렴한다. 실제 perception·임의 조건식·LLM 직접 할당은
  여전히 제외하며, counterfactual Live 평가로 입력에 따라 graph/policy/target이 달라짐을 보인다.
- v1.46 (D-049): 발표용 **native desktop operator console**을 P11로 추가한다. 한
  `QApplication`에서 운용자 대화·제어 창과 별도 2D simulator 창을 함께 열고, 기존
  `MissionSession`·orchestrator·P9 online action·P10 `PlaybackSpec`만 소비한다. desktop
  view는 CBBA·Validator·executor clock을 복제하지 않으며, checkpoint에서만 후속 입력을
  허용한다. Streamlit은 감사·회귀용 fallback으로 보존한다. 새 연구 주장·실험·버전 변경 없음.
- v1.45 (D-048): P10 UI에 서로 다른 목적의 실행 모드 둘을 명시한다. **checkpoint 재생**은
  전역에서 가장 이른 task completion마다 멈춰 후속 명령을 받으므로 다른 agent는 TRAVEL/DWELL
  중일 수 있다. UI가 정지 원인 task와 계속 RUNNING인 agent 상태를 표시한다. **끝까지 연속
  재생**은 같은 checkpoint primitive를 구간별로 반복해 terminal까지 보여주되 중간 입력은 받지
  않고 오류·비정상 종료에서 즉시 멈춘다. 실행·감사 의미와 버전·수치는 불변.
- v1.44 (D-047): D-046의 "마지막 frame은 after checkpoint의 정적 runtime 의미와 일치"를
  정정한다. 같은 completion 시각에도 다른 agent는 계속 RUNNING일 수 있고, P8.5 정적 지도는
  그 agent를 마지막 **확정** 위치에 두지만 P10은 기록된 travel/dwell schedule로 보간한다.
  따라서 완료 agent만 확정 target과 일치하고, RUNNING agent는 그 시각의 보간 위치라 정적
  marker와 다를 수 있다. 마지막 frame의 time·activity·task는 after checkpoint와 일치해야 한다.
- v1.43 (D-046): P10 checkpoint 구간 2D playback을 추가한다. P8.5에서 제외했던 애니메이션을
  일반 실시간 simulator가 아니라 **기존 P9 task-completion checkpoint 사이의 결정론적
  시각화**로 한정해 연다. 실행 상태는 먼저 원자적으로 다음 checkpoint에 commit되며, UI는 그
  전후의 frozen snapshot에서 UAV 직선·UGV route polyline을 simulation time 기준으로 보간해
  재생한다. 재생 중 입력은 받지 않고 재생 완료 뒤 checkpoint에서만 후속 명령·선택적 재할당을
  허용한다. 물리 pose·동역학·임의 wall-clock interrupt는 주장하지 않는다. 연구 판정과 실행
  의미는 불변이므로 `VALIDATOR_VERSION` 1.4, `ONLINE_POLICY_VERSION`과 P3/P4/P9 수치는 불변.
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

**RQ5 (선택 확장)**: 자연어 최초 명령에서 LLM이 초기 정찰 graph와 화재 발생 시의 대응 범위를
분리해 추출하고, 실행 중 UAV 정찰 완료가 낸 simulated `FIRE_DETECTED` observation 또는
운영자의 자연어 화재 신고를 동일한 검증·증분 할당 경로로 처리할 수 있는가? 같은 scene에서
명령의 대응 단계가 달라지면 생성되는 정책과 incident workflow prefix가 달라지고, 같은 명령에서
보고된 zone이 달라지면 신규 incident target과 경로가 달라져야 한다.

RQ5의 LLM 역할은 초기 objective·고정 2단계 workflow의 response prefix·운영자 발화의 zone을
구조화하는 데 한정한다. 화재 존재 여부, 좌표, priority, capability, Validator 판정, agent 선택,
release 집합과 실행 성공을 LLM이 결정하지 않는다. `FIRE_DETECTED`는 실제 영상 인식이 아니라
사전 고정된 latent-world fixture가 특정 `AREA_RECON` 완료 뒤 공개하는 결정론적 observation이다.
따라서 결과를 "자동 화재 인식" 또는 물리적 실시간 perception으로 부르지 않는다.

**RQ6 (선택 확장)**: 고정된 semantic world와 fleet에서 자유 형식 자연어 명령이 초기·후속
task graph와 검증 가능한 자원 제약을 만들고, 결정론적 Validator/CBBA가 이를 실행 가능한 active
team과 assignment로 변환하며, 계속 진행되는 2D runtime이 실행 중 입력을 다음 안전 경계에서
atomic하게 반영할 수 있는가?

RQ6에서 LLM은 intent, target/workflow slot, agent class·수량·포함·배제 **제약만** 구조화한다.
특정 task→agent 배정, 좌표·경로·priority·capability, constraint feasibility, release 집합과 commit
여부는 결정론적 코드가 정한다. 지원 ontology 밖의 표현은 자유롭게 추측하지 않고 clarification
또는 UNSUPPORTED로 끝난다. P13의 2D runtime은 kinematic simulation이며 robot telemetry가 아니다.
P14가 연결되기 전에는 Gazebo/물리 실행 또는 arbitrary wall-clock preemption을 주장하지 않는다.

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
소화 성공이나 소화 소요시간을 산출하거나 주장하지 않는다.
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
incident의 `GROUND_SUPPRESSION` task가 완료된 checkpoint에서 그 incident는
`RESOLVED`로 전이한다(D-068). 이는 실행이 만든 결정론적 상태 변화이며 LLM 판정이 아니다.
`RESOLVED` incident는 §18.14 지도에서 흐린 회색 X로 그려 진압됨을 표시하고, scene_hash에는
`status.value`로 그대로 반영된다.

화재 위치·상태는 semantic scene 또는 운용자·외부 시스템 보고로만 시스템에 진입한다. P12의
patrol fixture에서는 초기 planner/LLM context에 보이지 않는 `latent_incidents`를 별도 파일에
두고, 대응하는 `AREA_RECON` task가 완료된 checkpoint에서만 simulated `FIRE_DETECTED`
observation으로 공개한다. 이 fixture는 재현 가능한 world input이지 화재 탐지 모델이 아니다. 실제
영상 분석, 화재 탐지, 화재 안정성 판정은 구현하지 않는다. Task 완료는 위치 도달과 dwell
time으로만 판정한다.

**reference fixture 고정 형상** (P1~P4에서 쓰는 canonical full-response graph, §12 Family A에
대응). 이 값은 게이트 기준이며 LLM이 개입하기 전까지 사람이 손으로 고정한다:

| 항목 | 값 | 구성 |
|---|---|---|
| task | 8 | `AREA_RECON` 4 (ZONE_A~D) + incident workflow 2단계 × incident 2 = 4 |
| edge | 2 | incident 체인당 1 (§4 workflow) × incident 2 |
| 초기 READY | 6 | predecessor 없는 task = `AREA_RECON` 4 + `GROUND_INSPECTION` 2 |
| 초기 PENDING | 2 | `GROUND_SUPPRESSION` 2 |

READY/PENDING은 fixture YAML에 적지 않고 graph의 predecessor 상태에서 계산한다(§7, §9).

### 3.1 확장 reference scene (발표·시각화용, D-059)

`industrial_park`(4 zone)은 P1~P6.5 게이트와 P3/P4 골든 makespan(150.8 / 149.9, D-060+D-061)의 기준
scene으로 **동결**된다. 발표 슬라이드와 CBBA 할당 그림(§18.14)에서 이종 할당이 눈에 들어오도록,
같은 semantic world 규칙 위에서 zone·incident·route node 수만 늘린 **확장 reference scene**을
추가로 둘 수 있다. 확장 scene이 바꾸지 않는 것: task vocabulary(§4), fleet 구성과
capability(§5), workflow predecessor(§4), Validator 규칙과 `VALIDATOR_VERSION`, 이동비용 모델(§8),
priority 파생 규칙(§7, D-022).

확장 scene도 scene loader의 검증을 그대로 통과해야 한다: 모든 incident/zone response node가
route graph에 있고 모든 UGV 시작점에서 도달 가능(§8), 모든 task type의 eligible bidder ≥ 2(§5),
incident priority 1..10(§7). 확장 scene은 단계 게이트 대상이 아니고 어떤 평가 수치도 이 scene에서
만들지 않는다 — 발표 그림 생성(§18.14)과 발표용 라이브 데모에 쓴다. incident가 채워진 확장
scene은 `industrial_park`의 `reference_fixture.yaml`과 동일하게 손으로 고정한 full-response
fixture를 둔다. incident-empty 변형은 §23.3.1의 dynamic-world 방식대로 native UI에 선택 가능한
world profile로 등록해 첫 자연어부터 graph를 생성하며, D-058의 기본 profile(`patrol_park`)은
그대로 유지한다.

---

## 4. Task vocabulary

3종으로 고정한다(D-061에서 `THERMAL_RECON`·`SUPPRESSANT_DROP` 제거). 추가 제안은 하지 않는다.

| task_type | 의미 | 완료 조건 |
|---|---|---|
| `AREA_RECON` | UAV가 지정 구역을 정찰. incident 대응 chain 밖의 독립 task | 위치 도달 + dwell |
| `GROUND_INSPECTION` | UGV가 보고된 incident 접근 지점으로 이동해 지상 상태 점검. incident 대응 chain의 첫 단계 | 위치 도달 + dwell |
| `GROUND_SUPPRESSION` | GROUND_INSPECTION 완료 후 UGV가 incident 접근 지점에서 지상 진압을 수행하는 symbolic task. 완료는 물리적 소화 성공·소화 소요시간을 의미하지 않는다(D-016) | 위치 도달 + dwell |

**정적 incident workflow** (Phase 1, 조건부 규칙 — 아래 항상 강제되는 게 아님에 주의):

```
GROUND_INSPECTION → GROUND_SUPPRESSION
```

이 규칙은 "downstream task가 **존재하면** 같은 incident의 올바른 predecessor가 필요하다"는
조건부 규칙이지, "모든 incident가 반드시 2단계를 전부 생성해야 한다"는 강제가 아니다. 어떤
NL 명령이 GROUND_INSPECTION까지만 요청했다면 그 부분 graph도 구조적으로 유효하다. "이 부분
graph가 의도된 것인지 덜 만들어진 것인지"는 Validator의 역할이 아니라 §12 평가 하네스의
mission profile로 별도 판정한다(§9 참고).

`AREA_RECON`은 이 incident 대응 chain의 predecessor가 아니다 — 구역 정찰은 독립적으로
수행한다.

**dwell duration은 symbolic scenario parameter다**(D-016): 각 task_type마다 하나의 고정값을
`TASK_TABLE`에 두며, 물리적 소요시간(비행시간·소화시간 등)이라고 주장하지 않는다.
`GROUND_SUPPRESSION`의 duration도 마찬가지로 하나로 고정한다.

---

## 5. Agent 구성

총 5대. UAV 3대는 동일 기체, UGV 2대 (D-060).

| Agent | 대수 | capability |
|---|---|---|
| UAV (U1, U2, U3) | 3 | `AERIAL_RECON` |
| Ground UGV (G1, G2) | 2 | `GROUND_MOBILITY`, `SUPPRESSANT_APPLICATOR` |

Task별 eligible bidder: `AREA_RECON`=UAV 3, `GROUND_INSPECTION`=UGV 2,
`GROUND_SUPPRESSION`=UGV 2. 모든 task type에 eligible bidder ≥2 —
UGV 전용 task에서도 CBBA가 G1/G2 중 winner를 결정한다.

D-060 이전의 Scout(2) + Response(2) UAV 분리는 폐기했다(이유는 D-060). D-061 이후 UAV는
정찰 전담이고 진압은 UGV만 한다. **이종성은 UAV와 UGV 사이에 있다**: UAV는 공중 정찰(직선
이동), UGV는 지상 대응(route graph Dijkstra, §8) — 역할·이동 모델·capability가 모두 다르다. RQ2의 "이종 무인체계 할당"은
이 UAV/UGV 경계를 뜻한다.

UGV의 진압 장비는 사전 탑재된 것으로 가정한다. `WATER_LOAD`, suppressant 잔량·재보급,
same-agent resource coupling은 구현하지 않는다.

**모든 agent가 반드시 하나 이상의 task를 받아야 한다는 제약은 두지 않는다.** 대기하는 것도
비용상 합리적인 결과일 수 있다. 대신 다음을 측정한다: agent utilization, idle-agent count,
workload distribution, task별 eligible bidder 수. UAV가 계속 유휴 상태라면 이는 즉시 실패가
아니라 task 수·bid 가중치·world 크기가 의도한 이종 할당 실험을 만드는지 재검토할 근거로
취급한다.

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
- incident를 target으로 하는 task(`GROUND_INSPECTION`/
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
Validator는 이 두 출력을 구별하지 못한다: (a) 의도적으로 GROUND_INSPECTION까지만 생성한
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

이 방식에서 어떤 UGV가 초기에는 대기하다 `GROUND_INSPECTION`이 READY가 된 뒤 투입되는 것도
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
- Family B(aerial-focused): AREA_RECON만 요청 — UGV task가
  생성되면 안 됨
- Family C(selective incident response): 특정 incident만 전체 대응, 다른 incident는 정찰
  또는 GROUND_INSPECTION까지만

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
| P10 | 온라인 checkpoint 구간 2D playback (D-046~D-048) | 전후 frozen `ExecutionCheckpoint`만 입력 / 같은 snapshot·frame 수 → 같은 `PlaybackSpec` / UAV 직선·UGV shortest-path polyline을 simulation time으로 보간 / travel과 dwell 구분, 보간 pose를 물리 pose로 주장하지 않음 / checkpoint 모드는 가장 이른 completion마다 정지 원인과 계속 RUNNING인 agent 상태 표시, 재생 뒤 명령 허용 / 연속 모드는 같은 advance를 terminal까지 반복하되 구간 사이 입력 금지·실패 즉시 중단 / accepted online UPDATE 뒤 다음 구간이 새 assignment를 사용 / frame 생성·렌더가 allocate·advance·session mutation을 하지 않음 / matplotlib 실패 시 committed execution 보존 + 정적 map·표 fallback / AppTest + headless(Agg) / P3/P4/P9 수치·감사 event 불변 |
| P11 | native desktop operator console + 별도 2D simulator 창 (D-049) | `python3 -m desktop` 한 명령으로 두 top-level Qt 창 / 동일 `MissionSession` 공유 / live·cached·mock 출처 명시 / 자연어·후보 선택·checkpoint·연속 재생 연결 / simulator는 `MapRenderSpec`·`PlaybackSpec`만 그리며 연구 로직 미복제 / playback 중 입력 비활성, checkpoint에서 재활성 / simulator 창 종료·view 오류가 committed 실행을 rollback하지 않음 / Streamlit 보존 / `QT_QPA_PLATFORM=offscreen` 자동 테스트 / P3/P4/P9 수치·감사 JSON 불변 |
| P12.0 | RQ5·incident contingency 계약 | v1.47 / D-051 커밋 |
| P12.1 | strict `MissionDirective`/response policy + 한 턴 REPORT response slot | 같은 scene에서 response step만 다른 명령이 서로 다른 policy를 만들고 future incident workflow prefix가 정확히 달라짐 / policy 없는 단순 REPORT는 scene-only 유지 / resource constraint는 무시하지 않고 UNSUPPORTED |
| P12.2 | patrol scene + strict latent observation fixture | 초기 known incident 0 / latent data가 LLM context·초기 graph·scene hash에 없음 / 지정 `AREA_RECON` 완료 전 event 0, 완료 checkpoint에서 정확히 1회 / 잘못된 zone·trigger·type 거부 |
| P12.3 | sensor/operator 공통 atomic incident transaction | 같은 zone·response step이면 두 source가 같은 scene/graph diff를 생성 / planning·paused 모두 성공 후 한 번에 commit / Validator·reallocation 실패 시 scene/state/runtime identity와 hash·시각 불변 / sensor observation 별도 typed audit |
| P12.4 | Live counterfactual + 두 발표 scenario | 사전 고정 명령/annotation으로 initial graph·policy·report zone·response prefix exact scoring / 같은 scene의 다른 명령이 다른 graph/policy, 다른 zone이 다른 target을 생성 / scripted mock은 정확한 제시 문장 외 입력을 backend 소비 없이 거부 / sensor 시나리오와 operator-report 시나리오 모두 `COMPLETED`, capability/precedence violation 0, P9 selective release 원시값 감사 / 실제 model snapshot 기록 / 첫 Live 원시 결과와 개선 후 사전 고정 held-out 결과를 별도 artifact로 보존 |
| P12.5 | native UI 연결 | scenario는 명시적 선택·seed/fixture id 표시 / Live parsed directive·event source·patch·release/rebid 표시 / sensor observation과 operator report를 구분 / 다음 checkpoint 이후 변경 경로 재생 / cached를 live로 표시 금지 / P3/P4/P9 골든 불변 |
| P12.6 | autonomous safe-checkpoint playback + queued Live command (D-054) | initial `COMMITTED` 뒤 native UI가 별도 클릭 없이 checkpoint segment를 연속 재생 / playback 중 input 1건을 `QUEUED`로 표시하되 LLM·grounder는 호출하지 않음 / frozen segment 종료 뒤 같은 checkpoint의 sensor observation을 먼저 반영하고 queued command를 정확히 1회 기존 orchestrator로 처리 / accepted update 뒤 P9 selective release/rebid와 다음 segment 자동 진행 / clarification·UNSUPPORTED·REJECTED·TURN_ERROR에서는 자동 진행 정지 / queue overwrite 금지 / 일반 UAV·UGV platform 표현 허용, 특정 agent id·수량·배제는 계속 UNSUPPORTED / native 기본 scenario는 sensor detection / checkpoint 수동 버튼은 진단용으로 보존 / P3/P4/P9/P12 결과·감사 의미 불변 |
| P12.7 | completed patrol → follow-on incident response (D-055) | online `COMPLETED` terminal checkpoint가 있는 `EXECUTED`에서만 REPORT/canonical UPDATE 허용 / scene-only report는 terminal 유지, response patch commit은 previous `ExecutionAudit` 보존 + COMPLETED task/status/time 불변 + 새 task만 READY/ASSIGNED + `EXECUTION_PAUSED` 재개 / 다음 segment 자동 재생 후 다시 `COMPLETED`·위반 0 / one-shot terminal·EXECUTION_FAILED·NEW_MISSION은 계속 거부 / TurnAudit이 follow-on patch와 online assignment를 기록하고 이전 EXECUTION→TURN→새 EXECUTION event 순서 보존 / 단순 recon 명령은 future incident policy null / `p12-v4` / mid-run selective reallocation과 follow-on episode 결과를 혼동하지 않음 |
| P13.0 | RQ6 동적 임무·자원 제약·연속 runtime 계약 | v1.52 / D-056 커밋 |
| P13.1 | strict resource request + deterministic active-team selection | `NEW_MISSION`이 UAV/UGV exact·min·max와 required/excluded agent slot을 strict wire로 보존 / 미지 id·중복·교집합·범위 모순 거부 / feasible team 전수 탐색 뒤 기존 `allocate` 결과로 결정론적 선택 / 제약 없는 입력은 기존 full-fleet 결과와 정확히 동일 / constraint를 조용히 무시하거나 LLM assignment로 대체하지 않음 |
| P13.2 | 후속 resource update + online safe-boundary 적용 | `UPDATE_RESOURCES`와 incident report에 동반된 resource request를 지원 / RUNNING·COMPLETED commitment 불변 / 새로 배제된 RUNNING agent는 현재 task 완료 뒤 future work에서만 제외 / 실패 시 policy·state·runtime identity와 hash 불변 / resource request·resolved team·assignment 변화·deferred exclusion 감사 |
| P13.3 | scenario-free Live operator session | Live 기본 scene은 world만 로드하고 reference graph·latent incident fixture·scripted response fallback 없음 / 서로 다른 사전 고정 자연어가 서로 다른 graph·team·assignment를 생성 / mock은 별도 TEST/DEMO 배너와 exact utterance만 허용 / Live 실패를 mock 결과로 대체하지 않음 |
| P13.4 | continuous wall-clock 2D runtime + asynchronous command queue | 고정 tick에서 simulation time·pose가 연속 증가 / UI 버튼 없이 자동 진행 / 재생 중 Live 명령을 LLM이 해석해 pending transaction으로 보존 / 현재 frozen commitment는 다음 task-completion safe boundary까지 유지 / boundary에서 Validator→resource feasibility→selective release/rebid를 한 번만 atomic commit / 입력·tick timing 변화가 같은 boundary state에서 같은 결과 / pause·resume·failure 감사 / P3/P4/P9 골든 불변 |
| P13.5 | Live counterfactual evaluation | 사전 커밋 held-out 명령에서 graph·resource request·resolved team·assignment exact score / invalid constraint clarification·rejection 분모 보고 / 초기 순찰→simulated detection→response와 순찰 중 operator report→재할당 두 시나리오 완주·위반 0 / 모델 snapshot·raw/final wire·hash·timing 감사 |
| P14.0 | ROS2/Gazebo adapter 계약 | simulator boundary·topic/service schema·clock ownership·failure semantics·재현 가능한 world/launch 고정; P13 알고리즘과 adapter 분리 |
| P14.1 | multi-agent Gazebo execution adapter | P13 committed assignment를 UAV/UGV controller에 발행하고 telemetry를 UI에 반영 / LLM은 setpoint를 만들지 않음 / adapter failure가 Validator·graph audit를 훼손하지 않음 / 대표 두 시나리오 재현 영상과 raw ROS audit |

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

1. P14 Gazebo 통합
2. P13.2 후속 자원 정책 중 min/max 갱신
3. exact solver 비교
4. 반복 LLM 호출

**절대 자르지 않음**: canonical reference graph, deterministic whole-graph Validator,
heterogeneous capability allocation, platform-aware travel cost, 2D end-to-end 실행, 최소
9개 LLM 평가, raw output과 validated output 비교.

---

## 17. 명시적 범위 제외

실제 RGB/thermal perception, 학습 기반 자동 화재 탐지, 물리적 화재 안정성 판정, `WATER_LOAD`,
suppressant 잔량과 재보급, same-agent resource coupling, obstacle removal, relay deployment,
target tracking, `FIRE_DETECTED` 고정 contingency 밖의 일반 조건부 task graph, SLAM, 동적 장애물 회피, 일반 road planner, LLM 직접
task→agent 할당(P13의 agent class·수량·포함·배제 constraint 추출은 허용), 새로운 CBBA 알고리즘 제안, P0~P6.5 완료 전 RQ3 구현(P7 Gazebo는 RQ3의
선행조건이 아님 — §16 cut-order·§15·§1 참고, D-027), MP4MR A~G 체계 복제, 모든
agent가 최소 1개 task를 받아야 한다는 제약, bundle 길이 ≥2를 Phase 1 invariant나 완료 게이트로
쓰는 것(P8에서는 실험 precondition으로 재검토 가능 — §15 P8), 임의 wall-clock 시점의 강제
중단, RUNNING task abort·migration, 실행 후 terminal graph 수정, P12의 strict simulated
`FIRE_DETECTED` fixture 밖의 자동 perception event,
P9 정책의 전역 최소성·최적성 주장. P13도 RUNNING task의 즉시 abort·migration을 도입하지 않으며,
wall-clock 입력은 다음 task-completion safe boundary에서만 실행 상태에 반영한다.

---

## 18. Operator–LLM Planning Session (P8, D-027)

### 18.1 범위

실행 개시 전의 다중 턴 임무 계획 세션. 대화·graph 수정·incident 등록은 전부 실행 전.
"실행" 버튼(결정론적 UI 동작, LLM intent 아님) 이후 첫 버전에서: graph 수정 불가, incident
추가 불가, `NEW_MISSION`/`REPORT_INCIDENT`/`UPDATE_MISSION` 전부 `UNSUPPORTED`, 저장된
`ExecutionResult` 조회(`QUERY_STATUS`)만 가능. 실패 시 동일 graph 재시도만 허용하고 graph
변경은 금지한다.

후속 P12.7은 이 최초 규칙을 한 경우에만 좁게 supersede한다(D-055). online 실행이
`Termination.COMPLETED`로 끝났고 terminal `runtime` checkpoint가 보존된 `EXECUTED` session은
새 `REPORT_INCIDENT`를 기록하고, 그 incident의 canonical workflow를 REPORT 한 턴 또는 이어지는
`UPDATE_MISSION`으로 추가할 수 있다. 기존 COMPLETED task를 다시 열거나 수정하지 않고 새 task만
terminal checkpoint에 붙인다. response task가 실제로 commit되면 현재 `execution` field를 비우고
`EXECUTION_PAUSED`로 전환하지만 과거 `ExecutionAudit`은 event stream에 남는다. 이것은 임무 진행
중 release/rebid와 구분되는 **follow-on execution episode**다. one-shot 완료(runtime 없음),
`EXECUTION_FAILED`, `NEW_MISSION`에는 이 예외를 적용하지 않는다.

P8 결과만으로는 "임무 실행 중 자연어 업데이트"를 주장하지 않는다. 이는 P9 §19의 별도
checkpoint/resume 게이트를 모두 통과한 경우에만 선택 확장 결과로 주장한다. perception·자동
화재 탐지 없음(§3 재확인) — 신규 incident는 운용자의 명시적 보고로만 시스템에 진입한다.
고정 5종 task 어휘에서는 어떤 유효 patch도 기존 task의 predecessor 집합을 바꾸지 못하므로
(D-006), 정상 대화에서 기존 assignment의 release·재할당은 발생하지 않는다.

### 18.2 지원 대화 행위 (5종 고정)

`NEW_MISSION` / `REPORT_INCIDENT` / `UPDATE_MISSION` / `QUERY_STATUS` / `UNSUPPORTED`.
미지원(→ `UNSUPPORTED`, 고정 템플릿 응답): 자유 채팅, task/incident 취소·삭제, 재우선순위,
agent 지정 할당, 비-canonical graph 편집, incident 위치 변경, 임의 mid/post-execution patch.
단 §19의 paused canonical patch와 §18.1/D-055의 completed-online follow-on incident workflow는
명시된 예외다.

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
live/cached backend에서 첫 wire 응답이 이 strict 변환의 `ValidationError`를 내면, 같은 발화와
같은 deterministic context에 그 오류를 첨부해 **schema correction을 정확히 한 번** 요청한다.
repair도 동일한 `IntentWireEnvelope`와 cross-field 검증을 통과해야 하며, 코드는 무관 slot을
삭제·세탁하지 않는다. 두 번째 schema 오류, network/auth/cache miss 등 다른 예외는 재시도하지
않고 기존 `TURN_ERROR` 경계로 보낸다. mock은 고정 script의 불일치를 숨기지 않도록 이 repair를
사용하지 않는다. repair prompt/cache 의미가 바뀌면 prompt schema version을 함께 올린다.
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
`intent_repair_attempted`, `intent_repair_recovered`,
`timing`{`total_s`, `llm_total_s`, `deterministic_s`, `llm_calls`: `[[schema_name, seconds], …]`}
| null (D-071) — 그 턴의 wall-clock 분해. `llm_calls`는 `backend.complete()` 호출을 발생 순서로
schema 이름(`IntentWireEnvelope`·`Step1Output`·`Step2Output`·`RepairOutput`)과 초 단위로
기록한다. `deterministic_s = total_s − llm_total_s`(grounder·Validator·compiler·CBBA 합).
계측일 뿐이며 어떤 판정·결과도 바꾸지 않는다. `mock`에서는 LLM 시간이 ~0이므로 `live`에서만
의미가 있다,
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
`intent_repair_attempted/recovered`는 D-052의 intent-wire correction만 가리키며,
`generation.repaired`(task graph repair)와 다른 단계다. attempted=false이면 recovered도 반드시
false다. 첫 응답 실패 뒤 두 번째 응답도 실패하면 attempted=true/recovered=false로 기록한다.

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
`normalize_zone_ref()`(끝의 한국어 위치 조사 `에서`/`에` 하나를 먼저 제거하고, 이어서
`구역`/`지역` 접미사 하나를 제거한 뒤 `normalize_identifier`). 조사는 zone reference에만
적용하며 incident id나 일반 identifier에는 적용하지 않는다. scene
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

**P8.5 범위**: TaskGraph DAG + 정적 2D 임무 지도. **P8.5 자체에서는 애니메이션이 범위
밖이다** — timestamp로
재구성은 가능하나 agent별 보간, dwell/travel 분리, online update 전후 assignment 연결,
Streamlit rerun 상태 관리, 발표 환경 성능이 모두 따라붙는다. 정적 그림에 순서와 상태를
표시하는 것으로 충분하다.
후속 P10에서 이 제외를 §20의 좁은 checkpoint playback에 한해 해제한다(D-046). P8.5의 정적
지도·결정론·degrade 게이트는 그대로 유지된다.

**순수 view 경계.** 렌더러는 `demo/visualization.py`에 두고 matplotlib `Figure`만 반환한다.
`core/`·`allocation/`·`execution/`·`interaction/`의 **할당·실행 의미는 바꾸지 않으며**, 연구
로직을 복제하지 않고 이미 계산된 값(`MissionState`, `AllocationResult`, `ExecutionResult`,
executor checkpoint)만 그린다. **예외 하나(D-044)**: `RouteGraph`에 최단경로의 **경유 node를
돌려주는 read-only 조회 API**를 추가하는 것은 허용한다 — 현재 `shortest_path_distance()`는
거리만 주므로, 이것 없이 UGV polyline을 그리려면 view가 Dijkstra를 재구현해야 하고 그것이야말로
"연구 로직 비복제" 위반이다. 요구사항: 기존 `shortest_path_distance()`와 **같은 tie-break**,
반환 경로의 누적 weight가 그 거리와 **모든 node 쌍에서 일치**(테스트), 입력 graph 불변, 동일
입력 동일 경로, 도달 불가 시 기존 API와 일관된 반환. **P3/P4 골든 makespan(D-060+D-061: 150.8 / 149.9)은
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
chain을 추가하는 online update — 에서는 즉시 `READY`가 되는 것이 `GROUND_INSPECTION` 하나뿐이고
그 bidder union이 UGV 전체다. 그러면 모든 UGV task가 영향, 모든 UAV task가 비영향이 되고
bundle은 한 agent(UAV이거나 UGV)의 것이므로 그 경로에서는 섞인 bundle이 나오지 않았다.
따라서 이 실행들에서는 항상 `released == directly_affected`이고

    suffix_extra_release_count = |released − directly_affected| = 0

**단정하지 않는 것(D-042)**: 이것을 "도메인 전체에서 섞인 bundle이 불가능하다"로 일반화하지
않는다. `build_chain_patch`는 신규 incident의 전체 chain뿐 아니라 **기존 incident의 부분
workflow 연장**도 만든다. 예를 들어 `GROUND_INSPECTION`이 이미 COMPLETED인 incident를
`GROUND_SUPPRESSION`까지 늘려도 신규 READY task의 bidder는 UGV 전체이고 `AREA_RECON`은 UAV가
bidder라 비영향이므로, 한 agent의 bundle에 영향 task와 비영향 task가 섞이려면 그런 배치가
현재 CBBA·priority 아래에서 실제로 도달 가능해야 하는데 **검증하지 않았다**. (D-060 이전
서술은 Scout/Response 분할을 전제했다 — 그 예시는 현 fleet에 성립하지 않으며, 정식 재서술은
후속 검토로 남긴다.)

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

---

## 20. Checkpoint-segment 2D playback (P10, D-046)

### 20.1 범위와 진실 원천

P10은 P9 온라인 실행의 **연속한 두 `ExecutionCheckpoint` 사이**를 눈으로 재생하는 presentation
layer다. 임의 wall-clock 시각에 simulator thread를 정지시키는 기능이 아니고, 기존
`advance_online_session()`의 task-completion event 경계를 바꾸지 않는다. 버튼 한 번의 의미는
계속 `다음 completion event까지 원자적으로 진행`이다.

실행 상태와 감사 event가 먼저 정상적으로 commit된 뒤, UI가 action 직전 checkpoint와 commit된
직후 checkpoint를 frozen 입력으로 `PlaybackSpec`에 변환해 재생한다. playback은 결과를
**설명하는 view**이며 실행을 구동하는 두 번째 clock이 아니다. wall-clock 재생 시간·배속·frame
rate는 연구 지표나 감사 event가 아니고 `turn_count`도 소비하지 않는다. one-shot 실행은 기존
정적 completed-execution 지도를 유지한다.

### 20.2 위치 보간 의미

- UAV travel: task의 기록된 `task_departure`부터 `task_start`까지 출발 위치와 target 사이를
  simulation-time 선형 보간한다.
- UGV travel: 같은 구간에 `RouteGraph.shortest_path_nodes()`가 준 polyline을 lane weight 누적
  거리로 보간한다. view가 별도 경로 탐색을 재구현하지 않도록 lane weight의 read-only 조회 API를
  허용한다. 경로·누적 weight는 allocator/executor가 사용한 shortest-path 거리와 일치해야 한다.
- dwell: `task_start`부터 해당 agent의 `finish_at`까지 target에 정지해 표시한다.
- 해당 구간에 travel/dwell이 없는 agent는 마지막 확정 위치에 정지한다. 동시에 계속 RUNNING인
  agent도 자신의 기록된 departure/start/finish time에 따라 같은 규칙으로 표시한다.

이는 기존 discrete-event schedule의 **kinematic interpolation**이다. 실제 robot telemetry,
continuous collision avoidance, acceleration·turning dynamics, 물리 pose 정확성을 주장하지 않는다.
frame label에 simulation time과 agent별 `TRAVEL`/`DWELL`/`IDLE` 상태를 표시해 이 경계를 숨기지
않는다.

### 20.3 결정론·상태 불변

`PlaybackSpec`과 `AnimationFrameSpec`은 matplotlib을 import하지 않는 immutable 구조다. 같은
scene, before/after checkpoint, frame 수에는 같은 frame time·agent position·activity·task id가
나와야 한다. 결정론 게이트는 Figure/GIF 바이트가 아니라 이 spec을 비교한다(§18.14와 동일 원칙).

spec 생성과 frame 렌더는 `allocate()`, CBBA epoch, `advance_to_next_completion()`,
`advance_online_session()`을 호출하지 않고 session·scene·checkpoint를 바꾸지 않는다. 전후
checkpoint의 simulation time, graph/state, assignment, timing과 scene hash가 frame 생성 전후
동일해야 한다. 마지막 frame의 time과 agent activity/task는 commit된 after checkpoint와
일치한다. 그 시각에도 RUNNING인 agent의 보간 위치는 P8.5 정적 Runtime 지도의 "마지막 확정
위치"와 다를 수 있으며, 이것이 정상이다(D-047). 완료된 agent는 확정된 task target에 놓인다.

### 20.4 UI·실패 경계

**Checkpoint 재생** 버튼은 action 전 snapshot을 잡고 기존 `advance_online_session()`을 한
번만 호출한 뒤, 성공적으로 시간이 전진한 경우에만 그 구간을 재생한다. 전역에서 가장 이른 task
completion event가 pause 원인이므로, 그 시각에 다른 agent는 목적지로 TRAVEL 중이거나 target에서
DWELL 중일 수 있다. 이는 임무 종료가 아니다. UI는 버튼을 `다음 checkpoint까지 재생`으로
표현하고, 완료되어 pause를 만든 task와 계속 RUNNING인 각 agent의 `TRAVEL 중 일시정지` /
`DWELL 중 일시정지`를 표시한다. 재생이 끝난 뒤 이미 commit된 checkpoint에서 후속 자연어
입력을 받는다. 따라서 운용자는 **재생 → checkpoint 입력 → selective release/rebid → 다음 구간
재생** 순서로 계획·할당 변화를 확인한다.

**끝까지 연속 재생**은 별도 명시적 버튼이다. 새 executor나 one-shot 우회가 아니라 같은
`advance_online_session()`을 checkpoint별로 반복하고 각 구간의 `PlaybackSpec`을 순서대로
재생해 `EXECUTED` 또는 `EXECUTION_FAILED`까지 간다. 구간 사이에 chat input·실행 버튼을
렌더하지 않으므로 중간 명령은 받을 수 없다. 예외나 `DEADLOCK`/`STEP_LIMIT`이면 자동 retry하지
않고 즉시 연속 모드를 끝낸다. 모든 `CheckpointAudit`과 마지막 `ExecutionAudit`은 기존 순서대로
남는다. RUNNING task abort·migration은 두 모드 모두 여전히 지원하지 않는다.

Streamlit의 동기 playback 중에는 chat input·실행 버튼을 처리하지 않는다. checkpoint 모드와
연속 모드는 같은 session에서 임의로 전환할 수 있으나, 이미 terminal인 실행은 다시 시작하지
않는다.

UI는 playback on/off, 1x/2x/5x 배속을 제공한다. off는 연구 실행을 건너뛰는 것이 아니라 화면
재생만 생략한다. matplotlib import/렌더 실패나 frame 생성 실패는 이미 commit된 runtime·state·
감사 event를 되돌리지 않고 앱을 죽이지 않는다. 오류를 알리고 §18.14 정적 Runtime 지도와 표로
degrade한다. 테스트는 sleep을 비활성화한 상태에서 AppTest로 버튼→frame→checkpoint 입력 가능
순서, 연속 모드의 terminal 도달·중간 control 미렌더·감사 순서를 검사한다.

---

## 21. Native desktop operator console (P11, D-049)

### 21.1 목적과 범위

P11은 P8~P10의 결과를 브라우저의 긴 분석 페이지가 아니라 발표용 native desktop 화면으로
보여주는 **presentation client**다. 새 연구 알고리즘·실험·지표가 아니며 Streamlit UI를
대체하거나 삭제하지 않는다. 실행 명령은 `python3 -m desktop`이고, 한 Qt application 안에
서로 독립적으로 이동·크기 조절 가능한 두 top-level window를 연다.

- **Operator Console**: 모드(live/cached/mock), 대화, clarification 후보, phase·simulation
  time, 핵심 Validator/patch/assignment 변화, checkpoint/연속 재생 제어.
- **Mission Simulator**: scene·route lane·incident·task·agent와 simulation clock을 큰
  전용 viewport에 표시하고 P10 frame을 순서대로 재생한다.

두 창은 같은 `MissionSession` 객체를 공유한다. 별도 simulator process·socket·두 번째 session을
만들지 않는다. 창 사이 전달값은 이미 계산된 session event와 immutable render/playback spec뿐이다.

### 21.2 진실 원천과 상태 전이

desktop controller는 기존 공개 경계만 호출한다: 자연어는 `handle_turn`, 후보는
`select_clarification_candidate`/`cancel_clarification`, 실행은 `advance_online_session`,
감사는 `write_session_audit`. live/cached/mock backend도 Streamlit과 동일한 구현을 사용한다.
desktop이 `allocate`, CBBA epoch, `SimExecutor._*`를 직접 호출하거나 task/agent 상태를 고치지
않는다. 단 첫 online action 전 P10의 frozen `before` snapshot을 얻기 위한
`SimExecutor(session.state, scene).checkpoint()`는 기존 UI와 동일하게 허용한다.

지도는 P8.5 `MapRenderSpec`, 움직임은 P10 `PlaybackSpec`/`AnimationFrameSpec`만 그린다.
Qt painter의 좌표 변환·색·label은 view 의미이며 simulator time이나 물리 pose의 새 진실 원천이
아니다. P10의 kinematic interpolation 한계와 checkpoint 경계는 그대로다.

### 21.3 입력·재생 lifecycle

- planning/checkpoint 상태에서 자연어 입력과 후보 선택을 허용한다.
- 한 segment를 재생하는 동안 입력·실행 control을 비활성화한다. 마지막 frame 뒤 checkpoint
  상태를 표시하고 다시 활성화한다.
- **다음 checkpoint**는 online action을 정확히 한 번 호출한다.
- **끝까지 연속 재생**은 segment 종료 callback에서 같은 online action을 terminal까지 반복한다.
  구간 사이 입력을 허용하지 않고, 예외·DEADLOCK·STEP_LIMIT에서 자동 retry하지 않는다.
- checkpoint에서 accepted online UPDATE가 assignment를 바꾸면 다음 `PlaybackSpec`이 새 runtime
  assignment를 사용한다. RUNNING task abort·migration과 임의 wall-clock interrupt는 여전히
  범위 밖이다.

### 21.4 실패·의존성·검증

Qt binding은 공식 Qt for Python 바인딩인 `PySide6`로 고정하고 선택 dependency `desktop`
extra로 선언한다. desktop module import는 Qt가 없는
환경에서도 연구 core와 기존 테스트 import를 깨뜨리지 않아야 하며, 실행 시 설치 안내와 함께
명시적으로 실패한다. simulator 창을 닫아도 session 실행을 취소하거나 rollback하지 않고 다시
열 수 있다. render 실패는 메시지를 표시하고 대화·감사 경로를 보존한다.

자동 검증은 `QT_QPA_PLATFORM=offscreen`에서 한다: 두 창 생성, 동일 session identity, mock
mission 생성, structured clarification, checkpoint frame 진행, playback 중 control 비활성,
checkpoint 후 재활성, 연속 모드 terminal 도달, 온라인 UPDATE 뒤 다음 frame assignment 반영,
오류 시 자동 retry 없음, audit event 순서와 파일 경로 보존. P3/P4/P9 골든과
`VALIDATOR_VERSION`/`ONLINE_POLICY_VERSION`은 불변이어야 한다.

---

## 22. LLM-driven incident contingency (P12, D-051/D-052)

### 22.1 범위와 LLM 경계

P12는 정적 graph만 만들던 `NEW_MISSION`을 **초기 graph + 좁은 incident response policy**로
확장한다. interaction intent의 `incident_response_up_to`는 없거나 §4 workflow step 하나다.
예: "전체 구역을 정찰하고 화재를 발견하면 지상 진압까지 대응"은 초기 `AREA_RECON` graph와
`GROUND_SUPPRESSION` policy를 만든다. 아직 존재하지 않는 incident id나 task를 미리 만들지
않는다. "정찰만"은 policy가 `None`이어야 한다.

`REPORT_INCIDENT`는 기존 `zone_ref`와 선택 `response_up_to`를 가진다. 명시 step이 있으면 그것을
사용하고, 없으면 활성 session policy를 사용한다. 둘 다 없으면 기존처럼 scene-only report로
commit하며 대응 task를 추측해 추가하지 않는다. 특정 agent·대수·제외 agent 등 resource
constraint는 P12 범위 밖이고 `UNSUPPORTED`로 fail closed한다.

### 22.2 observation과 latent-world 경계

`LatentIncidentFixture`는 id, 공개할 zone, trigger task id를 strict하게 저장한다. fixture는
scene과 별도이며 LLM prompt/context, 초기 graph, `scene_hash`에 포함하지 않는다. trigger는 해당
zone의 `AREA_RECON` task여야 하고 checkpoint의 `completed_now`에 처음 나타난 경우에만
`FireDetectedObservation`을 정확히 한 번 낸다. 재개·rerun·cached 재생은 같은 observation을
중복 발행하지 않는다.

observation은 `source=SENSOR_SIMULATED`, detecting agent id, zone, simulation time, fixture id를
typed audit에 남긴다. 실제 센서 confidence나 영상 결과를 발명하지 않는다. task가 완료됐다는
사실과 fixture 조건이 맞았다는 것만 뜻한다.

**다중 latent fire field (D-062).** `LatentFireField`는 `field_id`, 정수 `seed`, `count`,
선택적 `candidate_zones`를 strict하게 저장한다. `candidate_zones`가 없으면 scene의 모든 zone이
후보다. `random.Random(seed)`가 정렬된 후보에서 `count`개를 뽑아(sample) 각 zone의 `AREA_RECON`을
trigger로 하는 `LatentIncidentFixture` 튜플을 만든다. 같은 seed·scene·spec은 항상 같은 zone
집합을 준다. 지형·fleet·route·zone 위치는 전부 고정이고 seed가 정하는 것은 화재가 있는 zone뿐이며
화재 위치는 그 zone의 기존 response point다. field는 단일 fixture와 동일하게 scene·LLM prompt·
초기 graph·`scene_hash`에 포함되지 않는다. 각 fixture는 자기 trigger가 checkpoint
`completed_now`에 처음 나타난 경우에만 `FireDetectedObservation`을 한 번 낸다. 한 checkpoint에서
여러 trigger가 완료되면 zone id 오름차순으로 발행한다. `count`가 후보 zone 수보다 크거나 1 미만이면
로드 시 거부한다. `seed`·`field_id`·뽑힌 zone 수는 UI에 표시하되(§22.5) 어느 zone인지는 공개
전까지 표시하지 않는다.

### 22.3 공통 atomic incident transaction

sensor observation과 operator report는 zone이 결정된 뒤 같은 transaction을 호출한다:

1. 원본을 바꾸지 않고 `register_incident()`로 candidate scene과 결정론적 id를 만든다.
2. response step이 있으면 candidate incident에 `build_chain_patch()`를 만든다.
3. planning은 candidate state에 `apply_patch → allocate`, paused runtime은 checkpoint clone에
   `apply_online_patch(SELECTIVE)`를 수행한다.
4. scene/state/plan 또는 scene/runtime/state를 모든 계산 성공 뒤 한 번에 publish한다.

실패 시 원 scene·state·plan·runtime identity, simulation time, completed/RUNNING commitment와
hash를 보존한다. sensor/operator source에 따라 알고리즘 경로를 복제하지 않는다. 성공 event는
incident id, source, policy origin(`EXPLICIT|SESSION_POLICY|NONE`), patch/hash, before/after
assignment, released task를 감사한다.

### 22.4 하드코딩 방지와 평가

P12의 결정론적 scene/compiler/Validator는 안전 경계이지 고정 LLM 응답이 아니다. Live 경로에는
reference fixture fallback이 없다. 다음 counterfactual을 사전 annotation으로 고정한다.

- 같은 patrol scene: 정찰만 / 감지 시 DROP / INSPECTION / SUPPRESSION 명령은
  서로 다른 policy를 내며, 동일 sensor observation 뒤 정확히 0/1/2/3 workflow task를 만든다.
- 같은 command: Warehouse와 Tank Farm operator report는 서로 다른 zone으로 grounding되고
  서로 다른 incident target·경로를 만든다.
- 같은 의미의 허용된 한국어/영어 paraphrase는 같은 directive가 되어야 하고, 미지·모호 zone은
  추측하지 않고 clarification한다.

mock은 UI wiring을 위한 scripted mode일 뿐이다. 현재 기대 문장과 다른 입력을 같은 응답으로
처리하지 않고, backend item을 소비하지 않은 채 명시적으로 거부한다. 발표의 핵심 결과는 live
또는 그 live 호출의 exact cached replay로 보여주고 provenance를 항상 표시한다.

첫 P12 Live counterfactual은 engineering feedback을 보기 전에 고정한 annotation과 함께 원시
artifact로 보존한다. 그 결과를 본 뒤 추가한 prompt repair·정규화 개선은 같은 명령에 다시
실행한 수치를 새 headline으로 삼지 않는다. 개선 후 일반화 평가는 결과를 보기 전에 별도
held-out paraphrase annotation을 커밋하고 별도 artifact 이름으로 실행한다. 첫 결과는 삭제하거나
덮어쓰지 않으며, regression 재실행과 held-out 결과를 보고서에서 명확히 구분한다.

### 22.5 실행·시각화 의미

P12도 P9/P10의 task-completion checkpoint만 사용한다. sensor event는 trigger recon completion
직후, operator report는 pause에서 처리한다. 임의 wall-clock interrupt·RUNNING task migration은
추가하지 않는다. UI는 initial directive, 활성 response policy, observation source, 신규 incident,
patch task, selectively released task와 다음 segment의 assignment/path를 구분해 표시한다.

두 발표 scenario 모두 최종 `COMPLETED`, capability/precedence violation 0이어야 한다. 이 결과는
simulated observation에 대한 온라인 mission adaptation이며 실제 perception 또는 물리적 화재
진압 성공 주장이 아니다. 기존 reference scene과 P3/P4/P9 fixture는 변경하지 않고 골든값을
그대로 보존한다.

### 22.6 autonomous safe-checkpoint presentation (D-054)

native UI의 기본 발표 lifecycle은 최초 임무가 `COMMITTED`되면 별도 실행 버튼 없이 P10 frozen
checkpoint segment를 연속 재생하는 것이다. 이는 executor를 wall-clock으로 구동하는 새 clock이
아니며, 각 segment의 실행 상태와 감사 event는 §20.1대로 먼저 원자적으로 commit된다. 기존
`다음 checkpoint` 버튼은 회귀·진단을 위해 남기지만 발표의 정상 경로는 자동 진행이다.

운용자는 segment가 화면에서 재생되는 동안 자연어 명령 **한 건**을 입력할 수 있다. UI는 이를
`QUEUED — 다음 safe checkpoint에서 적용`으로 명시하고, 현재 frozen playback이 끝나기 전에는
LLM·grounder·Validator·CBBA를 호출하지 않는다. 두 번째 입력으로 첫 입력을 조용히 덮어쓰지
않는다. segment 종료 callback에서 이미 commit된 같은 task-completion checkpoint의 P12
simulated sensor observation을 먼저 확정한 뒤 queued utterance를 기존 `handle_turn()` 경로로
정확히 한 번 처리한다. 따라서 명령은 화면상 임의 시각에 RUNNING task를 중단시키는 것이 아니고,
다음 안전 경계에서 적용되는 운용자 입력이다.

queued turn이 `COMMITTED`·`NO_CHANGE`·`ANSWERED`이고 session이 계속 실행 가능하면 다음 segment를
자동 재생한다. `CLARIFICATION`·`UNSUPPORTED`·`REJECTED`·`TURN_ERROR` 또는 pending clarification이면
자동 진행을 멈추고 입력/후보 선택을 기다린다. accepted online graph 변경은 §19의 atomic patch와
selective release/rebid를 그대로 사용하며 다음 segment의 assignment/path에서 처음 보인다. queue는
presentation state이고 처리 전에는 `TurnAudit`이 아니며, 처리된 시점에만 실제 턴 감사가 생긴다.

intent 경계에서 `UAV로 정찰`, `UGV로 점검`, `지상 로봇으로 진압` 같은 **일반 platform class**
표현은 이미 고정된 task capability/workflow를 설명하는 말이므로 허용한다. 이는 agent를 선택하거나
수를 제한하는 slot이 아니며 allocator가 기존 fleet 전체에서 결정한다. `G1만`, `UAV 한 대만`,
`R2 제외`처럼 특정 agent id·수량·배제를 요구하는 표현은 여전히 지원 범위 밖이고 요청 전체를
`UNSUPPORTED`로 fail closed한다. native 기본 scenario는 두 발표 시나리오 중 sensor detection으로
두어 처음 실행한 자유 문장이 legacy reference fixture처럼 보이지 않게 한다.

### 22.7 completed patrol의 follow-on response episode (D-055)

`AREA_RECON` 4개처럼 유한한 초기 graph는 마지막 task가 끝나면 정직하게 `EXECUTED`가 된다.
반복 순찰 task나 실제 지속 감시를 구현하지 않았으므로 화면이 계속 움직이는 것처럼 가장하지
않는다. 대신 online `COMPLETED` terminal checkpoint를 보존한 session은 이후 도착한 새 incident
report를 받을 수 있다. response step이 없는 report는 scene/referent만 추가하고 terminal을
유지하며, 같은 턴의 `response_up_to` 또는 후속 canonical `UPDATE_MISSION`이 workflow를 추가하면
그 terminal checkpoint를 복제해 `apply_online_patch`와 CBBA epoch를 수행한 뒤
`EXECUTION_PAUSED`로 전환한다.

이 전환은 기존 completed prefix, simulation time, agent의 마지막 확정 위치, 기존 assignment
history를 되돌리지 않는다. 직전 `ExecutionAudit`도 삭제하지 않고 event stream에
`... EXECUTION(COMPLETED) → TURN(COMMITTED) → ... → EXECUTION(COMPLETED)` 순서로 남긴다.
native auto-run은 follow-on commit도 자동 재생한다. 실행 중 queue가 만든 patch는 P9 selective
reallocation 사례이고, terminal 뒤 patch는 follow-on episode이므로 발표·평가에서 둘을 같은
수치로 부르지 않는다.

intent classifier는 `incident_response_up_to`를 **미래 화재가 감지·보고될 때**라는 조건이
명시된 `NEW_MISSION`에서만 채워야 한다. `전체 구역 항공 정찰만 해줘`의 `정찰만`은 초기 graph
범위를 설명할 뿐 future incident policy가 아니므로 null이다. 이 prompt 의미 변경은
`PROMPT_SCHEMA_VERSION = p12-v4`로 격리한다. LLM이 graph·policy 구조를 제안한다는 역할은
유지하며, allocator·priority·좌표·capability는 계속 결정론적이다.

### 22.7.1 상시 운용 콘솔 — terminal 뒤 새 mission episode (D-068)

재난 대응은 상황이 계속 갱신되므로 session에 "임무 완료"라는 종착점이 없다. terminal
checkpoint를 보존한 session은 `REPORT_INCIDENT`(§22.7)뿐 아니라 `NEW_MISSION`과
`UPDATE_RESOURCES`도 받는다. terminal 뒤 `NEW_MISSION`("전체 재정찰 해줘")은 기존 활성 임무
clarification 대신 **새 mission episode**를 연다:

- 새 자연어 → 기존 `generate_mission` 경로 → 검증된 **새 task graph**(완료된 graph에 덧붙이지
  않는다).
- UAV 시작 위치는 직전 terminal checkpoint의 마지막 확정 위치를 이어받는다. UGV는 scene 기지
  node(§5)에서 다시 시작한다(출동 후 기지 대기 가정) — `start_ref`이 UGV를 scene node로 잡는
  기존 규칙과 일치한다.
- 새 `MissionState`+`allocate` → `PLANNING`에서 commit → native auto-run이 재생한다.
- 직전 `ExecutionAudit`는 event stream에 남고 episode 순서는
  `... EXECUTION(COMPLETED) → TURN(COMMITTED NEW_MISSION) → EXECUTION(COMPLETED)`.
- scene에 쌓인 기존 incident는 그대로 있고, 새 episode graph는 자연어가 지시한 범위만 만든다
  (`전체 재정찰만` → `AREA_RECON`만). 기존 화재를 자동으로 다시 대응하지 않는다.

**정직한 한계** 반복 순찰 task나 지속 감시는 여전히 구현하지 않는다(§22.7). agent는 episode
사이에 마지막 위치에서 idle이며 화면이 계속 움직이는 척하지 않는다. 콘솔이 다음 명령을 항상
받을 수 있을 뿐이다. phase는 `EXECUTED`로 유지하되 UI는 terminal 보존 상태를 "대기 · 다음
명령 가능"으로 표시한다. LLM·allocator·priority·좌표 역할은 §22.7과 동일하게 불변.

**실행 중 새 mission을 이어서 (D-069, 재서술 D-070).** `NEW_MISSION`을 받는 시점은 completed
terminal에 국한하지 않는다. runtime을 보존한 어떤 session(= `EXECUTION_PAUSED` 또는 completed
`EXECUTED`)이든 받으며, "새 episode"로 리셋하지 않고 **하나의 이어지는 timeline**으로 처리한다:
- 검증된 새 graph를 실행할 executor를 **현재 sim time과 현재 agent 위치**(UAV는 마지막 확정
  좌표, UGV는 마지막 확정 route node)에서 seed한다. sim time은 0으로 돌아가지 않는다.
- phase는 `EXECUTION_PAUSED`를 유지하고 `advance_online_session`이 이어서 진행한다. `EXECUTED`
  에서 왔으면 D-055 follow-on처럼 `EXECUTED → EXECUTION_PAUSED` 전이만 한다.
- 옛 mission의 미완료 task는 버려지고 옛 mission은 `EXECUTION(COMPLETED)`를 받지 못한다.
  event stream은 옛 CheckpointAudit들 → `TURN(COMMITTED NEW_MISSION)` → 새 CheckpointAudit들로
  이어진다.
- `EXECUTION_FAILED`(one-shot/deadlock)는 여전히 거부한다 — "새 세션"으로 시작한다.

**반복 순찰 아님(§22.7 유지).** 이미 정찰 완료된 zone을 "재순찰"하면 그건 **새 recon task**로
현재 graph에 들어간다. 옛 sweep의 완료 기록은 감사에만 남고 재실행되지 않는다. 반복 순찰
루프를 구현하는 게 아니라, 운용자가 새 sweep 명령을 내렸고 agent가 현재 상태에서 수행하는
것이다.

continuous 재생 중 `NEW_MISSION`이 (직접 입력이든 §23.4.1 큐든) 수용되면 `ContinuousRuntime`은
그 boundary에서 옛 graph의 stale segment를 버리고 같은 sim time에서 새 graph의 다음 segment를
바로 이어 재생한다 — 재생을 멈추거나 새 `ContinuousRuntime`을 시작하지 않으며, 운용자에게는
한 번의 명령으로 끊김 없이 이어지는 것으로 보인다. monotonic clock 전제는 유지된다.

### 22.8 sensor 화재 감지 승인 게이트 (D-065)

`SimulatedFireField`(§22.2, D-062)가 공개하는 `FIRE_DETECTED`는 자동으로 대응 task를 만들지
않는다. 운용자가 아직 존재를 모르던 화재이고 home 근처에 사람이 있을 수 있으므로, 감지될
때마다 **무조건** 운용자에게 되묻는다("ZONE_x에 화재를 감지했습니다. 지상 로봇을
출동시킬까요?"). D-061에서 제거한 `THERMAL_RECON`의 "행동 전 확인" 역할을 사람 판단이
대신한다. D-062 이전 단일 `SimulatedFireSource` 경로와 운용자 자연어 `REPORT_INCIDENT`는 이
게이트를 거치지 않는다 — 전자는 P12 재현 고정, 후자는 운용자가 이미 판단한 보고다.

**pending 승인 큐.** 공개된 각 화재는 `PendingFireApproval`로 session의 `pending_approvals`
FIFO 큐에 들어간다. 한 checkpoint에서 여럿이 공개되면 zone id 오름차순으로 넣는다. 운용자는
큐의 head를 처리하고, 처리되면 다음 head가 활성화된다. `pending_approvals`가 비지 않은 동안
continuous clock·자동 재생·자유텍스트 명령 큐(§23.4.1)를 소비하지 않는다 — 승인 게이트가
자유텍스트 큐보다 우선한다. 이는 `PendingClarification`과 같은 성질의 resumable pending
상태이며 별도 `SessionPhase`를 만들지 않는다(phase는 `EXECUTION_PAUSED` 유지).

**결정 (기록 → boundary 적용, D-066).** 운용자 응답은 LLM 없이 결정론적으로 처리한다(후보
선택과 동일). 감지 즉시 clock을 멈추지 않는다 — 운용자는 다른 agent가 계속 움직이는 동안
답하고, 그 답은 `PendingFireApproval.decision`에 **기록만** 되며 **다음 task-completion
boundary**에서 적용된다(mid-segment 적용 없음). 그 boundary에서 `handle_turn` 앞과 같은
자리에, 결정된 승인을 FIFO 순으로 적용한다:
- 승인(scope = `GROUND_SUPPRESSION` 또는 `GROUND_INSPECTION`) → §22.3 공통 atomic incident
  transaction을 그 scope, `PolicyOrigin.EXPLICIT`로 수행한다. checkpoint clone에서
  `apply_online_patch(SELECTIVE)` + CBBA epoch 뒤 runtime을 교체하고, 실패하면 runtime·clock·
  graph identity를 보존한다.
- 거절 → scene·graph·runtime을 바꾸지 않는다. 화재는 audit로만 남는다.

`count`가 후보를 넘거나 하는 오류는 로드 시 거부하고, 적용은 결정된 head부터 진행하다가 첫
미결정 항목에서 멈춘다(큐 순서 보존).

**감사.** 공개 시 `outcome = "AWAITING_APPROVAL"` audit 1건, 적용 시 결정에 따라
`outcome ∈ {"COMMITTED", "REJECTED", "DECLINED"}` audit 1건을 append-only event log에 추가한다.
각 audit은 fixture id, zone, detecting agent, simulation time, 그리고 승인 시 scope·patch·
release/rebid 차이를 담는다.

**continuous runtime 연동 (D-066, 유예 범위 D-067).** 화재가 감지돼도 clock은 멈추지 않고
recon이 계속 진행된다 — 대응 task는 승인 전엔 graph에 없으므로 executor는 남은 순찰을 정상
실행하고 나머지 agent는 committed 궤적대로 계속 움직인다. **유예 = 남은 recon 전체.** 운용자가
recon 종료 전에 답하면 그 답은 다음 task-completion boundary의 `apply_recorded_fire_decisions`
에서 selective rebid로 반영되고(§22.3, mid-recon), recon이 끝난 뒤 답하면 completed terminal
checkpoint를 보존한 채 follow-on episode로 반영된다(§22.7/D-055). recon이 terminal에 도달했는데
아직 미결정 화재가 있으면 그때만 resumable halt한다(그 이후엔 대응 여부를 알아야 진행 가능).
답한 뒤 자동 재개한다. 미결정 화재는 recon 진행을 막지 않지만 자유텍스트 명령 큐(§23.4.1)와
자유텍스트 입력은 막는다.

두 발표 결과(승인 후 완주, 거절 후 무변경)는 모두 `COMPLETED` 또는 정직한 `EXECUTED`,
capability/precedence violation 0이어야 한다. 이는 simulated observation에 대한 운용자 승인
흐름이며 실제 perception이나 물리적 진압 성공 주장이 아니다.

---

## 23. Dynamic natural-language mission runtime (P13, D-056)

### 23.1 고정 world와 동적 mission의 경계

P13 Live 경로에서 미리 고정하는 것은 semantic world, fleet, route graph, task vocabulary,
workflow predecessor와 Validator 규칙뿐이다. 초기 task graph, incident response prefix,
resource request, active team과 assignment는 자연어와 현재 session state로부터 매번 생성·검증한다.
Live 기본 session에는 reference mission graph, latent incident fixture 또는 scripted backend 응답을
넣지 않는다. mock/cached는 시험·재현 모드이며 화면과 감사에서 Live와 명확히 구분한다.

자유 형식 입력은 무제한 행동 어휘를 뜻하지 않는다. LLM은 지원된 intent와 slot으로만 번역하고,
모르는 task·target·조건은 만들지 않는다. 따라서 “Warehouse를 UAV 한 대로 정찰해줘”는 지원된
graph와 자원 제약으로 처리할 수 있지만, 새 sensor payload나 임의 좌표를 요구하는 문장은
clarification 또는 UNSUPPORTED다.

### 23.2 resource request와 결정론적 team resolution

`ResourceRequest`는 platform별 `exact`/`min`/`max` 대수와 `required_agents`/
`excluded_agents`를 가진 strict 구조다. 정수는 bool이 아닌 0 이상의 int만 허용한다. 같은
platform에서 `exact`는 `min`/`max`와 함께 쓸 수 없고 `min <= max`여야 한다. agent id는 scene
fleet에 존재해야 하며 목록 내 중복과 required/excluded 교집합을 거부한다.

LLM은 이 제약을 추출할 뿐 task→agent mapping을 출력하지 않는다. 결정론적 resolver는 scene의
agent id 자연 정렬 순으로 가능한 active-team 부분집합을 열거하고 기존 `allocate()`를 그대로
호출한다. 모든 task가 할당되고 capability/precedence violation이 없으며 required agent가 최소
한 task를 실제로 맡는 candidate만 feasible이다. 선택 키는
`(estimated_makespan, total_distance, active_team_size, sorted_agent_ids)` 오름차순이다.
해가 없으면 명시적 `RESOURCE_INFEASIBLE`이며 full fleet로 조용히 fallback하지 않는다. 제약이
없으면 기존 full-fleet `allocate()`와 결과가 정확히 같아야 한다.

P13.1은 `NEW_MISSION`의 resource request와 initial team resolution을 먼저 구현한다. P13.2에서
별도 `UPDATE_RESOURCES`와 `REPORT_INCIDENT`에 동반된 request를 지원한다. 후속 request는 현재
policy를 atomic하게 교체하며, omitted field를 임의로 이전 값에서 추론하는 merge는 하지 않는다.

### 23.3 실행 중 resource 변경

실행 중 request는 다음 task-completion safe boundary에서 graph update와 한 transaction으로
적용한다. COMPLETED와 RUNNING task/assignment는 변경하지 않는다. 새 policy에서 제외된 agent가
RUNNING이면 그 task 완료까지 허용하고 이후 미시작 task에서 제외하는 deferred exclusion으로
감사한다. feasibility·Validator·reallocation 중 하나라도 실패하면 policy, graph, runtime,
simulation time과 assignment identity를 모두 보존한다.

P13.2부터 session과 executor의 `MissionState.agents`는 **scene 전체 fleet roster**를 보존한다.
`active_team`은 그 roster 중 새 CBBA 입찰과 새 task dispatch에 참여할 수 있는 집합이며, 따라서
둘을 같은 뜻으로 사용하지 않는다. initial team resolver도 subset으로 계획을 평가하지만 commit되는
state에서는 전체 roster를 유지한다. executor checkpoint는 `active_team`을 함께 저장·복원한다.

resource 교체 시 새 active team에서 빠진 agent의 ASSIGNED(미시작) task는 release/rebid한다.
RUNNING task는 release하지 않으며 그 agent는 즉시 새 입찰 대상에서는 빠지지만 현재 task를 끝낼
때까지 simulator roster에 남는다. 이를 `deferred_exclusions`로 감사한다. 완료 뒤 그 agent는 idle로
남고 future task를 dispatch하지 않는다. 다시 active team에 포함되면 새로 초기화하지 않고 roster에
보존된 마지막 확정 위치에서 입찰한다. 이 분리는 inactive agent의 위치를 scene 시작점으로 되감거나,
제외된 RUNNING agent가 다음 READY task를 다시 가져가는 것을 금지한다.

후속 team 후보는 현재 checkpoint의 COMPLETED/RUNNING prefix를 고정한 clone에서 미시작 assignment를
release한 뒤 잔여 mission을 끝까지 결정론적으로 rollout하여 검증한다. 모든 잔여 task가 완료되고
위반이 없으며 required agent가 잔여 task를 실제로 맡는 후보만 feasible이다. 선택 키는 P13.1과 같은
`(residual makespan, residual distance, active_team_size, sorted_agent_ids)`다. 선택된 candidate의
현재-checkpoint state만 commit하며 feasibility rollout의 미래 task status·clock은 commit하지 않는다.

감사는 raw/final intent wire, `ResourceRequest`, resolved active team, infeasibility code,
before/after assignment, released task, deferred exclusion과 적용 checkpoint time을 저장한다.

### 23.3.1 scenario-free Live 진입점 (P13.3)

native UI의 기본 profile은 `dynamic-world`이고 기본 mode는 `live`다. 이 profile은 zone, fleet,
route graph와 response point만 포함한 incident-empty semantic scene을 로드하며 initial graph,
latent incident fixture, expected command, mock response를 주입하지 않는다. 첫 task graph와 resource
request는 첫 자연어와 현재 empty session에서 생성된다. UI의 profile 선택은 world/test fixture의
선택이지 Live mission template 선택으로 표시하지 않는다.

`mock`은 exact scripted profile을 명시적으로 선택한 경우에만 사용할 수 있다. dynamic-world에서
mock을 선택해 임의 명령을 입력하면 명시적 wiring error이며 reference/mock graph로 fallback하지
않는다. `cached`도 model·prompt schema·context·utterance가 정확히 일치하는 응답만 사용한다. API
key 누락, network 오류, schema 오류 또는 infeasible request는 Live turn 실패/거부로 감사하며 mode를
바꾸거나 scripted mission을 대신 commit하지 않는다.

### 23.4 continuous 2D runtime과 입력 queue

P13.4는 `advance_to_next_completion()` 호출을 UI animation clock으로 쓰지 않는다. 별도 고정
wall-clock tick driver가 현재 committed segment 안에서 simulation time과 kinematic pose를
`SegmentView.frame_at`으로 연속 보간하고, task completion boundary에서만 연구 상태를 commit한다.
입력은 이동 중에도 FIFO 큐(§23.4.1)로 받는다. pending 명령은 현재 RUNNING task를 중단하지 않고
다음 safe boundary에서 정확히 한 번 적용된다.

boundary에서 연구 상태 전이(다음 checkpoint commit → sensor observation → queued 명령 1건의
`handle_turn`)는 tick driver가 **동기적으로** 수행하며, 그 사이 clock은 잠깐 멈춘다(별도
thread 없음, D-064). mock/cached 발표에서 이 정지는 수 ms이고, Live에서 boundary에 queued
명령이 있으면 눈에 띄게 끊길 수 있다. 결정론은 유지된다 — 적용 boundary는 wall-clock이 아니라
sim-time task 완료로 정해지므로 tick 간격·입력 시각·network latency가 **어느 boundary에
적용되는지**와 **결과 graph/resource/team/assignment**를 바꾸지 않는다. 동일 utterance,
pre-state hash와 적용 boundary가 같으면 결과도 같다. P13.4는 robot telemetry가 아니라 P10
schedule 기반 kinematic runtime이며 실제 비행으로 표시하지 않는다.

### 23.4.1 입력 queue 순서·취소 정책 (D-063)

재생 중 도착한 자유텍스트 명령은 제출 순서대로 FIFO 큐(`queued_commands`)에 쌓인다. P12.6의
단일 `queued_command`(2번째 입력이 1번째를 덮어쓰지 않되 1건만 허용) 제한을 대체한다. 각
발화는 독립된 운영자 결정이자 감사 대상이므로 큐에서 조용히 병합·삭제·교체하지 않는다.

큐는 safe boundary(task-completion checkpoint)마다 **정확히 한 건**을 소비한다. 소비 순서는
제출 순이고, 단일 운영자의 순차 입력이라 동률이 없다. 소비된 발화는 그 boundary의 commit된
checkpoint와 그 checkpoint의 simulated sensor observation을 먼저 반영한 상태에서 기존
`handle_turn`으로 한 번 처리된다. 결과가 `COMMITTED`/`NO_CHANGE`/`ANSWERED`이고 세션이 계속
실행 가능하면 다음 segment를 자동 재생하고 남은 큐의 다음 항목을 그 다음 boundary에서 처리한다.
`CLARIFICATION`/`UNSUPPORTED`/`REJECTED`/`TURN_ERROR` 또는 pending clarification이면 자동
진행을 멈추고 나머지 큐를 보존한 채 입력·후보 선택을 기다린다. 한 boundary에서 여러 턴을 몰아
처리하지 않는다 — 같은 simulation time에 감사 턴이 겹쳐 뒤 턴이 앞 턴의 효과를 보지 못한 채
처리되는 것을 피한다.

큐는 처리 전 presentation state이며 `TurnAudit`이 아니다. UI는 대기 항목을 제출 순서로
표시하고, 아직 소비되지 않은 항목은 운영자가 취소할 수 있다 — 취소는 graph·scene·runtime·
referent를 바꾸지 않으며 P8.3 후보 취소와 같은 성질이다. 소비 시점에 stale해진 명령(참조
대상이 이미 완료 등)은 특별 처리 없이 `handle_turn`이 그대로 거부·clarification한다.

승인 게이트(§22.8, 후속)의 pending 승인은 이 자유텍스트 큐보다 우선한다: 승인 대기 중에는
큐를 소비하지 않는다. 세부 순서는 §22.8 계약에서 확정한다.

### 23.5 ROS2/Gazebo adapter 경계

P14는 P13이 commit한 task와 assignment를 실행 platform 명령으로 변환하고 telemetry를 다시
session view에 공급하는 adapter다. LLM은 ROS topic, trajectory setpoint, velocity 또는 controller
명령을 만들지 않는다. multi-agent clock ownership, command acknowledgement, timeout, agent failure,
재접속과 world/launch 재현 조건은 P14.0 계약에서 먼저 고정한다. P14가 완료되기 전 native 2D
화면은 Gazebo 또는 실제 robot 실행으로 주장하지 않는다.
