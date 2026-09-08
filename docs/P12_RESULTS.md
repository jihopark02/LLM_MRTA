# P12 LLM-driven incident contingency 결과

## D-061 재실행 (3종 vocabulary)

계약 v1.57 이후 `gpt-5-mini-2025-08-07` live 재실행. workflow가 2단계(GROUND_INSPECTION ->
GROUND_SUPPRESSION)로 줄어 policy depth는 null / GI / GS 3종이다. unsupported 케이스는
P13(D-056)이 자원 대수 제약을 지원 범위로 바꿔 stale였으므로 "우선순위 변경"으로 교체했다.

- main annotation (`data/p12_counterfactual.yaml`): **exact 6/6**, 응답 case 전부 COMPLETED·위반 0
- held-out (`data/p12_counterfactual_heldout.yaml`): **exact 6/6**, 전부 COMPLETED·위반 0
- 정책 없음 -> 0 task, GI -> 1 task, GS -> 2 task (workflow prefix 정확히 반영)

원자료 `data/eval_results/p12_gpt-5-mini{,_heldout}.{json,txt}`. D-061 이전(5종, 첫 Live 4/8 등)
결과는 `data/eval_results/pre_d061_5type/`에 보존.

---

재현 기준: `feature/operator-interaction`, 계약 v1.49 / D-053. P12는 실제 perception이
아니라, 자연어로 만든 incident response policy 또는 실행 중 자연어 report를 기존
Validator → selective CBBA → checkpoint executor 경로에 연결한 실험이다.

위 버전은 평가 artifact의 역사적 기준이다. 현재 native 발표 UI는 계약 v1.51 / D-055이며,
평가 수치를 바꾸지 않고 자동 재생·safe-checkpoint command queue와 completed-patrol follow-on
incident episode를 추가했다.

## 평가 설계

동일한 `patrol_park` scene(초기 known incident 0)에서 8 case를 실행한다.

- policy 5개: 정찰만, 감지 시 `THERMAL_RECON`, `SUPPRESSANT_DROP`,
  `GROUND_INSPECTION`, `GROUND_SUPPRESSION`까지.
- operator report 2개: Warehouse(`ZONE_A`)와 Tank Farm(`ZONE_D`)의 새 화재.
- unsupported 1개: 특정 UAV 한 대만 사용하라는 resource constraint.

sensor case의 화재는 `simulated-fire-zone-b-v1` fixture가 `AREA_RECON__ZONE_B` 완료
checkpoint에서 한 번 공개한다. fixture는 초기 scene, scene hash, LLM context와 초기 graph에
들어가지 않는다. sensor와 operator report는 동일한 atomic incident transaction을 사용한다.

## 첫 Live 실행 — engineering feedback set

입력: `data/p12_counterfactual.yaml`  
원시 결과: `data/eval_results/p12_gpt-5-mini_first_pass.{json,txt}`

| 지표 | 결과 |
|---|---:|
| model snapshot | `gpt-5-mini-2025-08-07` |
| exact case | 4 / 8 |
| exact policy depth | 3 / 5 |
| exact operator report | 0 / 2 |
| unsupported fail-closed | 1 / 1 |

두 `NEW_MISSION`은 선택 kind에 속하지 않는 `note` 또는 `zone_ref`를 채워 strict wire
schema가 거부했다. 두 report는 `Warehouse에서` / `Tank Farm에서`를 slot에 보존했지만 당시
zone normalizer가 한국어 위치 조사를 처리하지 않아 clarification했다. 이 결과는 D-052 이전
첫 관측값이며 삭제하거나 새 결과로 덮어쓰지 않는다.

## D-052 이후 별도 held-out paraphrase

입력은 결과 확인 전에 커밋한 `data/p12_counterfactual_heldout.yaml`이다. 첫 실행의 어떤
명령 문장도 재사용하지 않았다. 원시 결과는
`data/eval_results/p12_gpt-5-mini_heldout.{json,txt}`에 있다. 동일 Live cache를 D-053 감사
schema로 재생한 결과는
`data/eval_results/p12_gpt-5-mini_heldout_cached_audit.{json,txt}`에 별도 보존한다.

| case | 기대/실제 response task | selective release | termination | exact |
|---|---:|---:|---|---:|
| H_P0_RECON_ONLY | 0 / 0 | 0 | COMPLETED | ✓ |
| H_P1_THERMAL | 1 / 1 | 1 | COMPLETED | ✓ |
| H_P2_DROP | 2 / 2 | 1 | COMPLETED | ✓ |
| H_P3_INSPECTION | 3 / 3 | 1 | COMPLETED | ✓ |
| H_P4_SUPPRESSION | 4 / 4 | 1 | COMPLETED | ✓ |
| H_R1_WAREHOUSE | 4 / 4, `ZONE_A` | 2 | COMPLETED | ✓ |
| H_R2_TANK_FARM | 4 / 4, `ZONE_D` | 2 | COMPLETED | ✓ |
| H_U1_NAMED_AGENT | UNSUPPORTED | 0 | n/a | ✓ |

