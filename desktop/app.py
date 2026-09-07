"""Application bootstrap for the two-window native presentation client."""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from desktop.controller import DesktopController
from desktop.simulator import MissionSimulatorWindow
from desktop.window import OperatorWindow

STYLE = """
QWidget { background:#08111f; color:#e8eef7; font-family:'DejaVu Sans'; font-size:12px; }
QMainWindow { background:#08111f; }
QLabel#eyebrow { color:#55d6df; font-size:9px; font-weight:700; letter-spacing:2px; }
QLabel#appTitle { color:#f8fafc; font-size:24px; font-weight:800; }
QLabel#sectionTitle { color:#8fa1b8; font-size:10px; font-weight:700; letter-spacing:2px; }
QFrame#metricCard { background:#0f1c2e; border:1px solid #20324a; border-radius:8px; }
QLabel#metricTitle { color:#7286a0; font-size:8px; font-weight:700; }
QLabel#metricValue { color:#f8fafc; font-size:15px; font-weight:700; }
QLabel#modeBanner { background:#102b3a; color:#6ee7f2; padding:8px 11px; border-radius:6px; }
QLabel#scenarioHelp { color:#9fb0c5; background:#0c1727; padding:8px 11px;
                      border:1px solid #20324a; border-radius:6px; }
QTextBrowser { background:#0c1727; border:1px solid #20324a; border-radius:9px; padding:7px; }
QLineEdit { background:#0f1c2e; border:1px solid #2d4563; border-radius:7px; padding:11px; }
QLineEdit:focus { border:1px solid #55d6df; }
QPushButton { background:#17263a; border:1px solid #304761; border-radius:7px;
              padding:10px; font-weight:600; }
QPushButton:hover { background:#203651; border-color:#55d6df; }
QPushButton:disabled { color:#52647b; background:#0c1727; border-color:#17263a; }
QPushButton#primaryButton, QPushButton#continuousButton {
    background:#0f7180; border-color:#23aebe; color:white;
}
QPushButton#checkpointButton { background:#244a75; border-color:#3e79b4; color:white; }
QComboBox { background:#0f1c2e; border:1px solid #304761; border-radius:7px;
            padding:8px 12px; min-width:90px; }
QFrame#candidateFrame { background:#2d2410; border:1px solid #725c20;
                        border-radius:8px; padding:8px; }
QLabel#latestDecision { background:#0f1c2e; border-left:3px solid #55d6df; padding:10px; }
QLabel#statusLine { color:#8fa1b8; padding:3px; }
QLabel#simulatorHeader { color:#55d6df; font-size:11px; font-weight:700; letter-spacing:2px; }
QLabel#simulatorClock { color:#f8fafc; font-size:22px; font-weight:700; }
"""


def build_windows(
    controller: DesktopController | None = None,
    *,
    playback_seconds: float | None = None,
) -> tuple[OperatorWindow, MissionSimulatorWindow]:
    controller = controller or DesktopController()
    simulator = MissionSimulatorWindow()
    operator = OperatorWindow(
        controller,
        simulator,
        playback_seconds=playback_seconds,
    )
    return operator, simulator


def run(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("LLM-MRTA Operator Console")
    app.setStyleSheet(STYLE)
    operator, simulator = build_windows()

    screen = app.primaryScreen().availableGeometry()
    operator.move(screen.topLeft() + QPoint(24, 24))
    simulator.move(operator.geometry().topRight() + QPoint(18, 0))
    operator.show()
    simulator.show()
    # Keep Python references for the lifetime of QApplication.
    app._llm_mrta_windows = (operator, simulator)
    return app.exec()


__all__ = ["STYLE", "build_windows", "run"]
