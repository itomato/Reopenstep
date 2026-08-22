from __future__ import annotations

from pathlib import Path

from .errors import ReopenstepError
from .util import executable


def command(config: Path, *, binary: str | None = None) -> list[str]:
    emulator = binary or executable("86Box", "86box")
    if not emulator:
        raise ReopenstepError("86Box is required; install it or pass --binary")
    if not config.is_file():
        raise ReopenstepError(f"86Box config not found: {config}")
    return [emulator, "-C", str(config)]
