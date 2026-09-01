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
2. `docs/DECISIONS.md`에서 최신 항목 확인 (현재 D-006, 계약 v1.5)
3. `docs/PROVENANCE.md`에서 지금까지 이식된 코드가 있는지 확인
4. `README.md`의 "현재 단계" 확인

## 지금 어디까지 왔는지 (2026-09-01 기준)

**P1 승인 완료(Codex). 계약 v1.4 (D-005).** `core/`(enums, Agent, Task, TaskGraph,
RouteGraph), `scenarios/`(scene loader, `compile_reference_graph`, reference fixture)까지
구현, §15 P1 게이트 5개 + Codex 반례 전부 통과(pytest 57개, `python3 -m pytest -q`). D-005는
P2 착수 전 선행 계약 수정이며 코드 변경은 없다. 다음: **P2**(deterministic whole-graph
Validator + MissionPatch reconciliation, §9/§10).

P2 착수 시 주의:
- §9 invariant 14개 전부 구현. **매 patch마다 최종 후보 graph 전체를 처음부터 재검증**(§9
  멀티 트랜잭션 우회 방지). patch 거부 시 원본 완전 보존(트랜잭션).
- raw LLM candidate / raw MissionPatch는 **list 표현으로 받아 검증 후에만 graph화**한다
  (D-003, D-005). candidate는 Validator가 E_UNKNOWN_REF/E_DUPLICATE_EDGE 등을, patch는
  §10 2단계가 `E_PATCH_CONFLICT`(중복 op, 같은 edge Add+Remove 등)를 판정. 그 다음
  canonical 순서 `AddTask → RemoveEdge → AddEdge`로 적용 — 순서 독립성은 diff가 아니라 이
  검증+canonical 적용이 보장한다.
- `compile_reference_graph`는 신뢰된(검증 통과) 목록만 받으므로 candidate 검증 용도로 쓰지
  않는다(계약 §7).
- frontier 계산은 COMPLETED predecessor만 "충족"으로 취급(§10 6단계). CANCELLED predecessor
  의미는 P4 전에 확정.
- `TaskGraph.reference_errors()`/`has_cycle()`는 P1의 경량 구조 검사일 뿐 P2 Validator가
  아니다.

RQ1(LLM 복합 task graph 생성)과 RQ2(이종 UAV/UGV CBBA 할당)가 필수 범위다. RQ3(선택적
재할당)는 P8 후속이며, 구현되기 전까지는 어디에도 "동적 재할당"을 완료된 결과로 쓰지 않는다.

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
- RQ3 관련 기능을 P0~P7 완료 전에 구현하거나, 구현 안 됐는데 구현된 것처럼 서술하기
- 실행하지 않은 실험 수치를 문서/주석에 넣기
