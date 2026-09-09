# 발표 수치 출처 (source file / commit)

모든 수치는 아래 파일에서 검증 가능하다. 추정치는 없다.
브랜치: 발표 자산은 `feature/presentation-deck` (= `feature/latency-profiling` D-075 +
`feature/demo-scene-scaleup` 의 `scenarios/demo_grid*.yaml`).

| 슬라이드 · 주장 | 값 | 출처 파일 | commit |
|---|---|---|---|
| S10① P6 그래프 생성 | 9/9 approved · exact-match 9/9 (raw·final) · repair attempted 0/9 · task·edge P/R (macro) 1.00/1.00 · latency mean 13.3s | `data/eval_results/p6_gpt-5-mini.txt` (`.json`) | `a0763b0` (3종 어휘 재실행) |
| S6 / S7 task 어휘 · fleet | AREA_RECON / GROUND_INSPECTION → GROUND_SUPPRESSION · UAV×3 + UGV×2 · `VALIDATOR_VERSION "1.4"` · λ=0.999 | `docs/RESEARCH_CONTRACT.md` §4·§5·§8, `core/enums.py`, `allocation/scoring.py` | 계약 v1.70 |
| S8 / S10② P9 선택적 재할당 | release: no-reset 0 · selective 3 · full-reset 4 · 세 정책 모두 `COMPLETED` · 위반 0 · makespan 413.981 (세 정책 동일) · `suffix_extra_release_count = 0` | `data/eval_results/p9_online_reallocation.txt` (`.json`) | `a0763b0` |
| S10③ / S5 single-call P6 latency | two-stage / single-call 모두 exact 9/9 · repair 0 · latency mean 10.06s → 5.65s (≈ −44%) · LLM calls 2 → 1 | D-072 P6 ablation 요약 (raw artifact 미커밋 — 재생성: `python3 -m evaluation.graph_gen_ablation --set p6 --out data/eval_results/d074_p6`) | 요약은 `docs/DECISIONS.md` D-072/D-075 항목, `2486f49` |
| S10③ Stress-L (industrial_park, 어려운 영어 19) | exact-match 15/16 == 15/16 · first-pass valid two 16 / single 15 · safety-invalid accept 0 · latency mean 10.44s → 6.10s · median 9.37s → 5.12s · **paired median reduction 46% · single faster 95%** · explicit-reject 0/2 == 0/2 → gate NOT ALL PASS | `data/eval_results/d074_linguistic.txt` (`.json`) | `d6c06a5` |
| S10③ Stress-S (stress_grid 15z/4i, 영어 15) | exact-match 12/13 == 12/13 · first-pass valid 13/13 == 13/13 · safety-invalid accept 0 · latency mean 12.48s → 8.59s · median 13.35s → 8.14s · **paired median reduction 29% · single faster 100%** · explicit-reject 0/2 == 0/2 | `data/eval_results/d074_scale.txt` (`.json`) | `d6c06a5` |
| S10③ 채택 결정 (D-075) | pre-registered gate NOT ALL PASS 보존 · explicit-reject는 non-discriminative · 별도 engineering 결정으로 runtime 기본값 single-call · two-stage는 baseline 유지 | `docs/DECISIONS.md` D-075, `docs/RESEARCH_CONTRACT.md` §12 | `2486f49` / `59bc636` |
| 평가 모델 | `gpt-5-mini-2025-08-07` | `d074_*.json` → `modes.*.resolved_models` | `d6c06a5` |
| S9 데모 scene | `demo_grid.yaml` — 15 zone A–O · UAV×3 + UGV×2 · incident-empty · latent seed 2 + min_separation 170 → 화재 zone A/D/J/O | `scenarios/demo_grid.yaml` · `scenarios/demo_grid_latent.yaml` (D-073) | `feature/demo-scene-scaleup` (`b367357`, `a4939f2`) |
| S9 데모 CBBA 분배 (그림 예시) | U1={C,D,F,H,J} · U2={A,B,E,G,I} · U3={K,L,M,N,O} · est. makespan ≈ 300s | `presentation/deck_figures.py`가 `allocation.allocate`로 **실행 시 계산** (커밋된 eval 수치 아님 — 데모 illustration) | — |

## 그림 재생성

```bash
python3 presentation/deck_figures.py        # presentation/fig/*.png
python3 presentation/build_deck_d075.py     # presentation/LLM-MRTA_발표.pptx
```

`presentation/fig/*.png` 는 `.gitignore`(`presentation/*.png`) 대상 — 저장소에 커밋되지
않으며 위 스크립트로 재생성한다. `deck_figures.py` 는 데모 프레임의 좌표·경로·분배를
전부 repo 코드(`allocation.allocate`, `scenarios/demo_grid.yaml`)에서 계산한다.
