#!/usr/bin/env python3
"""Disassemble named functions from a 32-bit big-endian PPC Mach-O.

Capstone is intentionally optional project tooling. Install it in a temporary
virtual environment and invoke this script with that environment's Python.
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
from pathlib import Path

try:
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
except ImportError as exc:
    raise SystemExit("capstone is required (install it in a temporary virtual environment)") from exc


LC_SEGMENT = 1


def text_section(data: bytes) -> tuple[int, int, int]:
    if data[:4] != b"\xfe\xed\xfa\xce":
        raise ValueError("expected a 32-bit big-endian Mach-O")
    _, _, _, _, command_count, _, _ = struct.unpack_from(">7I", data, 0)
    offset = 28
    for _ in range(command_count):
        command, command_size = struct.unpack_from(">2I", data, offset)
        if command == LC_SEGMENT:
            section_count = struct.unpack_from(">I", data, offset + 48)[0]
            section_offset = offset + 56
            for index in range(section_count):
                current = section_offset + index * 68
                section_name = data[current:current + 16].split(b"\0", 1)[0]
                if section_name == b"__text":
                    address, size, file_offset = struct.unpack_from(">3I", data, current + 32)
                    return address, size, file_offset
        offset += command_size
    raise ValueError("Mach-O has no __text section")


def symbols(path: Path, start: int, end: int) -> list[tuple[int, str]]:
    output = subprocess.run(
        ["nm", "-n", str(path)], check=True, text=True, capture_output=True,
    ).stdout
    found: list[tuple[int, str]] = []
    for line in output.splitlines():
        match = re.match(r"^([0-9a-fA-F]{8,16})\s+([Tt])\s+(.+)$", line)
        if match:
            address = int(match.group(1), 16)
            if start <= address < end:
                found.append((address, match.group(3)))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--match", default=".", help="regular expression matched against symbol names")
    args = parser.parse_args()
    data = args.binary.read_bytes()
    start, size, file_offset = text_section(data)
    end = start + size
    selected = symbols(args.binary, start, end)
    decoder = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    expression = re.compile(args.match)
    unique_addresses = sorted({address for address, _ in selected} | {end})
    names: dict[int, list[str]] = {}
    for address, name in selected:
        names.setdefault(address, []).append(name)
    for index, address in enumerate(unique_addresses[:-1]):
        labels = names.get(address, [])
        if not any(expression.search(label) for label in labels):
            continue
        next_address = unique_addresses[index + 1]
        begin = file_offset + address - start
        finish = file_offset + next_address - start
        print(f"\n{address:08x} {' / '.join(labels)}")
        for instruction in decoder.disasm(data[begin:finish], address):
            print(f"  {instruction.address:08x}  {instruction.mnemonic:10s} {instruction.op_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
