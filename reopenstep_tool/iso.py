from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .errors import ReopenstepError


SECTOR_SIZE = 2048
EL_TORITO_ID = b"EL TORITO SPECIFICATION"


def inspect_el_torito(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReopenstepError(f"image not found: {path}")
    result: dict[str, Any] = {
        "path": str(path), "size": path.stat().st_size, "pvd": False,
        "boot_record": False, "catalog_lba": None, "catalog_valid": False,
        "bootable": False, "media_type": None, "boot_lba": None, "boot_sectors": None,
    }
    with path.open("rb") as handle:
        for lba in range(16, 64):
            handle.seek(lba * SECTOR_SIZE)
            sector = handle.read(SECTOR_SIZE)
            if len(sector) != SECTOR_SIZE:
                break
            if sector[1:6] != b"CD001" or sector[6] != 1:
                continue
            if sector[0] == 1:
                result["pvd"] = True
            elif sector[0] == 0 and sector[7:39].rstrip(b" ").startswith(EL_TORITO_ID):
                result["boot_record"] = True
                result["catalog_lba"] = struct.unpack_from("<I", sector, 71)[0]
            elif sector[0] == 255:
                break
        if result["catalog_lba"] is not None:
            handle.seek(result["catalog_lba"] * SECTOR_SIZE)
            catalog = handle.read(SECTOR_SIZE)
            if len(catalog) == SECTOR_SIZE:
                checksum = sum(struct.unpack_from("<16H", catalog, 0)) & 0xFFFF
                result["catalog_valid"] = catalog[0] == 1 and checksum == 0
                result["bootable"] = catalog[32] == 0x88
                result["media_type"] = catalog[33]
                result["boot_sectors"] = struct.unpack_from("<H", catalog, 38)[0]
                result["boot_lba"] = struct.unpack_from("<I", catalog, 40)[0]
    return result


def require_bootable(report: dict[str, Any]) -> None:
    required = ("pvd", "boot_record", "catalog_valid", "bootable")
    missing = [name for name in required if not report.get(name)]
    if missing:
        raise ReopenstepError("invalid El Torito image; failed: " + ", ".join(missing))
