from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .errors import ReopenstepError


MAGIC = b"dlV3"
LABEL_SCAN_SIZE = 32768
LABEL_EXPORT_SIZE = 7680
CHECKSUM_OFFSET = 558
DISKTAB_OFFSET = 44
SECTOR_SIZE_OFFSET = DISKTAB_OFFSET + 0x32
FRONT_OFFSET = 112
BOOT_BLOCKS_OFFSET = DISKTAB_OFFSET + 0x56
PARTITION_A_OFFSET = DISKTAB_OFFSET + 0x94
PARTITION_RECORD_SIZE = 0x40
PARTITION_TYPE_OFFSET = 0x23
PARTITION_COUNT = 8


def read_be24(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 3], "big")


def write_be24(data: bytearray, offset: int, value: int) -> None:
    if not 0 <= value <= 0xFFFFFF:
        raise ReopenstepError(f"value {value} does not fit a NeXT disk-label 24-bit field")
    data[offset:offset + 3] = value.to_bytes(3, "big")


def checksum_v3(label: bytes) -> int:
    if len(label) < CHECKSUM_OFFSET + 2 or label[:4] != MAGIC:
        raise ReopenstepError("not a complete NeXT dlV3 label")
    words = struct.unpack(f">{CHECKSUM_OFFSET // 2}H", label[:CHECKSUM_OFFSET])
    total = sum(words)
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return total


def parse_label(data: bytes, offset: int = 0) -> dict[str, Any]:
    label = data[offset:offset + CHECKSUM_OFFSET + 2]
    if len(label) < CHECKSUM_OFFSET + 2 or label[:4] != MAGIC:
        raise ReopenstepError(f"no NeXT dlV3 label at offset {offset}")
    text = lambda start, length: label[start:start + length].split(b"\0", 1)[0].decode("ascii", "replace")
    stored = struct.unpack_from(">H", label, CHECKSUM_OFFSET)[0]
    computed = checksum_v3(label)
    normalized = bytearray(label)
    struct.pack_into(">I", normalized, 4, 0)
    normalized_checksum = checksum_v3(bytes(normalized))
    partition = lambda start: {
        "base": read_be24(label, start),
        "size": read_be24(label, start + 3),
        "block_size": struct.unpack_from(">H", label, start + 6)[0],
        "fragment_size": struct.unpack_from(">H", label, start + 8)[0],
        "type": text(start + PARTITION_TYPE_OFFSET, 8),
    }
    return {
        "offset": offset, "version": "dlV3", "label_block": struct.unpack_from(">I", label, 4)[0],
        "label": text(12, 24), "drive_name": text(44, 24), "drive_type": text(68, 24),
        "sector_size": struct.unpack_from(">H", label, SECTOR_SIZE_OFFSET)[0],
        "front_porch": struct.unpack_from(">H", label, FRONT_OFFSET)[0],
        "boot_blocks": list(struct.unpack_from(">II", label, BOOT_BLOCKS_OFFSET)),
        "kernel": text(132, 24), "root_partition": chr(label[188]), "rw_partition": chr(label[189]),
        "partition_a": partition(PARTITION_A_OFFSET),
        "partition_b": partition(PARTITION_A_OFFSET + PARTITION_RECORD_SIZE),
        "checksum": stored, "computed_checksum": computed,
        "checksum_valid": stored in {computed, normalized_checksum},
        "checksum_normalized_label_block": normalized_checksum,
    }


def inspect_labels(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = handle.read(LABEL_SCAN_SIZE)
    offsets = []
    cursor = 0
    while (offset := data.find(MAGIC, cursor)) >= 0:
        offsets.append(offset)
        cursor = offset + 1
    if not offsets:
        raise ReopenstepError(f"no NeXT dlV3 label in first {LABEL_SCAN_SIZE} bytes: {path}")
    primary = parse_label(data, offsets[0])
    primary["copies"] = offsets
    root = primary["root_partition"]
    if not "a" <= root < chr(ord("a") + PARTITION_COUNT):
        raise ReopenstepError(f"invalid NeXT root partition {root!r}")
    root_offset = PARTITION_A_OFFSET + (ord(root) - ord("a")) * PARTITION_RECORD_SIZE
    root_record = partition_record(data, offsets[0] + root_offset)
    primary["root_partition_info"] = root_record
    primary["ufs_byte_offset"] = (
        primary["front_porch"] + root_record["base"]
    ) * primary["sector_size"]
    return primary


def partition_record(data: bytes, offset: int) -> dict[str, Any]:
    return {
        "base": read_be24(data, offset),
        "size": read_be24(data, offset + 3),
        "block_size": struct.unpack_from(">H", data, offset + 6)[0],
        "fragment_size": struct.unpack_from(">H", data, offset + 8)[0],
        "type": data[offset + PARTITION_TYPE_OFFSET:offset + PARTITION_TYPE_OFFSET + 8]
        .split(b"\0", 1)[0].decode("ascii", "replace"),
    }


def normalized_template(source: Path) -> bytes:
    with source.open("rb") as handle:
        data = handle.read(LABEL_SCAN_SIZE)
    offset = data.find(MAGIC)
    if offset < 0 or offset + LABEL_EXPORT_SIZE > len(data):
        raise ReopenstepError(f"cannot export a {LABEL_EXPORT_SIZE}-byte NeXT label template from {source}")
    label = bytearray(data[offset:offset + LABEL_EXPORT_SIZE])
    next_copy = label.find(MAGIC, 4)
    if next_copy >= 0:
        label[next_copy:] = b"\0" * (len(label) - next_copy)
    struct.pack_into(">I", label, 4, 0)
    struct.pack_into(">H", label, CHECKSUM_OFFSET, checksum_v3(bytes(label)))
    return bytes(label)


def update_template(label: bytes, *, front_porch: int, partition_blocks: int,
                    partition_b: tuple[int, int] | None = None) -> bytes:
    if len(label) != LABEL_EXPORT_SIZE or label[:4] != MAGIC:
        raise ReopenstepError("label template must begin with a complete dlV3 label")
    if not 0 <= front_porch <= 0xFFFF:
        raise ReopenstepError(f"front porch {front_porch} does not fit the dlV3 16-bit field")
    result = bytearray(label)
    struct.pack_into(">I", result, 4, 0)
    struct.pack_into(">H", result, FRONT_OFFSET, front_porch)
    write_be24(result, PARTITION_A_OFFSET + 3, partition_blocks)
    if partition_b is not None:
        partition_b_offset = PARTITION_A_OFFSET + PARTITION_RECORD_SIZE
        result[partition_b_offset:partition_b_offset + PARTITION_RECORD_SIZE] = result[
            PARTITION_A_OFFSET:PARTITION_A_OFFSET + PARTITION_RECORD_SIZE
        ]
        write_be24(result, partition_b_offset, partition_b[0])
        write_be24(result, partition_b_offset + 3, partition_b[1])
    struct.pack_into(">H", result, CHECKSUM_OFFSET, checksum_v3(bytes(result)))
    return bytes(result)
