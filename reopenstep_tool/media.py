from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .iso import inspect_el_torito
from .nextlabel import inspect_labels
from .util import sha256_file


FLOPPY_SIZES = {1_474_560: "1.44MB", 2_949_120: "2.88MB"}


def inspect_media(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    report: dict[str, Any] = {
        "path": str(path), "size": size, "sha256": sha256_file(path),
        "kind": "unknown", "markers": [],
    }
    with path.open("rb") as handle:
        head = handle.read(64 * 2048)
    if len(head) >= 17 * 2048 + 7 and head[16 * 2048 + 1:16 * 2048 + 6] == b"CD001":
        report["kind"] = "iso9660"
        report["eltorito"] = inspect_el_torito(path)
    elif size in FLOPPY_SIZES:
        report["kind"] = "floppy"
        report["capacity"] = FLOPPY_SIZES[size]
        report["mbr_signature"] = head[510:512] == b"\x55\xaa"
    elif len(head) >= 8:
        magic_be = struct.unpack_from(">I", head, 0)[0]
        report["disklabel_magic_be"] = f"0x{magic_be:08x}"
        try:
            report["next_label"] = inspect_labels(path)
            report["kind"] = "next-raw-cd"
        except Exception:
            pass
    for marker in (b"OPENSTEP boot1", b"mach_kernel", b"4.3BSD", b"NeXT"):
        if marker in head:
            report["markers"].append(marker.decode("ascii"))
    return report
