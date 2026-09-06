"""Provenance labels shared by LLM and deterministic interaction actions."""

VALID_MODES = frozenset({"live", "cached", "mock"})


def require_mode(mode: object) -> str:
    """Return a valid audit mode or reject a provenance wiring error."""
    if not isinstance(mode, str) or mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}, got {mode!r}")
    return mode


def mode_of_backend(backend: object) -> str:
    return require_mode(getattr(backend, "mode", None))


__all__ = ["VALID_MODES", "require_mode", "mode_of_backend"]
