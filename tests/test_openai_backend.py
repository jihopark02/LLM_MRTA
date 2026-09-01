"""OpenAIBackend, exercised against an injected fake client — no network, no
`openai` package required (RESEARCH_CONTRACT.md §12, D-018)."""

from types import SimpleNamespace

from llm.backend import DEFAULT_MODEL, OpenAIBackend
from llm.schemas import Step1Output


class _FakeCompletions:
    def __init__(self, parsed, resolved_model="gpt-5-mini-2025-08-07"):
        self.calls: list[dict] = []
        self._parsed = parsed
        self._resolved_model = resolved_model

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(parsed=self._parsed)
        return SimpleNamespace(
            model=self._resolved_model, choices=[SimpleNamespace(message=message)]
        )


def _fake_client(parsed):
    completions = _FakeCompletions(parsed)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_sends_model_schema_and_messages():
    parsed = Step1Output(tasks=[])
    client, completions = _fake_client(parsed)
    backend = OpenAIBackend(model="gpt-5-mini", client=client)

    out = backend.complete("sys prompt", "user prompt", Step1Output)

    assert out is parsed
    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["model"] == "gpt-5-mini"
    assert call["response_format"] is Step1Output
    assert call["messages"] == [
        {"role": "system", "content": "sys prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert "temperature" not in call  # default is None -> omitted


def test_explicit_temperature_is_sent():
    client, completions = _fake_client(Step1Output(tasks=[]))
    backend = OpenAIBackend(model="gpt-4o-mini", temperature=0.0, client=client)
    backend.complete("s", "u", Step1Output)
    assert completions.calls[0]["temperature"] == 0.0


def test_default_model_is_gpt_5_mini():
    assert DEFAULT_MODEL == "gpt-5-mini"


def test_resolved_model_is_recorded_for_reproducibility():
    client, _ = _fake_client(Step1Output(tasks=[]))
    backend = OpenAIBackend(client=client)
    backend.complete("s", "u", Step1Output)
    backend.complete("s", "u", Step1Output)
    assert backend.resolved_models == ["gpt-5-mini-2025-08-07", "gpt-5-mini-2025-08-07"]


def test_client_is_built_once_and_reused(monkeypatch):
    import openai

    created = []
    original_init = openai.OpenAI.__init__

    def counting_init(self, *a, **kw):
        created.append(self)
        return original_init(self, *a, **kw)

    monkeypatch.setattr(openai.OpenAI, "__init__", counting_init)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    backend = OpenAIBackend()
    with_client = backend._get_client()
    with_client_again = backend._get_client()
    assert with_client is with_client_again
    assert len(created) == 1  # not rebuilt on the second call


def test_refusal_raises():
    client, _ = _fake_client(parsed=None)
    backend = OpenAIBackend(client=client)
    try:
        backend.complete("s", "u", Step1Output)
    except RuntimeError as e:
        assert "refused" in str(e) or "unparseable" in str(e)
    else:
        raise AssertionError("expected RuntimeError on a None-parsed response")
