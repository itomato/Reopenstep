#!/usr/bin/env python3
"""Emit reproducible sector/offset evidence from an OpenStep boot floppy."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SECTOR = 512
MARKERS = (
    b"OPENSTEP boot1", b"sarld", b"mach_kernel", b"mach_kernel.rcz",
    b"/private/Drivers/i386", b"Prompt For Driver Disk", b"Install Mode",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = args.image.read_bytes()
    hits = []
    for marker in MARKERS:
        start = 0
        while True:
            offset = data.find(marker, start)
            if offset < 0:
                break
            hits.append({
                "marker": marker.decode("ascii"),
                "byte_offset": offset,
                "sector": offset // SECTOR,
                "offset_in_sector": offset % SECTOR,
            })
            start = offset + 1
    report = {
        "image": str(args.image),
        "size": len(data),
        "sectors": len(data) // SECTOR,
        "sha256": hashlib.sha256(data).hexdigest(),
        "boot_signature": data[510:512].hex() if len(data) >= 512 else None,
        "markers": sorted(hits, key=lambda item: item["byte_offset"]),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
