# 발표 전 직접 확인할 claim 목록

발표자가 슬라이드/대본에 있는 주장을 **말하기 전에** 스스로 점검. 대부분 이미 repo에서
검증 가능하지만, 표현이 과장으로 흐르기 쉬운 지점을 모았다.

## A. 반드시 확인 (틀리면 발표 신뢰도 손상)

1. **"정형검증(formal verification)"이라는 말을 쓰지 않는다.**
   Validator는 결정론적 invariant 검사이지 정형검증이 아니다. 슬라이드·대본에서
   "deterministic invariant validation" 으로만 부른다. (계약 v1.70 D-075 명시)

2. **P9 선택적 재할당 — "더 빠르다 / 더 좋은 최적해"라고 말하지 않는다.**
   `data/eval_results/p9_online_reallocation.txt`: 세 정책 makespan 413.981 로 **동일**.
   주장은 "불필요한 release 축소 + UAV commitment 보존"뿐. (release 0/3/4)

3. **MP4MR 등과 "우리가 더 우월하다"고 말하지 않는다.**
   동일 조건 비교를 하지 않았다. "다른 reliability 전략" 까지만.

4. **D-074 pre-registered gate 결과를 숨기지 않는다.**
   질문이 나오면: gate는 형식적으로 NOT ALL PASS, 유일한 실패는 explicit-reject 이고
   **두 방식 모두 0/2** 로 실패 → non-discriminative. D-075는 gate 통과로 재해석한 것이
   아니라 별도 engineering 결정. (SCRIPT.md Q&A 참고)

5. **single-call을 main contribution으로 말하지 않는다.**
   "online 응답성을 위한 validated implementation decision / ablation result" 로 배치.
   메인은 ① Validated NL→Graph ② Heterogeneous CBBA ③ Online + Selective Reallocation.

6. **시뮬레이터: "LLM이 생각하는 동안 로봇이 계속 움직인다"고 말하지 않는다.**
   명령은 queue되지만 safe boundary에서의 LLM 처리는 **동기적**. 진짜 비동기는 future work.

7. **반복 순찰 / 지속 감시를 구현했다고 말하지 않는다.**
   agent는 task가 있을 때만 움직이고 임무 사이엔 idle. (계약 §22.7)

## B. 수치를 말하기 전 파일로 재확인

8. P6: `data/eval_results/p6_gpt-5-mini.txt` → 9/9 approved, exact 9/9, repair 0,
   P/R 1.00, latency mean 13.3s, 모델 `gpt-5-mini`.
9. D-072 P6 latency ≈ −44% (10.06→5.65 mean): raw artifact가 repo에 **없다**. 발표에서
   이 수치를 쓰려면 `python3 -m evaluation.graph_gen_ablation --set p6 --out data/eval_results/d074_p6`
   로 재생성해 커밋하거나, "약 44%"를 "약 40%대"로 완화. (요약은 DECISIONS.md D-072.)
10. Stress-L / Stress-S: `data/eval_results/d074_linguistic.txt` / `d074_scale.txt` →
    exact 15/16·12/13 (양쪽 동일), safety-invalid 0, paired median −46%/−29%,
    single faster 95%/100%.
11. 데모 CBBA 분배(U1/U2/U3 = C,D,F,H,J / A,B,E,G,I / K,L,M,N,O, makespan ≈300s):
    이건 `deck_figures.py`가 실행 시 계산하는 **그림 예시**이지 커밋된 평가 수치가 아니다.
    "정확히 5/5/5" 같은 수치를 강조하지 말고 "세 UAV가 각자 지역을 맡는다" 수준으로.

## C. 브랜치 / 재현 관련

12. 발표 자산 브랜치 `feature/presentation-deck` 는 `feature/latency-profiling`(D-071~D-075)
    위에 `feature/demo-scene-scaleup` 의 `scenarios/demo_grid*.yaml` 두 파일만 얹은 상태.
    `main`에는 아직 D-071 이후가 반영되지 않았다 (계약 라벨 재정렬 후 병합 예정).
13. `presentation/LLM-MRTA_발표.pptx` 는 `deck_figures.py` → `build_deck_d075.py` 순서로
    재생성. `presentation/fig/*.png` 는 gitignore 대상.
14. PPTX 발표자 노트가 대본과 동기화되어 있는지 (build_deck_d075.py 수정 시 SCRIPT.md도).
