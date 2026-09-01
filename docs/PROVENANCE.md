# PROVENANCE.md — 이식 코드 등록부

`/home/jiho/LLM_CBBA`(이하 "이전 저장소")에서 재사용하는 모든 코드/패턴을 여기에 기록한다.
가져올 때마다: 원본 경로, 원본 커밋(가능하면 해시), 무엇을 가져왔는지(패턴 vs 내용), 왜
가져왔는지를 적는다. 연구 계약·task 어휘·domain invariant·prompt·scenario·world·결과값은
절대 이 표에 올리지 않는다(가져오지 않기로 결정했으므로).

아직 아무 코드도 이식되지 않았다. P1~P4 구현 중 실제로 포팅하는 시점에 아래 형식으로 항목을
추가한다.

## 항목 형식

```
### <날짜> — <가져온 것 한 줄 요약>

- 원본: `research/<path>` @ `<commit-hash>` (LLM_CBBA)
- 종류: 패턴만 / 구조만 / 직접 포팅 후 수정
- 이유: <왜 이걸 재사용하는가 — 알고리즘적으로 도메인 무관함을 설명>
- 수정한 부분: <이식하면서 바꾼 것, 있다면>
- 가져오지 않은 부분: <원본에 있지만 의도적으로 안 가져온 것>
```

## 예정된 이식 후보 (아직 미실행)

- `allocation/cbba.py`의 consensus/bundle 핵심, 보상형태(우선순위×이동시간 할인) — 알고리즘
  자체가 도메인 무관.
- `mission/graph.py`의 TaskGraph 연산 패턴(cycle 검사, predecessor/successor 조회) — 도메인
  무관 자료구조.
- `execution/sim_executor.py`의 event-loop 구조 — 단, `execution/mission_runner.py`의
  premature-deadlock 버그(§14 RESEARCH_CONTRACT.md 참고)는 패턴만 배우고 고친 형태로 새로
  작성. 옛 코드를 그대로 복사하지 않는다.
- `mission/loader.py`의 environment/reference 분리 원칙(fleet+landmark 어휘만 담는 파일과,
  그 위에 task 인스턴스를 얹는 별도 파일을 분리) — 재현 가능한 오프라인 테스트를 위한 검증된
  설계 패턴.
- `llm/backends.py`의 structured-output 호출 래퍼 — 백엔드 추상화 자체는 도메인 무관.
- 도메인 독립 테스트 유틸리티(mock LLM 응답 주입 패턴 등).

## 명시적으로 가져오지 않는 것

이전 연구 계약(SPEC/CLAUDE/AGENTS/ROADMAP/DECISIONS의 내용), earthquake/vehicle-inspection/
fire-patrol의 task enum, `UAV` 중심 dataclass(PX4 전용 필드 포함), fire-patrol Validator
invariant의 구체적 규칙, 기존 prompt 문구, 기존 scenario/world 파일, 기존 실험 결과값(골든값),
기존 테스트 파일의 내용(교훈만 배우고 새로 작성).
