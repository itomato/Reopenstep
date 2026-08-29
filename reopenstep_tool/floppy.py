from __future__ import annotations

from pathlib import Path

from .errors import ReopenstepError
from .util import sha256_file


FLOPPY_1440_SIZE = 1440 * 1024
FLOPPY_2880_SIZE = FLOPPY_1440_SIZE * 2


def combine_floppies(install: Path, drivers: Path, output: Path) -> dict[str, object]:
    install_data = _read_exact_floppy(install, "install")
    driver_data = _read_exact_floppy(drivers, "driver")
    combined = install_data + driver_data
    if len(combined) != FLOPPY_2880_SIZE:
        raise ReopenstepError(f"combined floppy must be 2.88MB, got {len(combined)} bytes")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_bytes() != combined:
        output.write_bytes(combined)
    return {
        "output": str(output),
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
        "install": str(install),
        "install_sha256": sha256_file(install),
        "drivers": str(drivers),
        "drivers_sha256": sha256_file(drivers),
        "layout": [
            {"source": "install", "offset": 0, "size": FLOPPY_1440_SIZE},
            {"source": "drivers", "offset": FLOPPY_1440_SIZE, "size": FLOPPY_1440_SIZE},
        ],
    }


def _read_exact_floppy(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise ReopenstepError(f"{label} floppy not found: {path}")
    data = path.read_bytes()
    if len(data) != FLOPPY_1440_SIZE:
        raise ReopenstepError(f"{label} floppy must be 1.44MB, got {len(data)} bytes: {path}")
    return data
