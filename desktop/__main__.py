"""Run the native two-window console with ``python3 -m desktop``."""

from __future__ import annotations


def main() -> int:
    try:
        from desktop.app import run
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6" or (exc.name or "").startswith("PySide6."):
            raise SystemExit(
                "PySide6 is required for the desktop console. "
                "Install it with: pip install -e '.[desktop]'"
            ) from None
        raise
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
