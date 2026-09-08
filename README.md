# LLM_MRTA

LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

학부 학술대회 발표용 독립 연구 프로젝트. `/home/jiho/LLM_CBBA`와 Git 이력·연구 계약을
공유하지 않는다.

- 연구 계약 (단일 진실 원천): [`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md)
- 설계 결정 이력: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- 이식 코드 등록부: [`docs/PROVENANCE.md`](docs/PROVENANCE.md)

## 현재 단계

**P1~P6.5 완료** — `validator/`(P2) + `allocation/`(P3) + `execution/`(P4:
`SimExecutor`) + `llm/`(P5: Step1/Step2/repair 파이프라인 §12) + `evaluation/`(P6:
9개 입력 평가 하네스 + 감사 JSON + 시각화; P6.5: 통합 runner). **P8.1~P8.3 승인 완료** —
`interaction/`(intent schema, planning session, 결정론적 grounder, incident 등록,
canonical patch builder, 세션 orchestrator, 구조화된 clarification, 실행 감사, live/cached/mock)
+ `demo/app.py`(Streamlit 운영자 UI) + Validator 1.4. **P8.4 interaction 평가, P9
실행 중 명령·선택적 재할당, P8.5 정적 DAG/2D 지도, P10 checkpoint 구간 애니메이션,
P11 네이티브 운영자 콘솔·별도 2D simulator 창, P12 LLM-driven incident contingency와
P12.6 autonomous safe-checkpoint input까지 완료**. 테스트 859개 통과.

P6 실측(gpt-5-mini, 2026-09-02, validator 1.3): 9/9 approved, task precision/recall
1.00/1.00, edge P/R 1.00/1.00(family A·C), exact graph match 9/9, repair 0회. 상세는
[`docs/P6_RESULTS.md`](docs/P6_RESULTS.md), 원자료 `data/eval_results/`.
재현: `python3 -m evaluation --out data/eval_results/p6 --plot`.

P6.5 통합 runner(D-025, D-026): 대표 명령 A1/B1/C1. NL → `generate_mission`(RQ1) →
검증된 graph가 `allocate`(plan-time CBBA)와 `SimExecutor`(event-driven 실행)로 **각각**
들어간다(fork — allocate 결과는 executor에 전달 안 됨). 3/3 demo_pass(annotation
exact-match + 무위반 완주), A1(=P1 fixture graph)은 P3/P4 골든 makespan(359.8/257.9)과
graph_hash까지 일치. `python3 -m evaluation.integration [--mock]`.

priority·좌표·capability는 LLM이 만들지 않고 결정론적 compiler가 파생한다(D-022) —
LLM 출력은 graph 구조(task_type·target·edge)뿐이다. task 어휘: `GROUND_SUPPRESSION`
workflow (D-016). 계약 버전 v1.50 / 최신 결정 D-054 (P8 = 실행 전 다중 턴 자연어 계획
세션, §18 — P8.0~P8.4 완료). P8.4는 grounder-only 12/12, 실제 LLM end-to-end
dialogue exact 6/12이며 실패도 그대로 보고한다. 상세는
[`docs/P8_4_RESULTS.md`](docs/P8_4_RESULTS.md). 단계 게이트 정의는
[`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md) §15 참고.

P9는 task-completion checkpoint에서 실행을 멈추고, 운용자 업데이트로 생긴 새 READY task와
**입찰자가 겹치는 미시작 assignment만** release/rebid한 뒤 재개한다(bidder-connected selective
release). 대표 비교에서 no-reset/full-reset/selective release 수는 0/2/1, 세 정책 모두
COMPLETED·위반 0이며 makespan은 동일했다. 따라서 release 범위 축소만 주장한다. §19.3의
bundle-suffix 확장은 테스트된 경로에서 동작하지 않았으며(`suffix_extra_release_count = 0`)
실증된 결과로 서술하지 않는다 — 다른 update 형태에서 도달 가능한지는 미검증이다(D-041/D-042). 상세는 [`docs/P9_RESULTS.md`](docs/P9_RESULTS.md).

P12는 자연어 최초 명령에서 미래 화재 대응 깊이를 추출하고, UAV 정찰 완료의 엄격한 simulated
observation 또는 실행 중 자연어 화재 report를 동일한 atomic incident transaction과 P9
selective reallocation에 연결한다. 첫 Live engineering-feedback set은 4/8, 그 결과를 본 뒤
별도로 사전 커밋한 held-out paraphrase는 `gpt-5-mini-2025-08-07`에서 8/8 exact였다. 두 set을
같은 시험의 전후 성능 향상으로 주장하지 않는다. 상세와 발표 명령은
[`docs/P12_RESULTS.md`](docs/P12_RESULTS.md)에 있다.

