"""Exact structured-response cache for the P8.3 operator UI (§18.9).

The cache is deliberately below the mission pipeline: every structured LLM
call (intent, task list, dependency list, repair) is keyed by its complete
prompt context and response schema.  A miss never falls through to a live
model, and a cached answer is always exposed with ``mode = "cached"``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from llm.backend import LLMBackend

T = TypeVar("T", bound=BaseModel)

CACHE_FORMAT_VERSION = 1
PROMPT_SCHEMA_VERSION = "p12-v4"
DEFAULT_CACHE_DIR = Path("data/llm_cache")


class CacheMissError(LookupError):
    """No exact response exists for this model, prompt and schema."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cache_key(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[BaseModel],
) -> str:
    """Return the §18.9 key.

    ``system`` contains the fixed prompt plus deterministic session context;
    its hash is therefore the context hash.  The schema JSON hash and the
    explicit version pin the prompt/schema contract. ``user`` is retained
    exactly because it contains the operator utterance (or the generation
    stage's exact user payload).
    """
    if not isinstance(model, str) or not model:
        raise ValueError("cache model must be a non-empty str")
    material = {
        "model": model,
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "schema_name": schema.__name__,
        "schema_hash": _sha(_canonical_json(schema.model_json_schema())),
        "context_hash": _sha(system),
        "utterance": user,
    }
    return _sha(_canonical_json(material))


def _entry_path(directory: Path, key: str) -> Path:
    return directory / f"{key}.json"


def _read_entry(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CacheMissError(f"no cached response for key {path.stem}") from exc
    if not isinstance(payload, dict) or payload.get("cache_format_version") != 1:
        raise ValueError(f"invalid LLM cache entry: {path}")
    return payload


def _write_entry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


class CachedBackend:
    """Replay an exact prior live response; never call the network."""

    mode = "cached"

    def __init__(self, model: str, directory: str | Path = DEFAULT_CACHE_DIR) -> None:
        self.model = model
        self.directory = Path(directory)
        self.resolved_models: list[str] = []

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        key = cache_key(model=self.model, system=system, user=user, schema=schema)
        payload = _read_entry(_entry_path(self.directory, key))
        if payload.get("key") != key or payload.get("schema_name") != schema.__name__:
            raise ValueError(f"cached response metadata mismatch for key {key}")
        resolved_model = payload.get("resolved_model")
        if not isinstance(resolved_model, str) or not resolved_model:
            raise ValueError(f"cached response has no resolved model for key {key}")
        response = schema.model_validate(payload.get("response"))
        self.resolved_models.append(resolved_model)
        return response


class RecordingBackend:
    """Record successful responses from a live backend for exact replay."""

    mode = "live"

    def __init__(
        self,
        backend: LLMBackend,
        directory: str | Path = DEFAULT_CACHE_DIR,
    ) -> None:
        if getattr(backend, "mode", None) != "live":
            raise ValueError("RecordingBackend requires a live backend")
        model = getattr(backend, "model", None)
        if not isinstance(model, str) or not model:
            raise ValueError("live backend must expose a non-empty model")
        self.backend = backend
        self.model = model
        self.directory = Path(directory)

    @property
    def resolved_models(self) -> list[str]:
        return getattr(self.backend, "resolved_models", [])

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        response = self.backend.complete(system, user, schema)
        resolved_model = (
            self.resolved_models[-1] if self.resolved_models else self.model
        )
        key = cache_key(model=self.model, system=system, user=user, schema=schema)
        _write_entry(
            _entry_path(self.directory, key),
            {
                "cache_format_version": CACHE_FORMAT_VERSION,
                "key": key,
                "model": self.model,
                "resolved_model": resolved_model,
                "prompt_schema_version": PROMPT_SCHEMA_VERSION,
                "schema_name": schema.__name__,
                "response": response.model_dump(mode="json"),
            },
        )
        return response


__all__ = [
    "CACHE_FORMAT_VERSION",
    "PROMPT_SCHEMA_VERSION",
    "DEFAULT_CACHE_DIR",
    "CacheMissError",
    "CachedBackend",
    "RecordingBackend",
    "cache_key",
]
