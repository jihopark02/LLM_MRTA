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
2. `docs/DECISIONS.md`에서 최신 항목 확인 (현재 D-018, 계약 v1.17)
3. `docs/PROVENANCE.md`에서 지금까지 이식된 코드가 있는지 확인
4. `README.md`의 "현재 단계" 확인

## 지금 어디까지 왔는지 (2026-09-01 기준)

**P1~P5 구현 완료(P1~P4 승인, P5 Codex 검토 대기). 계약 v1.17 (D-018).** `validator/`(P2) +
`allocation/`(P3) + `execution/`(P4) + `llm/`(P5). `VALIDATOR_VERSION = "1.2"`, `λ = 0.999`.
pytest 185개 통과, ruff clean.

workflow: `THERMAL_RECON → SUPPRESSANT_DROP → GROUND_INSPECTION → GROUND_SUPPRESSION`
(D-016, symbolic UGV 진압). 골든값 P3 makespan ~359.8 / P4 ~257.9, violation 0.

P5 구조:
- `llm/schemas.py`: `Step1Output`/`Step2Output`/`RepairOutput` (pydantic).
- `llm/backend.py`: `LLMBackend` Protocol, `MockBackend`(게이트용), `OpenAIBackend`
  (`chat.completions.parse`, `OPENAI_API_KEY`, `openai` 지연 import — `llm` extra, D-018).
  실제 평가 모델은 실험 전에 pin(§14).
- `llm/prompts.py`: scene 어휘 주입 Step1/Step2/repair 프롬프트.
- `llm/pipeline.py` `generate_mission`: Step1 → `from_raw` schema(오류 즉시 거부) → Step2 →
  `validate_candidate` → repair 1회 → 재검증 → 승인(+compiled graph) / 명시적 거부. reference
  fallback 없음. `GenerationResult`가 §12 지표.

다음: **P6**(최소 9개 입력 평가 + 시각화). `OpenAIBackend`로 실제 평가, MockBackend는
파이프라인 self-test. reference annotation 사전 고정.

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
- **D-006**: reconciliation release 경로는 P2에서 단위테스트만, end-to-end는 RQ3(P8)까지 도달
  안 함. #13 terminal incoming 불변은 P2에서 도달.
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