## 네이티브 운영자 UI (권장)

발표·시연에는 운영자 콘솔과 2D simulator가 별도 창으로 열리는 P11 UI를 권장한다.

```bash
python3 -m pip install --user --upgrade pip
python3 -m pip install --user -e '.[desktop]'
python3 -m desktop
```

Ubuntu 22.04 기본 `pip 22.0.2`는 격리 환경에 최신 setuptools를 설치하고도 PEP 660
`build_editable` hook을 잘못 판정하는 경우가 있으므로, 첫 줄의 사용자 pip 업그레이드를 먼저
수행한다(D-050).

기본 실행 모드는 `mock`, 기본 scenario는 `UAV 순찰 → simulated fire detection`이며 운영자 창
상단에서 `mock`/`live`/`cached`와 scenario를 바꿀 수 있다. 두 창은 같은 `MissionSession`을
공유한다. 운영자 창에서 최초 임무가 승인되면 별도 실행 클릭 없이 checkpoint segment가 자동
재생된다. 재생 중 자연어 한 건을 전송하면 `QUEUED`로 표시되고 현재 이동을 끊지 않은 채 다음
task-completion safe checkpoint에서 실제 LLM/orchestrator가 처리한다. accepted update의 selective
release/rebid와 새 경로는 바로 다음 segment부터 보인다. `다음 checkpoint`와 `끝까지 연속 재생`
버튼은 수동 진단·회귀용으로 남아 있다.

`live`는 저장소 루트 `.env`의 `OPENAI_API_KEY`를 사용한다. 실제 API 호출임을 모드 배너에
표시하며, 성공 응답은 기존 exact cache 경로에 기록된다. `cached`는 동일한 모델·문맥·발화·
schema 응답만 네트워크 없이 재생한다. D-054의 prompt namespace는 `p12-v3`이므로 이전
`p12-v2` cache는 새 prompt의 Live 응답으로 가장해 재사용하지 않는다.

P12 발표는 상단 scenario 선택에서 `UAV 순찰 → simulated fire detection` 또는 `UAV 순찰 중
자연어 화재 신고`를 고른다. `mock`은 화면이 제시하는 고정 문장만 받는다. `live`는 지원 범위의
자연어를 실제 모델로 해석하고, `cached`는 이전 Live와 모델·문맥·발화가 모두 같은 경우만
재생한다. 검증된 cached/live 예시 문장은 `docs/P12_RESULTS.md`의 “발표 재생” 절에 있다.

## Streamlit UI (fallback)

저장소 루트에서 실행한다.

```bash
python3 -m pip install --user -e '.[llm,demo,viz]'
streamlit run demo/app.py
```

브라우저 기반 Streamlit UI도 그대로 유지한다. `live`는 실제 OpenAI API를 호출하고 성공 응답을
로컬 cache에 기록한다. `cached`는 모델·문맥·발화·schema가 정확히 같은 응답만 네트워크 없이
재생하며, `mock`은 화면 확인용 고정 스크립트다. 세 모드는 UI와 감사 JSON에 명시되며 서로 바꿔
표시하지 않는다. P8.3 검증 기록은
[`docs/P8_3_RESULTS.md`](docs/P8_3_RESULTS.md)에 있다.

온라인 실행은 두 방식이다(D-048). `온라인 실행 시작`/`다음 checkpoint까지 재생`은 전역에서
가장 이른 task-completion checkpoint마다 멈추므로, 여기서 후속 자연어 명령과 P9 selective
release/rebid를 시험할 수 있다. 화면은 정지 원인 task와 아직 `TRAVEL/DWELL 중 일시정지`인
agent를 구분한다. `끝까지 연속 재생`은 같은 checkpoint 구간을 terminal까지 이어서 재생하지만
구간 사이 명령은 받지 않는다. UAV는 직선, UGV는 route graph polyline을 따라 움직인다. 이는
discrete-event schedule의 보간이며 실제 telemetry·물리 pose나 임의 시각 interrupt를 뜻하지
않는다. 사이드바에서 재생 on/off와 1x/2x/5x 표시 배속을 고를 수 있다.

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소를 통합하고
재현 가능하게 시연·평가한다.
