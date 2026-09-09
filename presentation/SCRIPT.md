# 12분 발표자 대본 (LLM-MRTA)

- 슬라이드별 목표 발화 시간 + 실제로 읽었을 때 누적 시간(대략).
- 한국어 발화 기준 ≈ 320자/분으로 맞춤. 전체 ≈ 11분 30초 (질의 대비 버퍼 30~60초).
- Architecture · Online Reallocation · Demo 에 시간 배분을 더 뒀다.
- PPTX 발표자 노트에도 같은 내용이 요약되어 있다.

---

## 1. Title — 목표 0:45  (누적 0:45)

"발표를 시작하겠습니다. 제목을 그대로 읽는 대신 시스템을 한 문장으로 규정하겠습니다.
재난 대응 상황에서 운용자가 자연어로 여러 UAV와 UGV의 임무를 지시하면, 이 시스템은
그 지시를 **검증된 실행 계획**으로 바꾸고, CBBA로 어느 로봇이 무엇을 할지 배정하며,
실행 도중에 운용자가 자연어로 임무를 고치면 **영향받은 부분만** 다시 배정합니다.
오늘 발표의 목표는 우리가 만든 기능을 나열하는 것이 아니라, 왜 LLM과 결정론적
계획·검증을 분리했고 그것이 온라인 다중로봇 재계획으로 어떻게 이어지는지를 보이는
것입니다. 화면 아래 한 문장 — LLM은 의도와 후보를 생성하고, 결정론적 계층이 실행
의미와 안전을 결정한다 — 이게 발표 전체의 척추입니다."

## 2. Background & Motivation — 목표 1:15  (누적 2:00)

"두 가지 배경을 세우겠습니다. 첫째, 재난 다중로봇 대응에서는 운용자가 정찰·점검·진압
task를 일일이 정의하고, 어느 로봇이 그것을 언제 할지 수동으로 배정해야 합니다. 느리고
실수가 나기 쉽습니다. 게다가 상황은 실행 중에 계속 바뀝니다 — 새 화재가 나고, 쓸 수
있는 로봇이 달라집니다.
둘째, 자연어로 임무를 주면 빠르고 유연합니다. 사람이 목표만 말하면 되니까요. 그런데
LLM 출력에는 함정이 있습니다. 비결정적입니다 — 같은 입력에 다른 계획이 나옵니다.
존재하지 않는 구역이나 화재를 지시할 수 있습니다. 작업의 선후관계나 로봇 능력, 도달
가능성을 보장하지 않습니다. 그래서 이 슬라이드의 결론은 하나입니다 — **LLM 출력을
그대로 로봇 제어에 연결하는 것은 위험합니다.**"

## 3. Related Work — 목표 1:00  (누적 3:00)

"기존 연구를 짧게 보겠습니다. 우리가 구조적으로 참고한 MP4MR를 비롯한 LLM mission
planning 연구는 여러 LLM actor가 임무를 해석하고 task로 분해하고 실행 primitive로
매핑하고 명세를 만들며, LLM critic이 그 결과를 다시 검토하는 구조입니다. 표현력은
넓지만 inference 비용이 크고 출력은 여전히 확률적입니다.
우리는 다른 전략을 택했습니다. 실행 가능한 task 어휘를 세 종류로 제한하고, LLM 출력을
별도의 **결정론적 invariant 검증**으로 보장하며, 그 위에서 온라인 다중로봇 재할당을
합니다. 직접 성능 비교는 하지 않았고 더 우월하다고 주장하지 않습니다 — 신뢰성을
확보하는 전략이 다를 뿐입니다."

## 4. Core Idea — 목표 1:00  (누적 4:00)

"이 슬라이드의 문장이 발표의 중심입니다. 천천히 읽겠습니다.
**LLM은 운용자의 semantic intent와 mission graph 후보를 생성하고, 결정론적 계층이
정확한 실행 의미와 안전성을 결정하며, CBBA가 누가 수행할지를 결정한다.**
세 개의 기둥이 있습니다. 첫째, 검증된 자연어-그래프 변환. 둘째, 이종 CBBA 할당.
셋째, 실행 중 수정과 선택적 재할당. 나머지 발표는 이 셋을 하나씩 보여드립니다."

## 5. System Architecture — 목표 2:00  (누적 6:00)  ★

