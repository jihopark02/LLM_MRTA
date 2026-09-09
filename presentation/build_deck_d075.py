"""Build the 12-minute undergraduate-session deck (contract v1.70 / D-075).

Rebuilt from scratch — the older build_deck.py is D-055 content. Every number
is traceable (see presentation/SOURCES.md); nothing is estimated.

    python3 presentation/deck_figures.py       # first: regenerate presentation/fig/*.png
    python3 presentation/build_deck_d075.py    # -> presentation/LLM-MRTA_발표.pptx
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "fig"

INK = RGBColor(0x1B, 0x1B, 0x2B)
MUTED = RGBColor(0x6C, 0x72, 0x80)
LLM = RGBColor(0xD9, 0x81, 0x2F)       # LLM generates — probabilistic
LLM_BG = RGBColor(0xFB, 0xEC, 0xDA)
DET = RGBColor(0x0E, 0x7C, 0x7B)       # deterministic code decides — reproducible
DET_BG = RGBColor(0xDD, 0xEF, 0xEE)
CREAM = RGBColor(0xFA, 0xF8, 0xF3)
RED = RGBColor(0xC5, 0x34, 0x2B)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = CREAM
    bg.line.fill.background()
    bg.shadow.inherit = False
    s.shapes._spTree.remove(bg._element)
    s.shapes._spTree.insert(2, bg._element)
    return s


def tb(s, x, y, w, h, runs, *, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT,
       anchor=MSO_ANCHOR.TOP, leading=1.12):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    if isinstance(runs, str):
        runs = [runs]
    for i, item in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = leading
        p.space_after = Pt(4)
        segs = item if isinstance(item, list) else [(item, {})]
        for text, style in segs:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(style.get("size", size))
            r.font.bold = style.get("bold", bold)
            r.font.color.rgb = style.get("color", color)
            r.font.name = "Segoe UI"
    return box


def heading(s, kicker, title):
    tb(s, 0.62, 0.42, 12, 0.4, kicker, size=12.5, color=DET, bold=True)
    tb(s, 0.6, 0.78, 12.1, 1.0, title, size=27, color=INK, bold=True)
    ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(0.62), Inches(1.72),
                                Inches(12.7), Inches(1.72))
    ln.line.color.rgb = INK
    ln.line.width = Pt(1.6)


def box(s, x, y, w, h, text, *, kind="det", size=12.5):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                             Inches(w), Inches(h))
    shp.adjustments[0] = 0.12
    shp.fill.solid()
    shp.fill.fore_color.rgb = LLM_BG if kind == "llm" else (
        DET_BG if kind == "det" else CREAM)
    shp.line.color.rgb = LLM if kind == "llm" else (DET if kind == "det" else MUTED)
    shp.line.width = Pt(1.6)
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.06)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.05
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = INK
    r.font.name = "Segoe UI"
    return shp


def arrow(s, x1, y1, x2, y2, *, color=INK, w=1.8, dashed=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                               Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(w)
    le = c.line._get_or_add_ln()
    from pptx.oxml.ns import qn
    if dashed:
        d = le.makeelement(qn("a:prstDash"), {"val": "dash"})
        le.append(d)
    tail = le.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    le.append(tail)
    return c


def pic(s, name, x, y, w=None, h=None):
    kw = {}
    if w:
        kw["width"] = Inches(w)
    if h:
        kw["height"] = Inches(h)
    return s.shapes.add_picture(str(FIG / name), Inches(x), Inches(y), **kw)


def note(s, text):
    s.notes_slide.notes_text_frame.text = text


# ============================================================ 1 · Title
s = slide()
tb(s, 0.95, 1.25, 11.9, 2.0,
   "자연어 지시로 이종 UAV·UGV 재난 임무를\n계획·수정하는 검증형 다중로봇 할당 시스템",
   size=27, bold=True, color=INK, leading=1.22)
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.98), Inches(3.35),
                         Inches(3.4), Inches(0.055))
bar.fill.solid(); bar.fill.fore_color.rgb = DET; bar.line.fill.background()
bar.shadow.inherit = False
tb(s, 0.98, 3.6, 11.7, 0.9,
   "자연어 → 검증된 task graph → CBBA 할당 · 실행 중 자연어 수정에는 선택적 재할당",
   size=15, color=MUTED)
kb = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.98), Inches(4.75),
                        Inches(11.5), Inches(1.15))
kb.adjustments[0] = 0.12
kb.fill.solid(); kb.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
kb.line.color.rgb = DET; kb.line.width = Pt(1.4); kb.shadow.inherit = False
tb(s, 1.25, 4.9, 11.0, 1.0, [[
   ("핵심: ", {"bold": True, "color": INK}),
   ("LLM은 ", {}), ("의도와 mission graph 후보", {"color": LLM, "bold": True}),
   ("를 생성하고, ", {}),
   ("결정론적 계층이 실행 의미와 안전을 결정", {"color": DET, "bold": True}),
   ("하며, CBBA가 누가 수행할지를 정한다.", {})]], size=15)
tb(s, 0.98, 6.35, 11.7, 0.6,
   "학부 학술대회 발표  ·  LLM_MRTA  ·  평가 모델 gpt-5-mini-2025-08-07",
   size=11.5, color=MUTED)
note(s,
     "[목표 0:45] 제목만 읽지 말고 한 문장으로 시스템을 규정합니다. "
     "'재난 대응에서 사람이 자연어로 다중 UAV·UGV 임무를 주면, 시스템이 그것을 "
     "검증된 실행 계획으로 바꾸고 CBBA로 로봇에 배정하며, 실행 중 자연어로 임무를 "
     "고치면 영향받은 부분만 다시 배정합니다.' "
     "이 발표의 목표는 기능 나열이 아니라, 왜 LLM과 결정론적 계획/검증을 분리했고 "
     "그것이 온라인 다중로봇 재계획으로 어떻게 이어지는지를 12분 안에 설득하는 것입니다. "
     "화면 아래 한 문장(LLM=주황, 결정론=청록)이 발표 전체의 척추입니다.")

# ================================================= 2 · Background
s = slide()
heading(s, "01  BACKGROUND & MOTIVATION", "사람이 task를 정의·배정하는 부담, 그리고 LLM의 함정")
tb(s, 0.7, 2.1, 6.0, 4.6, [
   [("재난 다중로봇 대응", {"bold": True, "size": 15, "color": INK})],
   [("· 운용자가 정찰·점검·진압 task를 일일이 정의", {"size": 13})],
   [("· 어느 로봇이 무엇을 언제 할지 수동 배정 → 느리고 실수 유발", {"size": 13})],
   [("· 상황은 실행 중에 계속 바뀐다 (새 화재, 자원 변경)", {"size": 13})],
   [(" ", {"size": 8})],
   [("자연어로 임무를 주면?", {"bold": True, "size": 15, "color": LLM})],
   [("· 빠르고 유연하다 — 사람이 목표만 말하면 된다", {"size": 13})],
], leading=1.25)
tb(s, 7.0, 2.1, 5.8, 4.6, [
   [("하지만 LLM 출력은", {"bold": True, "size": 15, "color": RED})],
   [("· 비결정적 — 같은 입력에 다른 계획", {"size": 13})],
   [("· 존재하지 않는 구역·화재를 지시할 수 있다", {"size": 13})],
   [("· 선후관계·로봇 능력·도달성을 보장하지 않는다", {"size": 13})],
   [(" ", {"size": 8})],
   [("→ LLM을 로봇 제어에 바로 연결하는 것은 위험하다", {"bold": True, "size": 14, "color": INK})],
], leading=1.25)
note(s,
     "[목표 1:15] 두 축을 세웁니다. 첫째, 재난 대응에서 사람이 task를 정의하고 로봇에 "
     "배정하는 것은 부담이고 상황은 계속 바뀝니다. 둘째, 자연어 mission planning은 매력적이지만 "
     "LLM 출력은 비결정적이고 실행 가능성을 보장하지 않습니다. 존재하지 않는 대상, 잘못된 "
     "선후관계, 로봇 능력과 맞지 않는 지시가 나올 수 있습니다. 그래서 LLM 출력을 그대로 "
     "로봇 명령으로 쓰면 안 됩니다. 이 슬라이드의 결론 한 줄만 청중이 가져가면 됩니다: "
     "'LLM을 robot control에 바로 연결하는 것은 위험하다.' 다음 슬라이드에서 기존 연구가 "
     "이 문제를 어떻게 다뤘는지 봅니다.")

# ================================================= 3 · Related work
s = slide()
heading(s, "02  RELATED WORK", "다단계 LLM으로 신뢰성을 얻는 접근 vs. 실행 가능성을 제한하는 접근")
box(s, 0.8, 2.4, 5.4, 1.0, "기존: 범용 LLM mission generation\n(예: MP4MR — J. ICROS 2025)", kind="llm", size=12.5)
tb(s, 0.8, 3.7, 5.4, 3.2, [
   [("· 여러 LLM actor가 임무 해석 → task 분해 → 실행 primitive → 명세", {"size": 12})],
   [("· LLM critic이 논리·실행성·형식을 다시 검토", {"size": 12})],
   [("· 표현력은 넓지만 inference 비용이 크고 출력은 여전히 확률적", {"size": 12})],
], leading=1.3)
box(s, 7.1, 2.4, 5.4, 1.0, "본 연구: 제한된 어휘 + 결정론적 검증\n+ 온라인 MRTA", kind="det", size=12.5)
tb(s, 7.1, 3.7, 5.4, 3.2, [
   [("· 실행 가능한 task 어휘를 3종으로 고정", {"size": 12})],
   [("· LLM 출력을 독립적인 결정론적 invariant 검증에 통과시킴", {"size": 12})],
   [("· 실행 중 자연어 수정 → 선택적 재할당", {"size": 12})],
   [(" ", {"size": 6})],
   [("→ '더 우월하다'가 아니라 다른 reliability 전략이다", {"size": 12.5, "bold": True, "color": INK})],
], leading=1.3)
note(s,
     "[목표 1:00] 짧게 갑니다. 기존 LLM mission planning 연구, 대표적으로 우리가 구조적으로 "
     "참고한 MP4MR는 여러 LLM actor와 critic을 이용한 범용 mission generation 접근입니다. "
     "표현력은 넓지만 inference 비용이 크고 출력은 여전히 확률적입니다. "
     "우리는 다른 전략을 택했습니다. 실행 가능한 task 어휘를 제한하고, LLM 출력을 별도의 "
     "결정론적 invariant 검증으로 보장하며, 그 위에서 온라인 다중로봇 재할당을 합니다. "
     "직접 성능 비교는 하지 않았고 우월하다고 주장하지 않습니다 — 신뢰성을 확보하는 "
     "전략이 다를 뿐입니다. 이 점을 분명히 하고 넘어갑니다.")

# ================================================= 4 · Core idea
s = slide()
heading(s, "03  CORE IDEA", "핵심 아이디어 — 생성·검증·배정의 역할 분리")
q = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(2.15),
                       Inches(11.5), Inches(1.9))
q.adjustments[0] = 0.08
q.fill.solid(); q.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
q.line.color.rgb = DET; q.line.width = Pt(1.8); q.shadow.inherit = False
tf = q.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
tf.margin_left = tf.margin_right = Inches(0.35)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT; p.line_spacing = 1.3
for text, st in [
    ("LLM은 ", {}), ("operator의 semantic intent와 mission graph 후보", {"color": LLM, "bold": True}),
    ("를 생성하고,\n", {}),
    ("결정론적 계층이 정확한 실행 의미와 안전성", {"color": DET, "bold": True}),
    ("을 결정하며,\n", {}),
    ("CBBA가 ", {}), ("누가 수행할지", {"bold": True, "color": INK}), ("를 결정한다.", {})]:
    r = p.add_run(); r.text = text; r.font.size = Pt(17)
    r.font.bold = st.get("bold", False)
    r.font.color.rgb = st.get("color", INK); r.font.name = "Segoe UI"
for i, (t, sub) in enumerate([
    ("Validated NL → Mission Graph", "자연어를 검증된 실행 그래프로"),
    ("Heterogeneous CBBA Allocation", "능력·이동비용 기반 분산 배정"),
    ("Online Update + Selective Reallocation", "실행 중 수정 → 영향받은 부분만 재배정")]):
    x = 0.9 + i * 4.0
    box(s, x, 4.6, 3.7, 0.7, t, kind="det", size=11.5)
    tb(s, x, 5.4, 3.7, 0.9, sub, size=10.5, color=MUTED, align=PP_ALIGN.CENTER)
note(s,
     "[목표 1:00] 이 슬라이드의 문장이 발표 전체의 중심입니다. 천천히 읽습니다: "
     "'LLM은 operator의 semantic intent와 mission graph candidate를 생성하고, "
     "deterministic layer가 정확한 실행 의미와 안전성을 결정하며, CBBA가 누가 수행할지를 "
     "결정한다.' 세 개의 기둥이 있습니다 — 검증된 자연어-그래프 변환, 이종 CBBA 할당, "
     "온라인 수정과 선택적 재할당. 나머지 발표는 이 셋을 하나씩 보여줍니다. "
     "single-call, latency, UI 같은 것은 이 셋을 뒷받침하는 하위 결과입니다.")

# ================================================= 5 · Architecture  ★
s = slide()
heading(s, "04  SYSTEM ARCHITECTURE", "생성(LLM) → 결정론적 검증 → 배정 → 실행, 그리고 실행 중 온라인 루프")
GAP = 0.24
BW = 0.98    # box height


def flow(y, label, steps, *, x0=1.55):
    tb(s, 0.3, y + 0.06, 1.2, 0.9, label, size=10, color=MUTED, bold=True,
       anchor=MSO_ANCHOR.MIDDLE, leading=1.05)
    x = x0
    centers = []
    for i, (t, k, w) in enumerate(steps):
        box(s, x, y, w, BW, t, kind=k, size=9)
        centers.append((x, x + w))
        if i < len(steps) - 1:
            arrow(s, x + w + 0.02, y + BW / 2, x + w + GAP - 0.02, y + BW / 2, w=1.4)
        x += w + GAP
    return centers


row1 = 2.05
c1 = flow(row1, "임무\n생성", [
    ("Operator\n자연어", "plain", 1.15),
    ("Semantic\nInterpreter\n(LLM)", "llm", 1.4),
    ("Structured\nGraph Synthesis\n(LLM · 1 call)", "llm", 1.75),
    ("Deterministic\nInvariant\nValidator", "det", 1.65),
    ("Compiler /\nGrounding", "det", 1.35),
    ("CBBA\nAllocation", "det", 1.3),
    ("Checkpoint\nExecutor", "det", 1.35),
])
# repair loop under the Validator (index 3)
vx0, vx1 = c1[3]
vcx = (vx0 + vx1) / 2
box(s, vcx - 1.0, row1 + 1.75, 2.0, 0.58, "bounded Repair  ( ≤ 1 )", kind="llm", size=9.5)
arrow(s, vcx, row1 + BW + 0.02, vcx, row1 + 1.73, dashed=True, w=1.3)
arrow(s, vcx - 1.0, row1 + 2.04, vcx - 1.5, row1 + 2.04, dashed=True, w=1.3)
arrow(s, vcx - 1.5, row1 + 2.04, vcx - 1.5, row1 + BW + 0.02, dashed=True, w=1.3)
tb(s, vcx + 1.2, row1 + 1.82, 3.0, 0.45,
   "invalid → 고쳐서 재검증\nvalid → 그대로 진행", size=8.5, color=MUTED, leading=1.1)

row2 = 4.95
c2 = flow(row2, "실행 중\n온라인", [
    ("새 자연어 명령 /\n감지된 화재", "plain", 1.7),
    ("Semantic\nInterpreter (LLM)", "llm", 1.75),
    ("Deterministic\npatch + grounding", "det", 1.9),
    ("affected\nassignments\nreleased", "det", 1.65),
    ("Selective CBBA\nreallocation", "det", 1.8),
])
# online loop rejoins the executor
ex0, ex1 = c1[6]
sr0, sr1 = c2[4]
srcx = (sr0 + sr1) / 2
excx = (ex0 + ex1) / 2
arrow(s, srcx, row2 - 0.02, srcx, row2 - 0.5, color=DET, w=1.5)
arrow(s, srcx, row2 - 0.5, excx, row2 - 0.5, color=DET, w=1.5)
arrow(s, excx, row2 - 0.5, excx, row1 + BW + 0.02, color=DET, w=1.5)
tb(s, srcx - 2.1, row2 + BW + 0.06, 4.2, 0.4,
   "→ Executor의 다음 safe checkpoint에서 반영", size=8.5, color=DET,
   align=PP_ALIGN.CENTER)

# legend — real swatches
for i, (c, txt) in enumerate([(LLM, "LLM — 확률적, 재시도 가능"),
                              (DET, "결정론적 코드 — 재현 가능, 해시 감사")]):
    sw = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.62 + i * 4.7), Inches(6.95),
                            Inches(0.22), Inches(0.22))
    sw.fill.solid(); sw.fill.fore_color.rgb = c; sw.line.fill.background()
    sw.shadow.inherit = False
    tb(s, 0.92 + i * 4.7, 6.9, 4.2, 0.4, txt, size=10, color=MUTED)
note(s,
     "[목표 2:00 — 가장 중요] 이 그림이 발표의 뼈대입니다. 위 줄은 임무 생성입니다. "
     "운용자 자연어가 들어오면 Semantic Interpreter가 의도와 슬롯을 뽑고, "
     "Structured Graph Synthesis가 task와 의존관계를 한 번의 구조화 호출로 만듭니다. "
     "그 후보는 반드시 Deterministic Invariant Validator를 통과해야 합니다 — "
     "스키마·참조, DAG·사이클, workflow 선후관계, 로봇 능력, 도달성을 검사합니다. "
     "검증에 실패하면 최대 한 번 bounded repair로 고쳐 다시 검증하고, 통과하면 "
     "Compiler가 실행 그래프로 grounding한 뒤 CBBA가 배정하고 Checkpoint Executor가 실행합니다. "
     "아래 줄은 실행 중입니다. 새 자연어 명령이나 감지된 화재가 들어오면 같은 Semantic "
     "Interpreter를 거쳐 결정론적 patch와 grounding을 만들고, 영향받은 미시작 배정만 "
     "release한 뒤 선택적으로 CBBA 재할당을 하며, 이는 Executor의 다음 안전한 checkpoint에서 "
     "반영됩니다. 여기서 강조할 점: LLM은 semantic reasoning에만 쓰이고, 실행 가능성과 "
     "안전성은 별도의 결정론적 계층이 보장합니다. LLM 호출 횟수 자체는 중요한 이야기가 "
     "아닙니다 — 뒤 latency 슬라이드에서 다룹니다.")

# ================================================= 6 · NL -> graph
s = slide()
heading(s, "05  NATURAL LANGUAGE → VALIDATED MISSION GRAPH", "LLM 후보를 결정론적 invariant 검증에 통과시킨다")
pic(s, "graph_example.png", 0.55, 1.95, w=8.2)
tb(s, 9.0, 2.0, 4.0, 5.2, [
   [("Task 어휘 (3종)", {"bold": True, "size": 13, "color": INK})],
   [("AREA_RECON — UAV, 구역 항공 정찰", {"size": 11})],
   [("GROUND_INSPECTION → GROUND_SUPPRESSION", {"size": 11})],
   [("  UGV, incident 지상 점검 후 진압", {"size": 10.5, "color": MUTED})],
   [(" ", {"size": 8})],
   [("Validator가 확인 (deterministic invariant)", {"bold": True, "size": 13, "color": DET})],
   [("· schema / reference 존재성", {"size": 11})],
   [("· DAG · cycle 없음", {"size": 11})],
   [("· workflow 선후관계", {"size": 11})],
   [("· platform capability", {"size": 11})],
   [("· reachability / feasibility", {"size": 11})],
   [(" ", {"size": 8})],
   [("LLM이 만들지 않는 것", {"bold": True, "size": 12, "color": LLM})],
   [("좌표 · priority · capability · agent 선택 · 할당", {"size": 10.5, "color": MUTED})],
], leading=1.22)
note(s,
     "[목표 1:15] 구체적인 예를 봅니다. 운용자가 '구역 A, D, G를 정찰하고 FIRE_SITE_1은 "
     "지상 진압까지 대응해줘'라고 하면, LLM은 task 목록과 의존관계 후보를 냅니다 — "
     "세 개의 독립적인 AREA_RECON과, GROUND_INSPECTION에서 GROUND_SUPPRESSION으로 이어지는 "
     "체인입니다. task 어휘는 세 종류뿐입니다. 그다음 이 후보가 결정론적 Validator를 "
     "통과해야 합니다: 참조가 실제 존재하는지, 사이클이 없는지, workflow 선후관계가 맞는지, "
     "로봇 능력에 맞는지, 도달 가능한지. 이건 결정론적 invariant 검사이지 정형검증(formal "
     "verification)이 아닙니다. 그리고 중요한 것 — LLM은 좌표, 우선순위, 능력, 어느 로봇이 "
     "할지, 할당을 만들지 않습니다. 그건 전부 결정론적 계층의 몫입니다.")

# ================================================= 7 · CBBA
s = slide()
heading(s, "06  HETEROGENEOUS CBBA ALLOCATION", "검증된 task를 능력·이동비용에 따라 로봇에 분산 배정")
pic(s, "demo_1_world.png", 0.5, 1.95, w=7.6)
tb(s, 8.3, 2.1, 4.6, 5.0, [
   [("이종 fleet", {"bold": True, "size": 13, "color": INK})],
   [("3 × UAV — 항공 정찰, 직선 이동", {"size": 11.5})],
   [("2 × UGV — 지상 점검·진압, 도로망 이동", {"size": 11.5})],
   [(" ", {"size": 8})],
   [("CBBA (consensus-based bundle auction)", {"bold": True, "size": 13, "color": DET})],
   [("· 각 로봇이 능력에 맞는 task에만 입찰", {"size": 11.5})],
   [("· 이동비용 + 우선순위로 bundle 구성", {"size": 11.5})],
   [("· READY 프론티어를 따라가며 재입찰 (rolling)", {"size": 11.5})],
   [(" ", {"size": 8})],
   [("이동 모델이 그림에서 드러난다", {"size": 11, "color": MUTED})],
   [("UAV = Euclidean,  UGV = route-graph 최단경로", {"size": 10.5, "color": MUTED})],
], leading=1.24)
note(s,
     "[목표 1:00] 할당은 CBBA로 합니다. fleet은 이종입니다 — 동일한 UAV 3대는 항공 정찰을 "
     "직선으로 하고, UGV 2대는 지상 점검·진압을 도로망을 따라 합니다. CBBA에서는 각 로봇이 "
     "자기 능력에 맞는 task에만 입찰하고, 이동비용과 우선순위로 bundle을 구성하며, task가 "
     "완료될 때마다 READY가 된 다음 task를 다시 입찰합니다. 수식은 넘어갑니다 — 핵심은 "
     "검증된 task가 로봇 능력과 이동비용을 고려해 분산 배정된다는 것, 그리고 그 이종 "
     "이동 모델이 다음 데모 그림에서 눈에 보인다는 것입니다.")

# ================================================= 8 · Online reallocation  ★
s = slide()
heading(s, "07  ONLINE INTERACTION & SELECTIVE REALLOCATION", "실행 중 수정 → 처음부터 재계획하지 않고 영향받은 부분만")
pic(s, "realloc_before_after.png", 0.5, 1.95, w=7.7)
tb(s, 8.4, 2.05, 4.5, 2.7, [
   [("흐름", {"bold": True, "size": 13, "color": INK})],
   [("semantic update → 결정론적 patch\n→ 영향받은 배정 release → CBBA 재할당", {"size": 11})],
], leading=1.3)
tb(s, 8.4, 4.35, 4.6, 3.0, [
   [("대표 fixture 결과 (P9)", {"bold": True, "size": 13, "color": DET})],
   [("release 수:  no-reset 0  ·  선택적 3  ·  full-reset 4", {"size": 11})],
   [("세 정책 모두 COMPLETED · 위반 0 · makespan 동일", {"size": 11})],
   [(" ", {"size": 6})],
   [("주장: 불필요한 release를 줄이고 기존 UAV commitment를", {"size": 10.5, "color": MUTED})],
   [("보존한다.  '더 빠르다 / 더 좋은 최적해'는 주장하지 않는다.", {"size": 10.5, "color": MUTED})],
], leading=1.25)
note(s,
     "[목표 1:45 — 메인 기여] 실행 중에 새 incident가 감지되거나 운용자가 새 명령을 주면, "
     "전체 임무를 처음부터 다시 계획하지 않습니다. 자연어를 semantic update로 해석하고, "
     "결정론적으로 patch와 grounding을 만들고, 영향받은 미시작 배정만 release한 뒤 CBBA로 "
     "다시 입찰합니다. 왼쪽 그림 — full reset은 모든 배정을 풀어버립니다. 오른쪽 — 선택적 "
     "release는 새로 생긴 지상 대응만 풀고 UAV 정찰 bundle은 그대로 둡니다. "
     "대표 fixture에서 release 수는 no-reset 0, 선택적 3, full-reset 4였고, 세 정책 모두 "
     "임무를 완주했으며 위반이 없고 makespan이 동일했습니다. 그래서 우리 주장은 딱 하나입니다 "
     "— 선택적 재할당이 불필요한 release를 줄이고 진행 중인 UAV commitment를 보존한다. "
     "더 빠른 경로나 더 좋은 최적해를 찾는다고 주장하지 않습니다. makespan이 같으니까요.")

# ================================================= 9 · Demo flow  ★
s = slide()
heading(s, "08  SIMULATOR — DEMO FLOW", "World → 임무 → 할당 → 실행 → 화재 발견 → 선택적 재할당")
xs = [0.34, 4.62, 8.90]
ys = [1.98, 4.48]
frames = ["demo_1_world.png", "demo_2_mission.png", "demo_3_alloc.png",
          "demo_4_exec.png", "demo_5_incident.png", "demo_6_reselect.png"]
for idx, name in enumerate(frames):
    pic(s, name, xs[idx % 3], ys[idx // 3], w=4.28)
note(s,
     "[목표 1:30] 15구역 데모로 전체 흐름을 봅니다. 1) 임무 전에도 world가 보입니다 — "
     "15개 구역 A부터 O, UGV 도로망, depot의 로봇 5대. 2) '모든 구역을 항공 정찰해줘' → "
     "15개 AREA_RECON, 의존관계 0, 검증 통과. 3) CBBA가 세 UAV에 지역별로 분산 — 화면에 "
     "각 UAV의 담당 구역이 색으로 보입니다. 4) checkpoint 기반 실행, task 사이의 안전한 "
     "경계에서 멈출 수 있습니다. 5) 구역 J 정찰이 끝나면 숨어 있던 화재가 드러납니다 — "
     "나머지 화재는 아직 안 보입니다. 화재 감지는 운용자 승인 게이트를 거칩니다. "
     "6) 새 지상 대응만 입찰됩니다 — G1이 J로 가고, UAV 정찰 배정은 그대로입니다. "
     "이게 앞 슬라이드의 선택적 재할당이 실제로 화면에서 어떻게 보이는지입니다.")

# ================================================= 10 · Evaluation
s = slide()
heading(s, "09  EVALUATION — KEY RESULTS", "연구 주장과 직접 연결되는 세 축만")
cards = [
    ("① 그래프 생성 + 결정론적 검증", DET, [
        "P6 (9개 명령, gpt-5-mini)",
        "9/9 approved · exact-match 9/9 · repair 0",
        "task/edge precision·recall 1.00",
    ]),
    ("② 온라인 선택적 재할당", DET, [
        "release  no-reset 0 · 선택적 3 · full-reset 4",
        "세 정책 모두 COMPLETED · 위반 0",
        "makespan 동일 — release 범위만 축소",
    ]),
    ("③ single-call latency ablation (사전 등록 A/B)", LLM, [
        "P6: two-stage·single-call 모두 exact 9/9,  ~44% 빠름",
        "Stress-L / Stress-S: exact-match 동일 (15/16, 12/13)",
        "paired median latency  −46%  /  −29%",
    ]),
]
for i, (title, col, lines) in enumerate(cards):
    y = 2.0 + i * 1.72
    barc = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.7), Inches(y),
                              Inches(12.0), Inches(1.5))
    barc.adjustments[0] = 0.08
    barc.fill.solid(); barc.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    barc.line.color.rgb = col; barc.line.width = Pt(1.4); barc.shadow.inherit = False
    tb(s, 0.95, y + 0.1, 11.6, 0.4, title, size=12.5, bold=True, color=INK)
    tb(s, 0.95, y + 0.5, 11.6, 1.0,
       [[(ln, {"size": 10.5, "color": MUTED})] for ln in lines], leading=1.15)
tb(s, 0.7, 7.05, 12.2, 0.4,
   "single-call은 main contribution이 아니라 online 응답성을 위한 구현 결정이다.",
   size=10.5, color=INK, bold=True)
note(s,
     "[목표 1:30] 세 축만 봅니다. 첫째, 그래프 생성과 검증. gpt-5-mini로 9개 명령을 돌렸고 "
     "9/9가 승인, exact-match 9/9, repair는 한 번도 필요 없었고 task·edge 정확도는 1.00입니다. "
     "둘째, 온라인 선택적 재할당. release 수 0/3/4, 세 정책 모두 완주, 위반 0, makespan 동일 — "
     "즉 release 범위만 줄인다는 주장입니다. 셋째, single-call latency ablation. 원래 우리는 "
     "task 생성과 의존관계 생성을 두 번의 LLM 호출로 나눴는데, 이걸 한 번의 구조화 호출로 "
     "통합해 비교했습니다. clean 세트에서 두 방식 모두 9/9 exact이고 single-call이 약 44% "
     "빨랐습니다. 결과 보기 전에 고정한 어려운 영어 명령 세트와 15구역 규모 세트에서도 "
     "exact-match는 동일했고 명령별 median latency가 각각 46%, 29% 줄었습니다. "
     "[SPEAKER NOTE — 슬라이드에는 넣지 않음] 사전 등록한 D-074 gate는 형식적으로 "
     "NOT ALL PASS였습니다. 유일한 실패는 explicit-reject 기준인데, 두 방식 모두 0/2로 "
     "실패했습니다 — 모델이 존재하지 않는 대상을 그래프로 만들지 않고 안전하게 우회해서 "
     "Validator의 reject 경로가 자극되지 않았기 때문입니다. 즉 이 기준은 두 generator를 "
     "구분하지 못한 non-discriminative test였습니다. 그래서 gate 통과로 재해석하지 않고, "
     "판별력 있는 지표에서 열세가 없고 latency가 줄었다는 근거로 D-075에서 별도의 "
     "engineering 결정으로 runtime 기본값을 single-call로 바꿨습니다. two-stage는 평가 "
     "baseline으로 유지합니다. 질문이 나오면 이렇게 답하세요.")

# ================================================= 11 · Conclusion
s = slide()
heading(s, "10  CONCLUSION & LIMITATIONS", "세 문장으로")
for i, t in enumerate([
    "① 자연어 임무를 실행 가능한 task graph로 변환한다.",
    "② deterministic invariant validation + CBBA로 안전하고 재현 가능한 할당을 만든다.",
    "③ 실행 중 자연어 명령에는 선택적 재할당을 적용한다.",
]):
    box(s, 0.8, 2.05 + i * 0.95, 11.8, 0.72, t, kind="det", size=13)
tb(s, 0.8, 5.15, 11.9, 2.1, [
   [("한계", {"bold": True, "size": 13, "color": INK})],
   [("· 제한된 실행 task 어휘 · 특정 scene 계열 · gpt-5-mini-2025-08-07 · 비교적 작은 평가 세트", {"size": 11})],
   [("· 시뮬레이터에서 명령은 queue되지만 안전 경계에서의 LLM 처리는 동기적이다 —", {"size": 11})],
   [("  '로봇이 움직이는 동안 LLM이 생각한다'가 아니다", {"size": 11, "color": MUTED})],
   [("Future work", {"bold": True, "size": 13, "color": DET})],
   [("· ROS2 / PX4 / Gazebo 물리 실행  · 진짜 비동기 상호작용과 stale-state 보호  · 더 다양한 임무·언어 평가", {"size": 11})],
], leading=1.22)
note(s,
     "[목표 1:15] 결론은 세 문장입니다. 자연어 임무를 실행 가능한 그래프로 바꾼다. "
     "결정론적 invariant 검증과 CBBA로 안전하고 재현 가능한 할당을 만든다. 실행 중 "
     "자연어 명령에는 선택적 재할당을 적용한다. 한계를 솔직히 말합니다 — 평가는 제한된 "
     "task 어휘, 특정 scene 계열, 단일 모델 스냅샷, 작은 세트에 기반합니다. 그리고 "
     "시뮬레이터에서 명령은 queue되지만 안전 경계에서 LLM 처리는 동기적입니다. "
     "'LLM이 생각하는 동안 로봇이 계속 움직인다'고 말하면 안 됩니다. "
     "후속은 ROS2·PX4·Gazebo 물리 실행, 진짜 비동기 상호작용과 stale-state 보호, "
     "더 다양한 임무·언어 평가입니다. 감사합니다.")


out = ROOT / "LLM-MRTA_발표.pptx"
prs.save(out)
print("wrote", out, f"({len(prs.slides._sldIdLst)} slides)")
