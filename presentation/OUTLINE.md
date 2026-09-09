# LLM-MRTA 발표 — 목차 & 슬라이드별 핵심 메시지

산출물: `presentation/LLM-MRTA_발표.pptx` (11매, 16:9)
생성: `python3 presentation/deck_figures.py && python3 presentation/build_deck_d075.py`
근거: 계약 v1.70 (D-075) · `docs/RESEARCH_CONTRACT.md` · `docs/DECISIONS.md` · `data/eval_results/`

발표 목표(구현팀 공유용 한 줄):
> 이 발표의 목표는 '기능이 많다'가 아니라, **왜 LLM과 결정론적 계획/검증을 분리했고,
> 그것이 online multi-robot mission replanning으로 어떻게 이어지는지**를 12분 안에
> 설득하는 것이다. Architecture · Online Reallocation · Demo 세 장이 본론이다.

foreground 3가지: ① Validated NL→Mission Graph  ② Heterogeneous CBBA Allocation
③ Online NL Update + Selective Reallocation.
single-call / latency / UI 는 이 셋을 뒷받침하는 하위 결과로만 배치.

| # | 슬라이드 | 핵심 메시지 (1문장) | 목표 시간 |
|---|---|---|---|
| 1 | Title | 자연어로 이종 UAV·UGV 임무를 주면, 검증된 실행 그래프로 바꾸고 CBBA로 배정하며, 실행 중 자연어 수정에는 영향받은 부분만 다시 배정하는 시스템이다. | 0:45 |
| 2 | Background & Motivation | 사람이 task를 정의·배정하는 것은 부담이고, 자연어는 매력적이지만 LLM 출력은 비결정적·비실행성이라 로봇 제어에 바로 연결하면 위험하다. | 1:15 |
| 3 | Related Work | 기존은 다단계 LLM actor/critic으로 범용 mission을 만들지만, 우리는 실행 어휘를 제한하고 결정론적 invariant 검증을 두는 다른 reliability 전략이다(우월 주장 아님). | 1:00 |
| 4 | Core Idea | LLM은 의도와 mission graph 후보를 생성하고, 결정론적 계층이 실행 의미·안전을 결정하며, CBBA가 누가 수행할지를 정한다. | 1:00 |
| 5 | System Architecture ★ | 생성(LLM 2회) → 결정론적 invariant 검증 → (invalid 시 bounded repair ≤1) → compile → CBBA → executor, 그리고 실행 중에는 같은 파이프라인이 온라인 루프로 돈다. | 2:00 |
| 6 | NL → Validated Mission Graph | 자연어 명령에서 LLM이 task+의존관계 후보를 내면, 결정론적 Validator가 schema/reference·DAG·workflow·capability·reachability를 검사한다(정형검증 아님). | 1:15 |
| 7 | Heterogeneous CBBA Allocation | 검증된 task를 UAV(직선 정찰)·UGV(도로망 대응)의 능력과 이동비용에 따라 CBBA가 분산 배정한다. | 1:00 |
| 8 | Online Interaction & Selective Reallocation ★ | 실행 중 수정은 처음부터 재계획하지 않고 영향받은 배정만 release/rebid하며, 대표 fixture에서 release 수를 줄이고(0/3/4) UAV commitment를 보존한다(makespan 동일). | 1:45 |
| 9 | Simulator — Demo Flow ★ | 15구역 데모에서 World → 임무 → 할당 → 실행 → latent 화재 발견 → 선택적 재할당의 시간 흐름을 6개 프레임으로 보여준다. | 1:30 |
| 10 | Evaluation — Key Results | 그래프 생성·검증(P6 9/9 exact, repair 0), 온라인 선택적 재할당(release 0/3/4·위반 0·makespan 동일), single-call latency ablation(품질 동일·paired latency −46%/−29%). | 1:30 |
| 11 | Conclusion & Limitations | 자연어→실행 그래프 / 결정론적 검증+CBBA로 안전·재현 가능한 할당 / 온라인 명령에 선택적 재할당 — 한계는 제한된 어휘·단일 scene 계열·단일 모델·작은 세트, 후속은 ROS2/PX4/Gazebo·진짜 비동기. | 1:15 |

합계 목표 ≈ 13:15 (버퍼 포함). 실제 대본은 SCRIPT.md 기준 ≈ 11:30.
Architecture(2:00)와 Online Reallocation(1:45) + Demo(1:30)에 시간을 더 배분함.