"이 그림이 발표의 뼈대입니다.
위 줄은 임무 생성입니다. 운용자 자연어가 들어오면 Semantic Interpreter가 의도와 슬롯을
뽑습니다. 그다음 Structured Graph Synthesis가 task 목록과 의존관계를 **한 번의 구조화
호출**로 만듭니다. 이 후보는 반드시 Deterministic Invariant Validator를 통과해야 합니다.
스키마와 참조 존재성, DAG와 사이클 여부, workflow 선후관계, 로봇 능력, 도달성을
검사합니다. 검증에 실패하면 **최대 한 번** bounded repair로 고쳐 다시 검증하고, 통과하면
Compiler가 실행 그래프로 grounding한 뒤 CBBA가 배정하고 Checkpoint Executor가 실행합니다.
아래 줄은 실행 중입니다. 새 자연어 명령이나 감지된 화재가 들어오면 같은 Semantic
Interpreter를 거쳐 결정론적 patch와 grounding을 만들고, 영향받은 미시작 배정만 release한
뒤 선택적으로 CBBA 재할당을 하며, 이는 Executor의 다음 안전한 checkpoint에서 반영됩니다.
여기서 강조할 점 — LLM은 semantic reasoning에만 쓰이고, 실행 가능성과 안전성은 별도의
결정론적 계층이 보장합니다. LLM을 여러 번 호출해서 신뢰성을 얻는 구조가 아니라,
필요한 곳에만 LLM을 쓰고 정확성은 결정론적으로 강제하는 구조입니다."

## 6. NL → Validated Mission Graph — 목표 1:15  (누적 7:15)

"구체적인 예를 봅니다. 운용자가 '구역 A, D, G를 정찰하고 FIRE_SITE_1은 지상 진압까지
대응해줘'라고 하면, LLM은 task와 의존관계 후보를 냅니다 — 세 개의 독립적인 AREA_RECON과,
GROUND_INSPECTION에서 GROUND_SUPPRESSION으로 이어지는 체인입니다. task 어휘는 세 종류뿐
입니다 — 구역 항공 정찰, 그리고 incident에 대한 지상 점검과 진압.
그다음 이 후보가 결정론적 Validator를 통과해야 합니다. 참조가 실제 존재하는지, 사이클이
없는지, 선후관계가 맞는지, 로봇 능력에 맞는지, 도달 가능한지. 이건 결정론적 invariant
검사이지 정형검증이 아닙니다. 그리고 중요한 것 — LLM은 좌표, 우선순위, 능력, 어느
로봇이 할지, 할당을 만들지 않습니다. 그건 전부 결정론적 계층의 몫입니다."

## 7. Heterogeneous CBBA Allocation — 목표 1:00  (누적 8:15)

"할당은 CBBA로 합니다. fleet은 이종입니다 — 동일한 UAV 세 대는 항공 정찰을 직선으로
하고, UGV 두 대는 지상 점검·진압을 도로망을 따라 합니다. CBBA에서는 각 로봇이 자기
능력에 맞는 task에만 입찰하고, 이동비용과 우선순위로 bundle을 구성하며, task가 완료될
때마다 READY가 된 다음 task를 다시 입찰합니다. 수식은 넘어가겠습니다 — 핵심은 검증된
task가 로봇 능력과 이동비용을 고려해 분산 배정된다는 것, 그리고 이종 이동 모델이 다음
데모에서 눈에 보인다는 것입니다."

## 8. Online Interaction & Selective Reallocation — 목표 1:45  (누적 10:00)  ★

"실행 중에 새 incident가 감지되거나 운용자가 새 명령을 주면, 전체 임무를 처음부터 다시
계획하지 않습니다. 자연어를 semantic update로 해석하고, 결정론적으로 patch와 grounding을
만들고, 영향받은 미시작 배정만 release한 뒤 CBBA로 다시 입찰합니다.
왼쪽 그림 — full reset은 모든 배정을 풀어버립니다. 오른쪽 — 선택적 release는 새로 생긴
지상 대응만 풀고 UAV 정찰 bundle은 그대로 둡니다.
대표 fixture에서 release 수는 no-reset 0, 선택적 3, full-reset 4였고, 세 정책 모두 임무를
완주했으며 위반이 없고 makespan이 동일했습니다. 그래서 우리 주장은 딱 하나입니다 —
선택적 재할당이 불필요한 release를 줄이고 진행 중인 UAV commitment를 보존한다. 더 빠른
경로나 더 좋은 최적해를 찾는다고 주장하지 않습니다. makespan이 같으니까요."

## 9. Simulator — Demo Flow — 목표 1:30  (누적 11:30)  ★

