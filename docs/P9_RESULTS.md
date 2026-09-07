# P9 실행 중 명령과 선택적 재할당 결과

재현 기준: 계약 v1.38 / D-041, `ONLINE_POLICY_VERSION=1.0`, `VALIDATOR_VERSION=1.4`.

## 구현 범위

온라인 실행은 wall-clock thread를 임의 중단하지 않는다. `SimExecutor`가 가장 이른 task 완료
event까지 진행한 직후 정지하며, 완료된 task와 아직 수행 중인 task를 잠근다. 이 상태에서
운용자는 기존 P8의 자연어 경로로 화재를 보고하고 대응 workflow를 추가할 수 있다. 승인된
UPDATE만 checkpoint 복제본에서 patch 검증, 선택적 release, CBBA epoch를 모두 마친 뒤 session
runtime을 교체한다. clarification, NO_CHANGE, Validator 거부, 예외는 기존 runtime을 보존한다.

Streamlit에는 기존 한 번에 끝까지 실행하는 버튼과 온라인 실행 버튼을 별도로 둔다. 온라인
실행은 매 task 완료 event에서 멈추며 simulation time, 방금 완료된 task, RUNNING/READY task,
현재 assignment와 UPDATE의 release/rebid 차이를 표시한다.

## 대표 비교 입력

입력은 결과를 보기 전에 `data/online_reallocation_fixture.yaml`로 고정했다. 기존 scene에 화재
3개를 결정론적으로 등록해 총 5개 incident의 full workflow와 구역 정찰을 실행한다. 10번째
완료 event(t=121.643232s)에서 정지한 뒤 ZONE_B에 FIRE_SITE_6을 보고하고 지상 진압까지 4단계
workflow를 추가한다.

checkpoint에는 COMPLETED 10개와 RUNNING 5개가 잠겨 있고, 미시작 ASSIGNED task는 다음 2개다.

- `AREA_RECON__ZONE_C` → S2
- `GROUND_INSPECTION__FIRE_SITE_1` → G1

신규 READY `THERMAL_RECON__FIRE_SITE_6`과 bidder를 공유하는 직접 영향 task는 항공 정찰 하나다.
따라서 세 정책의 release 범위가 구분된다.

## 원시 결과

| 정책 | release | 보존된 미시작 assignment | suffix 추가 release | 새 epoch rounds | 최종 makespan | 종료/위반 |
|---|---:|---:|---:|---:|---:|---|
| no-reset | 0 | 2 | n/a | 3 | 453.883s | COMPLETED, 0/0 |
| full-reset | 2 | 0 | n/a | 4 | 453.883s | COMPLETED, 0/0 |
| selective | 1 | 1 | **0** | 4 | 453.883s | COMPLETED, 0/0 |

세 정책 모두 직접 영향 task는 `AREA_RECON__ZONE_C` 하나였다.

selective는 `AREA_RECON__ZONE_C`만 release하고, bidder가 겹치지 않는 UGV task
`GROUND_INSPECTION__FIRE_SITE_1`을 보존했다. full-reset은 둘 다 release했다. 세 정책 모두
FIRE_SITE_6의 THERMAL_RECON/SUPPRESSANT_DROP을 R1, GROUND_INSPECTION/GROUND_SUPPRESSION을
G2에 할당했다. 누적 UAV 거리 1448.062m, UGV 경로거리 761.703m, 기존 task owner change 0으로
세 정책이 같았다.

## 해석과 한계

이 fixture에서 selective 정책은 full-reset보다 미시작 commitment 한 개를 더 보존하면서도
no-reset과 달리 영향받은 항공 task를 release/rebid했다. COMPLETED/RUNNING 보존과 무위반
완주라는 안전 게이트도 세 정책 모두 통과했다.

그러나 makespan, 거리, 최종 owner는 같았다. 따라서 이 결과로 selective가 더 빠르거나 더
최적이라고 주장할 수 없다. 입증된 것은 고정 checkpoint에서 불필요한 release 범위를 줄였다는
것뿐이다. 이 정책은 결정론적 규칙이지 전역 최소 reset을 계산하는 알고리즘이 아니다.

### bundle suffix 확장은 실증되지 않았다 (D-041)

§19.3 3단계는 직접 영향 task **뒤에 줄 서 있는 비영향 task까지** release하는 bundle-suffix
규칙을 포함한다. 이 실행에서 그 확장은 **한 번도 동작하지 않았다** —
`suffix_extra_release_count = 0`, 즉 `released == directly_affected`다.

이는 fixture를 잘못 골라서가 아니라 현재 운용 경로의 구조 때문이다. canonical online
update(`build_chain_patch`)는 `AREA_RECON`을 만들지 않으므로 신규 incident에서 즉시 READY가
되는 task는 `THERMAL_RECON` 하나뿐이고, 그 bidder union은 UAV 전체다. 따라서 모든 UAV task가
영향, 모든 UGV task가 비영향이 되는데 bundle은 한 agent(=UAV이거나 UGV)의 것이므로 **섞인
bundle이 존재할 수 없다**.

그러므로 이 문서가 주장하는 것은 다음까지다.

> 신규 READY task와 입찰자가 겹치는 기존 미시작 assignment만 release/rebid하여, full reset보다
> 더 많은 기존 assignment를 보존하면서 무위반 완주했다.

주장하지 **않는** 것: 직접 영향 task 뒤의 비영향 task까지 suffix 규칙으로 추가 release하는
동작이 실제 end-to-end 시나리오에서 발생했다는 것. suffix 분기의 정확성은 손으로 구성한
상태에 대한 단위테스트(`tests/test_online_allocation.py`)로만 고정돼 있으며, 이는 **분기 검증**
이지 end-to-end 실증이 아니다. 코드에 규칙을 남겨 둔 이유는 다른 신규 READY 조합에서 bundle
prefix commitment를 깨지 않기 위한 보수적 안전장치이기 때문이다.

재현:

```bash
python3 -m evaluation.online_reallocation \
  --out data/eval_results/p9_online_reallocation
```

원자료는 `data/eval_results/p9_online_reallocation.{json,txt}`에 있다.
