from __future__ import annotations

import shutil
from pathlib import Path

from .errors import ReopenstepError
from .nextlabel import inspect_labels, update_template
from .util import sha256_file


UFS_MAGIC = b"\x00\x01\x19\x54"


def master_ufs_disk(*, ufs: Path, label_template: Path, boot_source: Path, output: Path,
                    size_bytes: int, front_porch_blocks: int = 80) -> dict[str, object]:
    if size_bytes <= 0 or size_bytes % 512:
        raise ReopenstepError("disk size must be a positive multiple of 512 bytes")
    for path, description in ((ufs, "UFS payload"), (label_template, "label template"),
                              (boot_source, "boot-block source")):
        if not path.is_file():
            raise ReopenstepError(f"{description} not found: {path}")
    sector_size = 2048
    ufs_offset = front_porch_blocks * sector_size
    if ufs_offset + ufs.stat().st_size > size_bytes:
        raise ReopenstepError("UFS payload does not fit after the front porch")
    if boot_source.stat().st_size < ufs_offset:
        raise ReopenstepError("boot-block source is shorter than the configured front porch")
    source_porch = boot_source.read_bytes()[:ufs_offset]
    source_label = source_porch.find(b"dlV3")
    if source_label >= 0 and b"removable_rw_scsi" in source_porch[source_label:source_label + 160]:
        raise ReopenstepError(
            "the supplied boot source is an optical NeXT image; hard-disk mastering requires "
            "native boot0/boot1/boot2 blocks from BuildDisk or the OpenStep disk utility"
        )
    label = update_template(
        label_template.read_bytes(),
        front_porch=front_porch_blocks,
        partition_blocks=(ufs.stat().st_size + sector_size - 1) // sector_size,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.truncate(size_bytes)
    with output.open("r+b") as handle:
        handle.seek(0)
        handle.write(label)
        # Preserve the source's real boot porch, including boot code and the
        # NeXT disk-label location. This is what makes the output installation
        # media rather than a UFS payload container.
        handle.seek(0)
        with boot_source.open("rb") as source:
            handle.write(source.read(ufs_offset))
        porch = source_porch
        label_offsets: list[int] = []
        cursor = 0
        while (found := porch.find(b"dlV3", cursor)) >= 0:
            label_offsets.append(found)
            cursor = found + 1
        if not label_offsets:
            raise ReopenstepError("boot-block source has no NeXT dlV3 label in its front porch")
        for label_offset in label_offsets:
            handle.seek(label_offset)
            handle.write(label)
        handle.seek(ufs_offset)
        with ufs.open("rb") as source:
            shutil.copyfileobj(source, handle)
    report = inspect_labels(output)
    if report["ufs_byte_offset"] != ufs_offset:
        raise ReopenstepError("disk label/UFS offset verification failed")
    with output.open("rb") as handle:
        handle.seek(ufs_offset)
        probe = handle.read(2 * 1024 * 1024)
    if UFS_MAGIC not in probe:
        raise ReopenstepError("UFS superblock magic was not found in mastered payload")
    return {
        "output": str(output), "size": size_bytes, "sha256": sha256_file(output),
        "ufs": str(ufs), "ufs_sha256": sha256_file(ufs),
        "ufs_offset": ufs_offset, "front_porch_blocks": front_porch_blocks,
        "label": report, "boot_source": str(boot_source),
        "bootable_candidate": True,
    }
