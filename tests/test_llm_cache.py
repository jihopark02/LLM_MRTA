"""Exact-cache provenance and key boundary for the P8.3 UI (§18.9)."""

import json

import pytest
from pydantic import ValidationError

from interaction.schemas import IntentEnvelope
from llm.backend import MockBackend
from llm.cache import CachedBackend, CacheMissError, RecordingBackend, cache_key
from llm.schemas import Step1Output


class FakeLiveBackend:
    mode = "live"
    model = "requested-model"

    def __init__(self):
        self.calls = 0
        self.resolved_models = []

    def complete(self, system, user, schema):
        self.calls += 1
        self.resolved_models.append("resolved-model-2026-09-06")
        return schema.model_validate({"intent": {"kind": "QUERY_STATUS"}})


def test_live_record_then_cached_replay_is_exact_and_marks_provenance(tmp_path):
    live = FakeLiveBackend()
    recording = RecordingBackend(live, tmp_path)

    first = recording.complete("context", "Operator: 상태", IntentEnvelope)
    replay = CachedBackend("requested-model", tmp_path)
    second = replay.complete("context", "Operator: 상태", IntentEnvelope)

    assert first == second
    assert live.calls == 1
    assert recording.mode == "live"
    assert replay.mode == "cached"
    assert replay.resolved_models == ["resolved-model-2026-09-06"]
    entries = list(tmp_path.glob("*.json"))
    assert len(entries) == 1
    assert json.loads(entries[0].read_text())["response"] == {
        "intent": {"about": "mission", "kind": "QUERY_STATUS", "target_phrase": None}
    }


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("model", "other-model"),
        ("system", "other-context"),
        ("user", "Operator: 다른 질문"),
        ("schema", Step1Output),
    ],
)
def test_key_changes_for_every_contract_component(change, value):
    kwargs = {
        "model": "requested-model",
        "system": "context",
        "user": "Operator: 상태",
        "schema": IntentEnvelope,
    }
    original = cache_key(**kwargs)
    kwargs[change] = value
    assert cache_key(**kwargs) != original


def test_cache_miss_never_falls_through_to_live(tmp_path):
    backend = CachedBackend("requested-model", tmp_path)
    with pytest.raises(CacheMissError, match="no cached response"):
        backend.complete("context", "Operator: 상태", IntentEnvelope)
    assert list(tmp_path.iterdir()) == []


def test_tampered_cached_payload_is_revalidated(tmp_path):
    live = FakeLiveBackend()
    RecordingBackend(live, tmp_path).complete("context", "Operator: 상태", IntentEnvelope)
    entry = next(tmp_path.glob("*.json"))
    payload = json.loads(entry.read_text())
    payload["response"]["unexpected"] = True
    entry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        CachedBackend("requested-model", tmp_path).complete(
            "context", "Operator: 상태", IntentEnvelope
        )


@pytest.mark.parametrize("backend", [MockBackend([]), object()])
def test_recording_backend_rejects_non_live_or_unidentified_backends(backend, tmp_path):
    with pytest.raises(ValueError, match="live backend"):
        RecordingBackend(backend, tmp_path)


def test_recording_backend_requires_a_declared_model(tmp_path):
    class NoModel:
        mode = "live"
        resolved_models = []

    with pytest.raises(ValueError, match="model"):
        RecordingBackend(NoModel(), tmp_path)
