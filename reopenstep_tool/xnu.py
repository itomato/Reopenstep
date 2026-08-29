from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .errors import ReopenstepError
from .fat import inspect_fat
from .util import sha256_file


CPU_TYPE_I386 = 7
CPU_TYPE_X86_64 = 0x01000007

CPU_NAMES = {
    CPU_TYPE_I386: "i386",
    CPU_TYPE_X86_64: "x86_64",
}

MACHO_MAGICS = {
    0xFEEDFACE: ("mach-o", "big", 32),
    0xCEFAEDFE: ("mach-o", "little", 32),
    0xFEEDFACF: ("mach-o", "big", 64),
    0xCFFAEDFE: ("mach-o", "little", 64),
}

FAT_MAGICS = {0xCAFEBABE, 0xBEBAFECA}


def _inspect_thin(data: bytes, offset: int = 0, size: int | None = None) -> dict[str, Any]:
    if len(data) < offset + 28:
        raise ReopenstepError("file is too short for a Mach-O header")
    magic = struct.unpack_from(">I", data, offset)[0]
    if magic not in MACHO_MAGICS:
        raise ReopenstepError(f"not a Mach-O kernel image at offset 0x{offset:x}")
    _kind, endian_name, bits = MACHO_MAGICS[magic]
    endian = ">" if endian_name == "big" else "<"
    cpu_type, cpu_subtype, file_type, ncmds, sizeofcmds, flags = struct.unpack_from(
        f"{endian}IIIIII", data, offset + 4
    )
    return {
        "format": f"mach-o-{bits}",
        "endian": endian_name,
        "cpu_type": cpu_type,
        "cpu_subtype": cpu_subtype,
        "architecture": CPU_NAMES.get(cpu_type, f"cpu-{cpu_type}"),
        "file_type": file_type,
        "ncmds": ncmds,
        "sizeofcmds": sizeofcmds,
        "flags": flags,
        "offset": offset,
        "size": size,
    }


def inspect_kernel(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReopenstepError(f"XNU kernel not found: {path}")
    data = path.read_bytes()
    if len(data) < 8:
        raise ReopenstepError(f"file is too short for a Mach-O kernel: {path}")
    magic = struct.unpack_from(">I", data, 0)[0]
    slices: list[dict[str, Any]]
    if magic in FAT_MAGICS:
        fat = inspect_fat(path)
        slices = [
            _inspect_thin(data, item["offset"], item["size"])
            for item in fat["architectures"]
        ]
        container = "fat"
    else:
        slices = [_inspect_thin(data, 0, len(data))]
        container = "thin"
    architectures = [item["architecture"] for item in slices]
    bootable_by_boote = "i386" in architectures or "x86_64" in architectures
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "container": container,
        "architectures": architectures,
        "slices": slices,
        "bootable_by_boote": bootable_by_boote,
    }


def require_boote_kernel(path: Path) -> dict[str, Any]:
    report = inspect_kernel(path)
    if not report["bootable_by_boote"]:
        raise ReopenstepError(
            f"kernel has no i386/x86_64 Mach-O slice for BootE/Chameleon: {path}"
        )
    return report
