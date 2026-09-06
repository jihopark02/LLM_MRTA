"""Serialising a session's audit trail (RESEARCH_CONTRACT.md §18.9).

§18.9 fixes both the record shape and the path, so the phase owes an actual
file, not just a serialisable dataclass:

    data/interaction_runs/<session_id>.json

The payload is an **event stream**, not a list of turns, so pressing run in
P8.3 appends an ``ExecutionAudit`` beside the ``TurnAudit`` records without
reshaping anything — every entry is discriminated by ``event_type``.

Sits above both ``audit`` (the schemas) and ``session`` (the holder), which is
why it is its own module: ``session`` already imports ``audit`` for the
``turn_log`` annotation.
"""

import json
from pathlib import Path

from interaction.audit import ExecutionAudit, TurnAudit
from interaction.session import MissionSession
from validator.hashing import VALIDATOR_VERSION, scene_hash

#: §18.9. One file per session.
AUDIT_DIR = Path("data/interaction_runs")


def session_audit_payload(
    session: MissionSession, executions: list[ExecutionAudit] | None = None
) -> dict:
    """The full audit record for one planning session.

    ``executions`` is accepted now so the P8.3 execute action has somewhere to
    put its record; in P8.2 there are none.
    """
    events: list[dict] = [
        e.to_dict() for e in session.turn_log if isinstance(e, TurnAudit)
    ]
    events += [e.to_dict() for e in (executions or [])]
    return {
        "session_id": session.session_id,
        "scene_hash": scene_hash(session.scene),
        "validator_version": VALIDATOR_VERSION,
        "phase": session.phase.value,
        "turn_count": session.turn_count,
        "events": events,
    }


def session_audit_json(
    session: MissionSession, executions: list[ExecutionAudit] | None = None
) -> str:
    """Deterministic JSON. ``ensure_ascii=False`` because operator utterances
    and clarification questions are Korean and must stay readable."""
    return json.dumps(
        session_audit_payload(session, executions),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def audit_path(session_id: str, directory: str | Path = AUDIT_DIR) -> Path:
    return Path(directory) / f"{session_id}.json"


def write_session_audit(
    session: MissionSession,
    directory: str | Path = AUDIT_DIR,
    executions: list[ExecutionAudit] | None = None,
) -> Path:
    """Write the session's audit trail and return the path it went to."""
    path = audit_path(session.session_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_audit_json(session, executions), encoding="utf-8")
    return path


__all__ = [
    "AUDIT_DIR",
    "audit_path",
    "session_audit_payload",
    "session_audit_json",
    "write_session_audit",
]