"15구역 데모로 전체 흐름을 봅니다.
1) 임무 전에도 world가 보입니다 — 15개 구역 A부터 O, UGV 도로망, depot의 로봇 다섯 대.
2) '모든 구역을 항공 정찰해줘' → 15개 AREA_RECON, 의존관계 0, 검증 통과.
3) CBBA가 세 UAV에 지역별로 분산합니다 — 화면에 각 UAV의 담당 구역이 색으로 보입니다.
4) checkpoint 기반 실행, task 사이의 안전한 경계에서 멈출 수 있습니다.
5) 구역 J 정찰이 끝나면 숨어 있던 화재가 드러납니다 — 나머지 화재는 아직 안 보입니다.
   화재 감지는 운용자 승인 게이트를 거칩니다.
6) 새 지상 대응만 입찰됩니다 — G1이 J로 가고, UAV 정찰 배정은 그대로입니다.
앞 슬라이드의 선택적 재할당이 화면에서 실제로 어떻게 보이는지입니다."

## 10. Evaluation — Key Results — 목표 1:30  (누적 13:00 → 압축해 1:00 권장, 누적 12:30)

"세 축만 보겠습니다.
첫째, 그래프 생성과 검증. gpt-5-mini로 9개 명령을 돌렸고 9/9 승인, exact-match 9/9,
repair는 한 번도 필요 없었고 정확도는 1.00입니다.
둘째, 온라인 선택적 재할당. release 수 0/3/4, 세 정책 모두 완주, 위반 0, makespan 동일 —
release 범위만 줄인다는 주장입니다.
셋째, single-call latency ablation. 원래 task 생성과 의존관계 생성을 두 번의 LLM 호출로
나눴는데, 이걸 한 번의 구조화 호출로 통합해 비교했습니다. clean 세트에서 두 방식 모두
9/9 exact이고 single-call이 약 44% 빨랐습니다. 결과 보기 전에 고정한 어려운 영어 명령
세트와 15구역 규모 세트에서도 exact-match는 동일했고 명령별 median latency가 각각 46%,
29% 줄었습니다. single-call은 우리 연구의 main contribution이 아니라 online 응답성을 위한
구현 결정입니다."

## 11. Conclusion & Limitations — 목표 1:00  (누적 13:30)

"결론은 세 문장입니다. 자연어 임무를 실행 가능한 task graph로 바꾼다. 결정론적 invariant
검증과 CBBA로 안전하고 재현 가능한 할당을 만든다. 실행 중 자연어 명령에는 선택적
재할당을 적용한다.
한계를 솔직히 말합니다 — 평가는 제한된 task 어휘, 특정 scene 계열, 단일 모델 스냅샷,
비교적 작은 세트에 기반합니다. 시뮬레이터에서 명령은 queue되지만 안전 경계에서 LLM
처리는 동기적입니다 — '로봇이 움직이는 동안 LLM이 생각한다'가 아닙니다.
후속은 ROS2·PX4·Gazebo 물리 실행, 진짜 비동기 상호작용과 stale-state 보호, 더 다양한
임무·언어 평가입니다. 감사합니다."

---

### 예상 Q&A (speaker note 요약)

- **"LLM을 왜 쓰나요, 어휘 3종이면 rule-based parser로도 되지 않나요?"** →
  자연어의 다양한 표현(복합·부정·순서 뒤섞임·selective target·미래 조건)을 executable
  graph로 매핑하는 것이 핵심이고, D-074 stress set이 그 표현 다양성을 다룹니다. rule
  parser는 이 표현 공간을 감당하지 못합니다. 다만 **정확성 보장**은 rule 기반 Validator가
  합니다 — LLM에 맡기지 않습니다.
- **"single-call로 바꾸면 구조가 가벼워지지 않나요?"** →
  LLM 호출 수와 시스템 단계 수는 다릅니다. Semantic Interpreter → Graph Synthesis →
  Deterministic Validator → bounded repair → Compiler → CBBA → Executor로 계층은 그대로
  입니다. two-stage의 이론적 조기 거부 이점은 이번 live stress에서 관측되지 않았습니다.
- **"D-074 gate가 실패했다면서요?"** (자세히 물으면) →
  사전 등록한 gate는 형식적으로 NOT ALL PASS입니다. 유일한 실패는 explicit-reject 기준
  인데, two-stage와 single-call **둘 다** 0/2로 실패했습니다 — 모델이 존재하지 않는 대상을
  그래프로 만들지 않고 안전하게 우회해서 Validator의 reject 경로가 자극되지 않았기
  때문입니다. 즉 두 방식을 **구분하지 못한 non-discriminative test**였습니다. 그래서 gate
  통과로 재해석하지 않고, 판별력 있는 지표에서 열세가 없고 latency가 줄었다는 근거로
  별도의 engineering 결정으로 runtime 기본값을 single-call로 바꿨습니다. two-stage는 평가
  baseline으로 유지합니다.
