"""Native operator window for the P8~P10 interaction path (§21)."""

from __future__ import annotations

import html
import os
from dataclasses import asdict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desktop.controller import SCENARIO_PROFILES, SUPPORTED_MODES, DesktopController
from desktop.simulator import MissionSimulatorWindow
from interaction.audit import CheckpointAudit, ExecutionAudit
from interaction.orchestrator import TurnOutcome
from interaction.session import SessionPhase


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        label = QLabel(title.upper())
        label.setObjectName("metricTitle")
        self.value = QLabel("—")
        self.value.setObjectName("metricValue")
        layout.addWidget(label)
        layout.addWidget(self.value)


class OperatorWindow(QMainWindow):
    """Compact command surface; the map lives in its own top-level window."""

    def __init__(
        self,
        controller: DesktopController,
        simulator: MissionSimulatorWindow,
        *,
        playback_seconds: float | None = None,
        auto_run: bool = True,
    ) -> None:
        super().__init__()
        self.setObjectName("operatorWindow")
        self.setWindowTitle("LLM-MRTA · Operator Console")
        self.resize(650, 900)
        self.controller = controller
        self.simulator = simulator
        self._busy = False
        self._continuous = False
        self.auto_run = auto_run
        configured = playback_seconds
        if configured is None:
            configured = float(os.environ.get("LLM_MRTA_PLAYBACK_SECONDS", "3.0"))
        self.playback_seconds = max(0.0, configured)
        self.simulator.playback_finished.connect(self._on_playback_finished)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        brand = QVBoxLayout()
        eyebrow = QLabel("HETEROGENEOUS DISASTER RESPONSE")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("LLM–MRTA  /  OPERATOR")
        title.setObjectName("appTitle")
        brand.addWidget(eyebrow)
        brand.addWidget(title)
        header.addLayout(brand, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("modeCombo")
        self.mode_combo.addItems(SUPPORTED_MODES)
        self.mode_combo.setCurrentText(self.controller.mode)
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        header.addWidget(self.mode_combo)
        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("scenarioCombo")
        for scenario_id, profile in SCENARIO_PROFILES.items():
            self.scenario_combo.addItem(profile.label, scenario_id)
        self.scenario_combo.setCurrentIndex(
            self.scenario_combo.findData(self.controller.scenario_id)
        )
        self.scenario_combo.currentIndexChanged.connect(self._scenario_changed)
        header.addWidget(self.scenario_combo)
        layout.addLayout(header)

        metrics = QHBoxLayout()
        self.phase_card = MetricCard("Phase")
        self.clock_card = MetricCard("Simulation")
        self.task_card = MetricCard("Tasks")
        self.event_card = MetricCard("Audit")
        for card in (self.phase_card, self.clock_card, self.task_card, self.event_card):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        self.mode_banner = QLabel()
        self.mode_banner.setObjectName("modeBanner")
        layout.addWidget(self.mode_banner)
        self.scenario_help = QLabel()
        self.scenario_help.setObjectName("scenarioHelp")
        self.scenario_help.setWordWrap(True)
        layout.addWidget(self.scenario_help)

        section = QLabel("MISSION DIALOGUE")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        self.chat = QTextBrowser()
        self.chat.setObjectName("chatHistory")
        self.chat.setOpenExternalLinks(False)
        self.chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.chat, 1)

        self.candidate_frame = QFrame()
        self.candidate_frame.setObjectName("candidateFrame")
        candidate_outer = QVBoxLayout(self.candidate_frame)
        self.candidate_question = QLabel()
        self.candidate_question.setWordWrap(True)
        self.candidate_buttons = QHBoxLayout()
        candidate_outer.addWidget(self.candidate_question)
        candidate_outer.addLayout(self.candidate_buttons)
        layout.addWidget(self.candidate_frame)

        input_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setObjectName("commandInput")
        self.command_input.setPlaceholderText("자연어 임무 또는 상태 질문을 입력하세요")
        self.command_input.returnPressed.connect(self.submit_command)
        self.send_button = QPushButton("전송")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self.submit_command)
        input_row.addWidget(self.command_input, 1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        controls = QGridLayout()
        controls.setHorizontalSpacing(9)
        controls.setVerticalSpacing(9)
        self.checkpoint_button = QPushButton("▶  다음 checkpoint")
        self.checkpoint_button.setObjectName("checkpointButton")
        self.checkpoint_button.clicked.connect(self.play_checkpoint)
        self.continuous_button = QPushButton("▶▶  끝까지 연속 재생")
        self.continuous_button.setObjectName("continuousButton")
        self.continuous_button.clicked.connect(self.play_continuous)
        self.simulator_button = QPushButton("시뮬레이터 창 열기")
        self.simulator_button.clicked.connect(self.show_simulator)
        self.new_button = QPushButton("새 세션")
        self.new_button.clicked.connect(self.new_session)
        controls.addWidget(self.checkpoint_button, 0, 0)
        controls.addWidget(self.continuous_button, 0, 1)
        controls.addWidget(self.simulator_button, 1, 0)
        controls.addWidget(self.new_button, 1, 1)
        layout.addLayout(controls)

        self.latest = QLabel("새 임무를 입력하면 Validator와 CBBA 결과가 여기에 요약됩니다.")
        self.latest.setObjectName("latestDecision")
        self.latest.setWordWrap(True)
        layout.addWidget(self.latest)

        self.status = QLabel("READY")
        self.status.setObjectName("statusLine")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _mode_changed(self, mode: str) -> None:
        self.controller.set_mode(mode)
        self.refresh()

    def _scenario_changed(self, index: int) -> None:
        scenario_id = self.scenario_combo.itemData(index)
        if scenario_id == self.controller.scenario_id:
            return
        self.controller.new_session(scenario_id)
        self.simulator.show_spec(None)
        self.status.setText("새 scenario · 명령 대기")
        self.refresh()

    def _chat_html(self) -> str:
        blocks = []
        for message in self.controller.chat:
            escaped = html.escape(message.text).replace("\n", "<br>")
            if message.role == "operator":
                blocks.append(
                    '<div class="operator"><b>OPERATOR</b><br>' + escaped + "</div>"
                )
            else:
                blocks.append(
                    '<div class="system"><b>MISSION AI</b><br>' + escaped + "</div>"
                )
        return """
        <style>
        body { color:#e8eef7; font-family:sans-serif; }
        div { margin:8px 2px; padding:10px 12px; border-radius:8px; }
        .operator { background:#18304f; margin-left:32px; }
        .system { background:#132238; margin-right:32px; }
        b { color:#6ee7f2; font-size:9px; letter-spacing:1px; }
        </style>
        """ + "".join(blocks)

    def _last_decision(self) -> str:
        session = self.controller.session
        if not session.event_log:
            return "대기 중 · 아직 감사 event가 없습니다."
        event = session.event_log[-1]
        if isinstance(event, CheckpointAudit):
            completed = ", ".join(event.completed_now) or "없음"
            return (
                f"CHECKPOINT  t={event.simulation_time:.1f}s  ·  완료 {completed}  ·  "
                f"RUNNING {len(event.running)}  ·  READY {len(event.ready_tasks)}"
            )
        if isinstance(event, ExecutionAudit):
            return (
                f"EXECUTION {event.execution_termination}  ·  makespan {event.makespan:.1f}s  ·  "
                f"violations {len(event.capability_violations) + len(event.precedence_violations)}"
            )
        if event.event_type == "INCIDENT_OBSERVATION":
            return (
                f"{event.source}  ·  {event.zone_id}  ·  {event.outcome}  ·  "
                f"incident {event.incident_id or 'none'}  ·  "
                f"response {event.response_up_to or 'scene-only'}"
            )
        parts = [event.outcome]
        if event.intent_kind:
            parts.append(event.intent_kind)
        if event.grounding and event.grounding.entity_id:
            parts.append(f"target {event.grounding.entity_id}")
        if event.patch:
            parts.append(
                f"patch +{len(event.patch.added_tasks)} task / +{len(event.patch.added_edges)} edge"
            )
        if event.online_reallocation:
            changes = asdict(event.online_reallocation.assignment_changes)
            changed = sum(len(value) for value in changes.values())
            parts.append(f"runtime assignment Δ {changed}")
        return "  ·  ".join(parts)

    def _refresh_candidates(self) -> None:
        _clear_layout(self.candidate_buttons)
        pending = self.controller.session.pending_clarification
        self.candidate_frame.setVisible(pending is not None)
        if pending is None:
            return
        last = self.controller.session.turn_log[-1]
        question = last.grounding.clarification if last.grounding else "후보를 선택하세요."
        self.candidate_question.setText(question)
        for entity_id in pending.candidates:
            button = QPushButton(entity_id)
            button.setObjectName("candidateButton")
            button.clicked.connect(
                lambda checked=False, candidate=entity_id: self.choose_candidate(candidate)
            )
            self.candidate_buttons.addWidget(button)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.cancel_candidate)
        self.candidate_buttons.addWidget(cancel)

    def _can_advance(self) -> bool:
        session = self.controller.session
        retryable = (
            session.phase is SessionPhase.EXECUTION_FAILED
            and session.runtime is not None
            and session.execution is None
        )
        return (
            session.state is not None
            and session.plan is not None
            and session.pending_clarification is None
            and (
                session.phase
                in {SessionPhase.PLANNING, SessionPhase.EXECUTION_PAUSED}
                or retryable
            )
        )

    def refresh(self) -> None:
        session = self.controller.session
        self.phase_card.value.setText(session.phase.value)
        now = session.runtime.now if session.runtime is not None else 0.0
        self.clock_card.value.setText(f"{now:.1f} s")
        task_count = len(session.state.graph.tasks) if session.state is not None else 0
        self.task_card.value.setText(str(task_count))
        self.event_card.value.setText(str(len(session.event_log)))
        self.mode_banner.setText(
            {
                "mock": "MOCK · 고정 발표 스크립트 · 연구 측정값 아님",
                "cached": "CACHED · 동일 모델·문맥·발화의 저장 응답",
                "live": "LIVE · 실제 OpenAI API 응답을 캐시에 기록",
            }[self.controller.mode]
        )
        policy = session.directive.incident_response_up_to
        fixture = self.controller.fixture_id or "none"
        mock_commands = "  →  ".join(self.controller.mock_commands)
        live_examples = "  →  ".join(self.controller.live_examples)
        if self.controller.mode == "mock":
            command_help = f"MOCK 정확 입력: {mock_commands}"
        elif self.controller.mode == "cached":
            command_help = (
                f"CACHED exact replay: {live_examples}"
                if live_examples
                else "CACHED: 이 session과 정확히 일치하는 저장 응답이 필요합니다."
            )
        else:
            command_help = (
                f"LIVE 예시(지원 범위 안에서 표현 변경 가능): {live_examples}"
                if live_examples
                else "LIVE: 지원 범위 안에서 자연어 표현을 바꿔 입력할 수 있습니다."
            )
        self.scenario_help.setText(
            f"SCENARIO: {self.controller.scenario_label}  ·  fixture: {fixture}  ·  "
            f"active policy: {policy.value if policy is not None else 'none'}\n"
            + command_help
        )
        self.chat.setHtml(self._chat_html())
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.latest.setText(self._last_decision())
        self._refresh_candidates()

        pending = session.pending_clarification is not None
        can_queue = (
            self._busy
            and self.simulator.is_playing
            and self.controller.queued_command is None
        )
        can_input = not pending and (not self._busy or can_queue)
        self.command_input.setEnabled(can_input)
        self.send_button.setEnabled(can_input)
        can_advance = not self._busy and self._can_advance()
        self.checkpoint_button.setEnabled(can_advance)
        self.continuous_button.setEnabled(can_advance)
        self.new_button.setEnabled(not self._busy)
        self.mode_combo.setEnabled(not self._busy)
        self.scenario_combo.setEnabled(not self._busy)

    def _refresh_simulator(self) -> None:
        self.simulator.show_spec(self.controller.current_map_spec())

    def submit_command(self) -> None:
        utterance = self.command_input.text().strip()
        if not utterance:
            return
        if self._busy:
            if not self.simulator.is_playing:
                return
            try:
                self.controller.queue_command(utterance)
                self.command_input.clear()
                self.status.setText(
                    "QUEUED · 현재 segment 종료 뒤 safe checkpoint에서 적용"
                )
            except ValueError as exc:
                self.status.setText(f"QUEUE REFUSED · {exc}")
            self.refresh()
            return
        self.status.setText("LLM / VALIDATOR 처리 중…")
        QApplication.processEvents()
        try:
            result = self.controller.submit(utterance)
            self.command_input.clear()
            self.status.setText(f"{result.outcome.value} · 감사 기록 저장됨")
            self._refresh_simulator()
        except Exception as exc:  # UI wiring/import errors, not mission decisions
            self.status.setText(f"ERROR · {type(exc).__name__}: {exc}")
            QMessageBox.warning(self, "명령 처리 실패", f"{type(exc).__name__}: {exc}")
            self.refresh()
            return
        self.refresh()
        self._auto_run_after_commit(result)

    def _auto_run_after_commit(self, result) -> None:
        """Start initial or D-055 follow-on work after an accepted commit."""
        if (
            self.auto_run
            and result.outcome is TurnOutcome.COMMITTED
            and self._can_advance()
        ):
            self.status.setText("AUTO · 임무 commit 완료, 실행을 시작합니다")
            QTimer.singleShot(0, self.play_continuous)

    def choose_candidate(self, entity_id: str) -> None:
        if self._busy:
            return
        result = self.controller.select_candidate(entity_id)
        self.status.setText(f"{result.outcome.value} · {entity_id} 선택")
        self._refresh_simulator()
        self.refresh()
        self._auto_run_after_commit(result)

    def cancel_candidate(self) -> None:
        if self._busy:
            return
        result = self.controller.cancel_candidate()
        self.status.setText(result.outcome.value)
        self.refresh()

    def _advance_segment(self) -> None:
        self._busy = True
        self.status.setText("다음 completion checkpoint 계산 중…")
        self.refresh()
        QApplication.processEvents()
        try:
            presentation = self.controller.advance_checkpoint()
        except Exception as exc:
            self._continuous = False
            self._busy = False
            self.status.setText(f"ERROR · {type(exc).__name__}: {exc}")
            self.refresh()
            return
        self.refresh()
        if presentation.playback_error:
            self._continuous = False
            self._busy = False
            self.status.setText(
                "실행은 commit됐지만 playback을 만들지 못했습니다 · "
                + presentation.playback_error
            )
            self._refresh_simulator()
            self.refresh()
            return
        if presentation.playback is None:
            self._continuous = False
            self._busy = False
            self.status.setText("실행 종료 · 감사 기록 저장됨")
            self._refresh_simulator()
            self.refresh()
            return
        self.simulator.show()
        self.simulator.raise_()
        self.status.setText("PLAYBACK · 입력 잠금")
        self.simulator.play(
            presentation.playback,
            wall_seconds=self.playback_seconds,
        )
        self.status.setText(
            "AUTO PLAYBACK · 자연어 명령 1건 입력 가능 · 다음 safe checkpoint 적용"
            if self._continuous
            else "CHECKPOINT PLAYBACK · 완료 후 입력 가능"
        )
        self.refresh()

    def play_checkpoint(self) -> None:
        if not self._can_advance() or self._busy:
            return
        self._continuous = False
        self._advance_segment()

    def play_continuous(self) -> None:
        if not self._can_advance() or self._busy:
            return
        self._continuous = True
        self._advance_segment()

    def _on_playback_finished(self) -> None:
        if self.controller.queued_command is not None:
            self.status.setText("SAFE CHECKPOINT · queued 명령을 LLM로 처리 중…")
            self.refresh()
            try:
                result = self.controller.submit_queued()
            except Exception as exc:
                self._continuous = False
                self._busy = False
                self.status.setText(f"QUEUE ERROR · {type(exc).__name__}: {exc}")
                self._refresh_simulator()
                self.refresh()
                return
            self._refresh_simulator()
            if (
                result.outcome
                not in {
                    TurnOutcome.COMMITTED,
                    TurnOutcome.NO_CHANGE,
                    TurnOutcome.ANSWERED,
                }
                or self.controller.session.pending_clarification is not None
            ):
                self._continuous = False
                self._busy = False
                self.status.setText(
                    f"{result.outcome.value} · 자동 실행 정지 · 운용자 확인 필요"
                )
                self.refresh()
                return
            self.status.setText(
                f"{result.outcome.value} · safe checkpoint 적용 완료"
            )
            self.refresh()
        if self._continuous and self.controller.session.phase is SessionPhase.EXECUTION_PAUSED:
            self.status.setText("연속 재생 · 다음 checkpoint로 진행")
            QTimer.singleShot(0, self._advance_segment)
            return
        self._continuous = False
        self._busy = False
        phase = self.controller.session.phase
        self.status.setText(
            "CHECKPOINT · 후속 명령 입력 가능"
            if phase is SessionPhase.EXECUTION_PAUSED
            else f"{phase.value} · 재생 종료"
        )
        # The committed checkpoint may also have revealed a P12 observation
        # and replaced the runtime after this segment's frozen playback was
        # built. Refresh now so the new incident/tasks appear only after the
        # detecting recon reaches its completion frame.
        self._refresh_simulator()
        self.refresh()

    def show_simulator(self) -> None:
        self._refresh_simulator()
        self.simulator.show()
        self.simulator.raise_()
        self.simulator.activateWindow()

    def new_session(self) -> None:
        if self._busy:
            return
        self.controller.new_session()
        self.mode_combo.setCurrentText(self.controller.mode)
        self.simulator.show_spec(None)
        self.status.setText("새 세션 · READY")
        self.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.simulator.shutdown()
        event.accept()
        QApplication.quit()


__all__ = ["OperatorWindow"]
