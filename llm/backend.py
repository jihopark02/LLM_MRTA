"""LLM backend abstraction (RESEARCH_CONTRACT.md §12, §14 PROVENANCE).

Only the *pattern* of a structured-output wrapper is reused from LLM_CBBA
(``llm/backends.py``); that code is OpenAI-specific and is not ported. The real
backend here targets the Anthropic SDK. Every pipeline test uses ``MockBackend``
so the P5 gate needs no network and no API key.
"""

from collections.abc import Iterator
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Default model: contract does not pin one; the Anthropic skill's default.
DEFAULT_MODEL = "claude-opus-5"


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


class AnthropicBackend:
    """Structured output via the Anthropic SDK (``client.messages.parse``)."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 8000) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - exercised only with the extra installed
            raise RuntimeError(
                "AnthropicBackend needs the 'llm' optional dependency: pip install -e '.[llm]'"
            ) from e

        client = anthropic.Anthropic()
        message = client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema.model_json_schema()}},
        )
        parsed = message.parsed
        if parsed is None:  # pragma: no cover
            raise RuntimeError("model returned no parseable structured output")
        return schema.model_validate(parsed)
