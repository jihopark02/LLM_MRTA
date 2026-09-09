"""LLM backend abstraction (RESEARCH_CONTRACT.md §12, §14 PROVENANCE).

Only the *pattern* of a structured-output wrapper is reused from LLM_CBBA
(``llm/backends.py``). The real backend targets the OpenAI SDK
(``chat.completions.parse`` with a pydantic ``response_format``). Every pipeline
test uses ``MockBackend`` so the P5 gate needs no network and no API key.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Overridable; the eval (§14 reproducibility) pins this and records it with the
# results. gpt-5-mini is a reasoning model -> no explicit temperature.
DEFAULT_MODEL = "gpt-5-mini"

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _load_dotenv() -> None:
    """Fill os.environ from a repo-root `.env` (KEY=value lines) without ever
    overriding a variable the real environment already set. `.env` is gitignored.
    """
    if not _ENV_FILE.is_file():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


class LLMBackend(Protocol):
    #: Provenance of the responses this backend returns, recorded in every
    #: audit entry (contract §18.9). A cached or mocked answer must never be
    #: reported as live, so each backend declares this rather than having a
    #: caller guess from the class name.
    mode: str

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        """Return one structured response validated against ``schema``."""
        ...


class MockBackend:
    """Replays scripted responses in order — one per ``complete`` call.

    Each script item is either a ``BaseModel`` instance or a dict that is
    validated against the call's schema (so a test can feed deliberately broken
    shapes and check the pipeline rejects them).
    """

    mode = "mock"

    def __init__(self, scripted: list[BaseModel | dict]) -> None:
        self._it: Iterator[BaseModel | dict] = iter(scripted)
        self.calls: list[tuple[str, str, str]] = []  # (system, user, schema name)

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        self.calls.append((system, user, schema.__name__))
        try:
            item = next(self._it)
        except StopIteration as e:
            raise AssertionError("MockBackend ran out of scripted responses") from e
        return item if isinstance(item, schema) else schema.model_validate(item)


class OpenAIBackend:
    """Structured output via the OpenAI SDK (``chat.completions.parse``).

    ``OPENAI_API_KEY`` (and optional ``OPENAI_BASE_URL``) come from the
    environment or a repo-root ``.env``. ``temperature=None`` (the default)
    omits the parameter — reasoning models such as gpt-5-mini reject any
    explicit value. ``client`` can be injected (a stub with a
    ``chat.completions.parse`` method) so this is testable without the
    ``openai`` package installed or a network call; ``resolved_models`` records
    the API's actual ``completion.model`` per call (a model alias like
    "gpt-5-mini" can resolve to a dated snapshot — log the resolved id for
    reproducibility, contract §14).
    """

    mode = "live"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float | None = None,
        client: object | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self._client = client
        self.resolved_models: list[str] = []

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:  # pragma: no cover - only with the extra installed
                raise RuntimeError(
                    "OpenAIBackend needs the 'llm' optional dependency: pip install -e '.[llm]'"
                ) from e
            _load_dotenv()
            self._client = OpenAI()  # built once, reused for every call
        return self._client

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        client = self._get_client()
        extra = {} if self.temperature is None else {"temperature": self.temperature}
        completion = client.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=schema,
            **extra,
        )
        self.resolved_models.append(getattr(completion, "model", self.model))
        parsed = completion.choices[0].message.parsed
        if parsed is None:  # pragma: no cover
            raise RuntimeError("model refused or returned unparseable structured output")
        return parsed


class TimedBackend:
    """Wraps a backend and records the wall time of every ``complete`` call.

    ``mode`` and ``resolved_models`` delegate to the inner backend so the
    orchestrator's provenance and ``resolved_models`` bookkeeping are unchanged
    (D-071). ``calls`` holds ``(schema_name, seconds)`` in call order.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[tuple[str, float]] = []

    @property
    def mode(self) -> str:
        return self._inner.mode

    @property
    def resolved_models(self):
        return getattr(self._inner, "resolved_models", [])

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        import time

        started = time.perf_counter()
        try:
            return self._inner.complete(system, user, schema)
        finally:
            self.calls.append((schema.__name__, time.perf_counter() - started))
