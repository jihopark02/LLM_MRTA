"""Native 2D simulator window consuming only P8.5/P10 render specs (§21)."""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from core.enums import PlatformKind
from demo.animation import AnimationFrameSpec, PlaybackSpec
from demo.visualization import MapRenderSpec

BACKGROUND = QColor("#08111f")
PANEL = QColor("#0f1c2e")
TEXT = QColor("#e8eef7")
MUTED = QColor("#8fa1b8")
ROUTE = QColor("#304158")
ZONE = QColor("#8fa1b8")
INCIDENT = QColor("#ff5d57")
TASK = QColor("#c8d2df")


def _pen_style(phase: str) -> Qt.PenStyle:
    return {
        "in_progress": Qt.PenStyle.DashLine,
        "remaining": Qt.PenStyle.DotLine,
    }.get(phase, Qt.PenStyle.SolidLine)


def _agent_offsets(agents) -> dict[str, tuple[float, float]]:
    """Deterministic screen offsets for agents at exactly the same pose.

    The map coordinate stays in ``MapRenderSpec``.  A short leader line points
    from each displaced marker back to that true coordinate, avoiding the
    unreadable six-label pile-up at the shared depot.
    """
    groups: dict[tuple[float, float], list[str]] = {}
    for agent in agents:
        groups.setdefault(agent.position, []).append(agent.agent_id)
    result = {}
    for agent_ids in groups.values():
        ordered = sorted(agent_ids)
        if len(ordered) == 1:
            result[ordered[0]] = (0.0, 0.0)
            continue
        for index, agent_id in enumerate(ordered):
            angle = -math.pi / 2 + 2 * math.pi * index / len(ordered)
            result[agent_id] = (14.0 * math.cos(angle), 14.0 * math.sin(angle))
    return result


class MissionCanvas(QWidget):
    """A scalable Qt painter for an already-built ``MapRenderSpec``."""

    def __init__(self, parent: QWidget | None = None, *, minimal: bool = True) -> None:
        super().__init__(parent)
        self.setMinimumSize(760, 560)
        self.spec: MapRenderSpec | None = None
        self.frame: AnimationFrameSpec | None = None
        #: MP4MR-clean view: drop the route-lane / zone / incident backdrop so
        #: the CBBA allocation polylines carry the picture (matches
        #: ``demo.visualization.render_mission_map(minimal=True)`` for slides).
        self.minimal = minimal

    def set_spec(
        self,
        spec: MapRenderSpec | None,
        frame: AnimationFrameSpec | None = None,
    ) -> None:
        self.spec = spec
        self.frame = frame
        self.update()

    def _points(self) -> list[tuple[float, float]]:
        if self.spec is None:
            return []
        points = [
            (point.x, point.y)
            for point in self.spec.zones + self.spec.incidents + self.spec.task_points
        ]
        points += [agent.position for agent in self.spec.agents]
        points += [point for lane in self.spec.route_lanes for point in lane]
        points += [point for leg in self.spec.legs for point in leg.points]
        return points

    def _projector(self, viewport: QRectF) -> Callable[[tuple[float, float]], QPointF]:
        points = self._points()
        if not points:
            return lambda point: viewport.center()
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        left, right = min(xs), max(xs)
        bottom, top = min(ys), max(ys)
        width = max(right - left, 1.0)
        height = max(top - bottom, 1.0)
        scale = min(viewport.width() / width, viewport.height() / height)
        used_w, used_h = width * scale, height * scale
        x0 = viewport.left() + (viewport.width() - used_w) / 2.0
        y0 = viewport.top() + (viewport.height() - used_h) / 2.0

        def project(point: tuple[float, float]) -> QPointF:
            return QPointF(
                x0 + (point[0] - left) * scale,
                y0 + (top - point[1]) * scale,
            )

        return project

    @staticmethod
    def _polyline(painter: QPainter, points, project) -> None:
        if len(points) < 2:
            return
        path = QPainterPath(project(points[0]))
        for point in points[1:]:
            path.lineTo(project(point))
        painter.drawPath(path)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BACKGROUND)
        if self.spec is None:
            painter.setPen(MUTED)
            painter.setFont(QFont("Sans Serif", 16))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "AWAITING MISSION")
            return

        legend_width = 150.0
        viewport = QRectF(self.rect()).adjusted(52.0, 45.0, -legend_width, -52.0)
        project = self._projector(viewport)

        if not self.minimal:
            painter.setPen(QPen(ROUTE, 2.0))
            for lane in self.spec.route_lanes:
                self._polyline(painter, lane, project)

        for leg in self.spec.legs:
            color = QColor(
                next(
                    (agent.color for agent in self.spec.agents if agent.agent_id == leg.agent_id),
                    "#8fa1b8",
                )
            )
            if leg.phase == "remaining":
                color.setAlpha(120)
            pen = QPen(color, 2.0 if self.minimal else 3.4)
            pen.setStyle(_pen_style(leg.phase))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            self._polyline(painter, leg.points, project)
            if leg.points:
                end = project(leg.points[-1])
                painter.setPen(color)
                painter.setFont(QFont("Sans Serif", 8, QFont.Weight.Bold))
                painter.drawText(end + QPointF(6, -6), str(leg.order + 1))

        if not self.minimal:
            painter.setFont(QFont("Sans Serif", 8))
            for zone in self.spec.zones:
                point = project((zone.x, zone.y))
                painter.setPen(QPen(ZONE, 2.0))
                painter.setBrush(QBrush(PANEL))
                painter.drawRoundedRect(QRectF(point.x() - 7, point.y() - 7, 14, 14), 3, 3)
                painter.drawText(point + QPointF(-25, -12), zone.label)

        painter.setPen(QPen(TASK, 1.0))
        painter.setBrush(QBrush(TASK))
        task_radius = 3.0 if self.minimal else 2.4
        for task in self.spec.task_points:
            point = project((task.x, task.y))
            painter.drawEllipse(point, task_radius, task_radius)

        if not self.minimal:
            painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
            for incident in self.spec.incidents:
                point = project((incident.x, incident.y))
                painter.setPen(QPen(INCIDENT, 3.0))
                painter.drawLine(point + QPointF(-7, -7), point + QPointF(7, 7))
                painter.drawLine(point + QPointF(-7, 7), point + QPointF(7, -7))
                painter.drawText(point + QPointF(-36, 24), incident.entity_id)

        activity = {
            item.agent_id: (item.activity, item.task_id) for item in self.frame.agents
        } if self.frame is not None else {}
        offsets = _agent_offsets(self.spec.agents)
        for agent in self.spec.agents:
            anchor = project(agent.position)
            dx, dy = offsets[agent.agent_id]
            point = anchor + QPointF(dx, dy)
            color = QColor(agent.color)
            if dx or dy:
                painter.setPen(QPen(QColor("#52647b"), 1.0))
                painter.drawLine(anchor, point)
                painter.setBrush(QBrush(QColor("#e8eef7")))
                painter.drawEllipse(anchor, 2, 2)
            painter.setPen(QPen(QColor("#f8fafc"), 1.4))
            painter.setBrush(QBrush(color))
            if agent.platform_kind is PlatformKind.UAV:
                painter.drawEllipse(point, 9, 9)
            else:
                painter.drawRoundedRect(
                    QRectF(point.x() - 9, point.y() - 9, 18, 18), 2, 2
                )
            painter.setPen(TEXT)
            painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
            painter.drawText(point + QPointF(11, 4), agent.agent_id)

        legend_x = self.width() - 130
        painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
        painter.setPen(TEXT)
        painter.drawText(legend_x, 65, "AGENTS")
        painter.setFont(QFont("Sans Serif", 8))
        for index, agent in enumerate(self.spec.agents):
            y = 91 + index * 34
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(agent.color)))
            painter.drawEllipse(QPointF(legend_x + 8, y - 4), 6, 6)
            painter.setPen(TEXT)
            state, task_id = activity.get(agent.agent_id, ("", None))
            painter.drawText(legend_x + 22, y, f"{agent.agent_id}  {state}")
            if task_id:
                painter.setPen(MUTED)
                painter.drawText(legend_x + 22, y + 13, task_id.split("__", 1)[0])

        painter.setPen(MUTED)
        painter.setFont(QFont("Sans Serif", 8))
        painter.drawText(
            22,
            self.height() - 18,
            "KINEMATIC SCHEDULE PLAYBACK · NOT ROBOT TELEMETRY",
        )


