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
    def complete(self, system: str, user: str, schema: type[T]) -> T:
        """Return one structured response validated against ``schema``."""
        ...


class MockBackend:
    """Replays scripted responses in order — one per ``complete`` call.

    Each script item is either a ``BaseModel`` instance or a dict that is
    validated against the call's schema (so a test can feed deliberately broken
    shapes and check the pipeline rejects them).
    """

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
    explicit value.
    """

    def __init__(
        self, model: str = DEFAULT_MODEL, temperature: float | None = None
    ) -> None:
        self.model = model
        self.temperature = temperature

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - only with the extra installed
            raise RuntimeError(
                "OpenAIBackend needs the 'llm' optional dependency: pip install -e '.[llm]'"
            ) from e

        _load_dotenv()
        client = OpenAI()
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
        parsed = completion.choices[0].message.parsed
        if parsed is None:  # pragma: no cover
            raise RuntimeError("model refused or returned unparseable structured output")
        return parsed
