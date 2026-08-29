from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import ReopenstepError
from .rhapsody import inspect_native_boot


UFS1_MAGIC = 0x00011954
UFS1_MAGIC_OFFSET = 0x55C
SUPERBLOCK_SAMPLE_SIZE = 0x2000
PLAUSIBLE_UFS_BLOCK_SIZES = {4096, 8192, 16384, 32768, 65536}
PLAUSIBLE_UFS_FRAGMENT_SIZES = {512, 1024, 2048, 4096, 8192}


@dataclass(frozen=True)
class UfsCandidate:
    byte_order: str
    magic_offset: int
    superblock_offset: int
    fs_bsize: int
    fs_fsize: int
    fs_frag: int
    plausible: bool
    source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "byte_order": self.byte_order,
            "magic_offset": self.magic_offset,
            "superblock_offset": self.superblock_offset,
            "fs_bsize": self.fs_bsize,
            "fs_fsize": self.fs_fsize,
            "fs_frag": self.fs_frag,
            "plausible": self.plausible,
        }


def _u32(data: bytes, offset: int, byte_order: str) -> int:
    fmt = "<I" if byte_order == "little" else ">I"
    return struct.unpack_from(fmt, data, offset)[0]


def _candidate_at(data: bytes, magic_offset: int, byte_order: str, *,
                  base_offset: int = 0, source: str = "image") -> UfsCandidate:
    superblock_offset = magic_offset - UFS1_MAGIC_OFFSET
    fs_bsize = 0
    fs_fsize = 0
    fs_frag = 0
    plausible = False
    if 0 <= superblock_offset and superblock_offset + UFS1_MAGIC_OFFSET + 4 <= len(data):
        fs_bsize = _u32(data, superblock_offset + 0x30, byte_order)
        fs_fsize = _u32(data, superblock_offset + 0x34, byte_order)
        fs_frag = _u32(data, superblock_offset + 0x38, byte_order)
        plausible = (
            fs_bsize in PLAUSIBLE_UFS_BLOCK_SIZES
            and fs_fsize in PLAUSIBLE_UFS_FRAGMENT_SIZES
            and fs_bsize >= fs_fsize
            and fs_bsize % fs_fsize == 0
            and fs_frag == fs_bsize // fs_fsize
        )
    return UfsCandidate(
        byte_order=byte_order,
        magic_offset=base_offset + magic_offset,
        superblock_offset=base_offset + superblock_offset,
        fs_bsize=fs_bsize,
        fs_fsize=fs_fsize,
        fs_frag=fs_frag,
        plausible=plausible,
        source=source,
    )


def scan_ufs1_superblocks(data: bytes, *, base_offset: int = 0,
                          source: str = "image") -> list[UfsCandidate]:
    candidates: list[UfsCandidate] = []
    for magic_bytes, byte_order in (
        (struct.pack("<I", UFS1_MAGIC), "little"),
        (struct.pack(">I", UFS1_MAGIC), "big"),
    ):
        offset = data.find(magic_bytes)
        while offset != -1:
            candidates.append(_candidate_at(
                data, offset, byte_order, base_offset=base_offset, source=source,
            ))
            offset = data.find(magic_bytes, offset + 1)
    return sorted(candidates, key=lambda candidate: candidate.magic_offset)


def ascii_strings(data: bytes, *, min_length: int = 4) -> list[dict[str, object]]:
    strings: list[dict[str, object]] = []
    start: int | None = None
    for index, value in enumerate(data + b"\0"):
        if 0x20 <= value <= 0x7E:
            if start is None:
                start = index
            continue
        if start is not None and index - start >= min_length:
            strings.append({"offset": start, "value": data[start:index].decode("ascii")})
        start = None
    return strings


def _read_slice(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(offset)
        return handle.read(size)


def analyze_boot_image(image: Path, *, max_full_scan_bytes: int | None = None) -> dict[str, object]:
    if not image.is_file():
        raise ReopenstepError(f"boot image not found: {image}")
    boot = inspect_native_boot(image)
    image_size = int(boot["size"])
    scan_size = image_size if max_full_scan_bytes is None else min(image_size, max_full_scan_bytes)
    boot2_offset = int(boot["boot2_byte_offset"])
    boot2_size = int(boot["boot2_size"])
    boot2 = _read_slice(image, boot2_offset, min(boot2_size, max(0, image_size - boot2_offset)))
    image_prefix = _read_slice(image, 0, scan_size)
    ufs_candidates = [
        candidate.as_dict()
        for candidate in scan_ufs1_superblocks(image_prefix, source="image-prefix")
    ]
    boot2_candidates = [
        candidate.as_dict()
        for candidate in scan_ufs1_superblocks(boot2, base_offset=boot2_offset, source="boot2")
    ]
    strings = ascii_strings(boot2)
    interesting_terms = (
        "Bad superblock", "bad root inode", "directory read error", "mach_kernel",
        "System.config", "Default.table", "sarld", "/private/Drivers/i386",
    )
    interesting_strings = [
        item for item in strings
        if any(term in str(item["value"]) for term in interesting_terms)
    ]
    return {
        "image": str(image),
        "size": image_size,
        "sha256": _sha256_file(image),
        "boot": boot,
        "ufs1_magic": {
            "value": UFS1_MAGIC,
            "superblock_field_offset": UFS1_MAGIC_OFFSET,
            "native_intel_encoding": struct.pack("<I", UFS1_MAGIC).hex(),
            "openstep_swapped_encoding": struct.pack(">I", UFS1_MAGIC).hex(),
        },
        "scan_size": scan_size,
        "ufs_candidates": ufs_candidates,
        "boot2_ufs_constants": boot2_candidates,
        "boot2_strings": interesting_strings,
        "inferences": [
            "RDR/i386 boot2 contains the little-endian UFS1 magic constant used by BSD 4.4 UFS.",
            "A plausible RDR/i386 reader must parse native little-endian superblocks, not OPENSTEP's swapped UFS layout.",
            "The loader validates fs_magic at superblock offset 0x55c and requires a nonzero plausible fs_fsize at offset 0x34.",
        ],
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