class MissionSimulatorWindow(QMainWindow):
    """A separate top-level viewport driven by immutable playback frames."""

    playback_started = Signal()
    playback_finished = Signal()

    def __init__(self, *, minimal: bool = True) -> None:
        super().__init__()
        self.setObjectName("missionSimulatorWindow")
        self.setWindowTitle("LLM-MRTA · Mission Simulator")
        self.resize(1120, 760)
        self._allow_close = False
        self._frames: tuple[AnimationFrameSpec, ...] = ()
        self._frame_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 14, 18, 16)
        self.header = QLabel("MISSION SIMULATOR  ·  AWAITING MISSION")
        self.header.setObjectName("simulatorHeader")
        self.clock = QLabel("SIMULATION  t = 0.0 s")
        self.clock.setObjectName("simulatorClock")
        self.canvas = MissionCanvas(minimal=minimal)
        layout.addWidget(self.header)
        layout.addWidget(self.clock)
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(body)

    @property
    def is_playing(self) -> bool:
        return self._timer.isActive()

    def show_spec(self, spec: MapRenderSpec | None) -> None:
        if self.is_playing:
            return
        self.canvas.set_spec(spec)
        if spec is None:
            self.header.setText("MISSION SIMULATOR  ·  AWAITING MISSION")
            self.clock.setText("SIMULATION  t = 0.0 s")
            return
        self.header.setText(f"MISSION SIMULATOR  ·  {spec.mode.upper()}")
        when = spec.simulation_time or 0.0
        self.clock.setText(f"SIMULATION  t = {when:.1f} s")

    def play(self, playback: PlaybackSpec, *, wall_seconds: float = 3.0) -> None:
        if self.is_playing:
            raise RuntimeError("the simulator is already playing")
        if not playback.frames:
            raise ValueError("playback must contain frames")
        self._frames = playback.frames
        self._frame_index = 0
        self._show_frame(self._frames[0])
        self.playback_started.emit()
        if len(self._frames) == 1:
            self.playback_finished.emit()
            return
        interval = max(1, round(max(0.0, wall_seconds) * 1000 / (len(self._frames) - 1)))
        self._timer.start(interval)

    def _show_frame(self, frame: AnimationFrameSpec) -> None:
        self.canvas.set_spec(frame.map_spec, frame)
        self.header.setText("MISSION SIMULATOR  ·  ONLINE PLAYBACK")
        self.clock.setText(
            f"SIMULATION  t = {frame.simulation_time:.1f} s"
            f"  ·  {frame.progress * 100:3.0f}%"
        )

    def _next_frame(self) -> None:
        self._frame_index += 1
        self._show_frame(self._frames[self._frame_index])
        if self._frame_index == len(self._frames) - 1:
            self._timer.stop()
            self.playback_finished.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._allow_close:
            event.accept()
        else:
            self.hide()
            event.ignore()

    def shutdown(self) -> None:
        self._timer.stop()
        self._allow_close = True
        self.close()


__all__ = ["MissionCanvas", "MissionSimulatorWindow"]
