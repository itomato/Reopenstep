#!/usr/bin/env python3
"""Reject BootE images whose loaded segments collide with PC firmware data."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


MH_MAGIC = 0xFEEDFACE
LC_SEGMENT = 0x1
EBDA_FLOOR = 0x9FC00


def loaded_image_end(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 28:
        raise ValueError("file is too small for a Mach-O header")

    magic, _cpu, _subtype, _filetype, command_count, command_bytes, _flags = (
        struct.unpack_from("<7I", data)
    )
    if magic != MH_MAGIC:
        raise ValueError("expected a little-endian 32-bit Mach-O image")
    if 28 + command_bytes > len(data):
        raise ValueError("Mach-O load commands extend past the file")

    offset = 28
    highest = 0
    for _ in range(command_count):
        if offset + 8 > len(data):
            raise ValueError("truncated Mach-O load command")
        command, command_size = struct.unpack_from("<2I", data, offset)
        if command_size < 8 or offset + command_size > len(data):
            raise ValueError("invalid Mach-O load command size")
        if command == LC_SEGMENT:
            if command_size < 56:
                raise ValueError("truncated LC_SEGMENT command")
            vmaddr, vmsize = struct.unpack_from("<2I", data, offset + 24)
            highest = max(highest, vmaddr + vmsize)
        offset += command_size

    if not highest:
        raise ValueError("Mach-O image has no loadable segments")
    return highest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--ceiling", type=lambda value: int(value, 0), default=EBDA_FLOOR)
    args = parser.parse_args()

    try:
        image_end = loaded_image_end(args.image)
    except ValueError as error:
        raise SystemExit(f"cannot verify BootE layout: {error}") from error

    if image_end > args.ceiling:
        raise SystemExit(
            f"BootE ends at {image_end:#x}, overlapping the PC EBDA floor "
            f"at {args.ceiling:#x}"
        )
    print(
        f"BootE loaded-image ceiling: {image_end:#x} "
        f"({args.ceiling - image_end:#x} bytes below EBDA)"
    )


if __name__ == "__main__":
    main()
