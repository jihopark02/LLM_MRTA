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

from interaction.session import MissionSession, valid_session_id
from validator.hashing import VALIDATOR_VERSION, scene_hash

#: §18.9. One file per session.
AUDIT_DIR = Path("data/interaction_runs")


def session_audit_payload(session: MissionSession) -> dict:
    """The full audit record for one planning session.

    Event order is owned by ``MissionSession.append_event``.  This writer does
    not merge or sort anything; it only validates and serialises that order.
    """
    events: list[dict] = []
    for event_seq, event in enumerate(session.event_log):
        if event.session_id != session.session_id:
            raise ValueError(
                f"event session_id {event.session_id!r} does not match {session.session_id!r}"
            )
        payload = event.to_dict()
        payload["event_seq"] = event_seq
        events.append(payload)
    return {
        "session_id": session.session_id,
        "scene_hash": scene_hash(session.scene),
        "validator_version": VALIDATOR_VERSION,
        "phase": session.phase.value,
        "turn_count": session.turn_count,
        "events": events,
    }


def session_audit_json(session: MissionSession) -> str:
    """Deterministic JSON. ``ensure_ascii=False`` because operator utterances
    and clarification questions are Korean and must stay readable."""
    return json.dumps(
        session_audit_payload(session),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def audit_path(session_id: str, directory: str | Path = AUDIT_DIR) -> Path:
    """The record's path. ``session_id`` is constrained at the session boundary
    (D-030) so the join cannot leave ``directory``; re-checked here because
    this function is also reachable with a bare id."""
    if not valid_session_id(session_id):
        raise ValueError(f"session_id is not a usable path component: {session_id!r}")
    return Path(directory) / f"{session_id}.json"


def write_session_audit(
    session: MissionSession,
    directory: str | Path = AUDIT_DIR,
) -> Path:
    """Write the session's audit trail and return the path it went to."""
    path = audit_path(session.session_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_audit_json(session), encoding="utf-8")
    return path


__all__ = [
    "AUDIT_DIR",
    "audit_path",
    "session_audit_payload",
    "session_audit_json",
    "write_session_audit",
]