요약: **8/8 exact**, 모든 실행 case `COMPLETED`, capability/precedence violation 0/0.
실제 snapshot은 전부 `gpt-5-mini-2025-08-07`이었다. D-053 cached exact replay의 모든
`TurnAudit`에서 `intent_repair_attempted=false`, `intent_repair_recovered=false`였으므로 이
held-out Live 응답들은 D-052의 1회 schema repair를 실제로 사용하지 않았다. repair 성공과
2차 실패 경로는 strict 회귀 테스트로 확인했다.

첫 4/8과 held-out 8/8은 문장이 다른 두 set이므로 paired improvement나 통계적 유의성을
주장하지 않는다. 8/8은 **사전 고정한 이 작은 held-out set에서 입력에 따라 policy depth와
reported zone이 달라졌고, 그 결과 graph·release·경로가 달라졌음**을 보이는 통합 증거다.

## 발표 재생

```bash
python3 -m desktop
```

센서 시나리오(cached/live):

1. `1 · UAV 순찰 → simulated fire detection` 선택.
2. `네 개 구역을 모두 항공 정찰하고 새 화재가 감지되면 지상 로봇 진압 단계까지 완료해줘`
3. 승인 직후 자동 재생되는 UAV 순찰을 본다. 별도 checkpoint 클릭은 필요 없다.
4. `AREA_RECON__ZONE_B` 완료 시점의 simulated observation, 새 `FIRE_SITE_1`의 4개 workflow
   task, selective reallocation과 바뀐 다음 경로를 확인한다.

운영자 report 시나리오(cached/live):

1. `2 · UAV 순찰 중 자연어 화재 신고` 선택.
2. `네 개 구역 전체를 항공 정찰만 해줘`
3. 자동 재생 중 `Warehouse 구역에 새 화재가 발생했어. 지상 로봇 진압 단계까지 대응해줘`를
   입력하고 `QUEUED — 다음 safe checkpoint에서 적용` 표시를 확인한다.
4. 현재 움직임이 중단되지 않고 checkpoint에 도달한 뒤 실제 LLM 턴이 처리되는지 확인한다.
5. task 4→8, `ZONE_A`, selective release와 다음 segment 경로 변화를 확인한다.

`cached`는 이 머신에 `p12-v4` prompt로 기록한 실제 Live 응답 cache가 있을 때만 위 문장을 exact
replay한다. D-055 이전 `p12-v3` cache는 재사용하지 않는다. `mock`은 별도의 화면-wiring
script이며 UI가 표시하는 정확한 mock 문장만 받는다.

### 정찰이 먼저 끝난 경우

`AREA_RECON` 4개는 반복 순찰이 아니라 유한 task이므로 마지막 구역 정찰 뒤 `EXECUTED`가 되는
것이 정상이다. 운용자가 재생 중 입력하지 못했더라도 online `COMPLETED` terminal runtime은
보존된다. 같은 세션에서 아래처럼 새 화재와 대응 깊이를 함께 보고하면 기존 4개 정찰의 완료
상태·simulation time·agent 마지막 위치를 보존하고 신규 incident workflow 4개만 추가해 자동
재생한다.

```text
네 개 구역 전체를 항공 정찰만 해줘
# 정찰 4개 완료 뒤에도 입력 가능
Warehouse 구역에 새 화재가 발생했어. 지상 로봇 진압 단계까지 대응해줘
```

감사 순서는 첫 `EXECUTION(COMPLETED)` 뒤 `TURN(COMMITTED)`과 두 번째
`EXECUTION(COMPLETED)`이 남는다. 이 경로는 terminal 뒤 시작한 **follow-on episode**이며,
첫 실행 도중 safe checkpoint에서 명령을 넣어 기존 미시작 assignment를 release/rebid하는 P9
mid-run 결과와 같은 것으로 집계하지 않는다.

## 한계

- 단일 model snapshot, 8개 held-out case의 소규모 평가다.
- 화재 감지는 strict latent fixture가 만든 simulated observation이며 실제 영상/열 센서가 아니다.
- 이동은 discrete-event schedule의 kinematic playback이고 실제 robot telemetry가 아니다.
- 특정 agent/대수 제약은 아직 지원하지 않으며 조용히 무시하지 않고 `UNSUPPORTED`로 거부한다.
- LLM은 intent·slot·초기 graph를 만들지만 좌표, priority, capability, assignment, release와
  Validator 판정은 결정론적 코드가 담당한다.
