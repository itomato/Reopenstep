from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .errors import ReopenstepError


FAT_MAGIC = 0xCAFEBABE
CPU_NAMES = {6: "m68k", 7: "i386", 11: "hppa", 14: "sparc"}
QUAD_ARCHES = {"m68k", "i386", "hppa", "sparc"}


def inspect_fat(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(8)
        if len(header) != 8:
            raise ReopenstepError(f"file is too short for a Mach-O fat header: {path}")
        magic, count = struct.unpack(">II", header)
        if magic != FAT_MAGIC:
            raise ReopenstepError(f"not a big-endian Mach-O fat binary: {path}")
        if count < 1 or count > 32:
            raise ReopenstepError(f"implausible fat architecture count {count}: {path}")
        records = handle.read(count * 20)
    if len(records) != count * 20:
        raise ReopenstepError(f"truncated fat architecture table: {path}")
    architectures = []
    size = path.stat().st_size
    for index in range(count):
        cpu, subtype, offset, slice_size, align = struct.unpack_from(">IIIII", records, index * 20)
        if offset + slice_size > size:
            raise ReopenstepError(f"architecture slice {index} extends beyond {path}")
        architectures.append({
            "cpu_type": cpu, "cpu_subtype": subtype, "architecture": CPU_NAMES.get(cpu, f"cpu-{cpu}"),
            "offset": offset, "size": slice_size, "alignment_power": align,
        })
    return {"path": str(path), "architectures": architectures, "count": count}


def require_quad_fat(report: dict[str, Any]) -> None:
    actual = {item["architecture"] for item in report["architectures"]}
    if actual != QUAD_ARCHES or report["count"] != 4:
        missing = sorted(QUAD_ARCHES - actual)
        extra = sorted(actual - QUAD_ARCHES)
        raise ReopenstepError(f"not quad-fat; missing={missing or 'none'} extra={extra or 'none'}")
