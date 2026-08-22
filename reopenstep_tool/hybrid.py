from __future__ import annotations

import shutil
import struct
import tempfile
from pathlib import Path

from .errors import ReopenstepError
from .iso import SECTOR_SIZE, inspect_el_torito, require_bootable
from .nextlabel import normalized_template, update_template
from .util import executable, run, sha256_file


LABEL_SIZE = 7680


def extract_raw_cd(source: Path, ufs_output: Path, label_output: Path, front_porch_blocks: int) -> dict[str, object]:
    if front_porch_blocks < 1:
        raise ReopenstepError("front porch must be at least one 2048-byte block")
    skip = front_porch_blocks * SECTOR_SIZE
    if not source.is_file() or source.stat().st_size <= skip:
        raise ReopenstepError(f"raw CD is missing or smaller than its front porch: {source}")
    ufs_output.parent.mkdir(parents=True, exist_ok=True)
    label_output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle:
        input_handle.seek(skip)
        with ufs_output.open("wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    label_output.write_bytes(normalized_template(source))
    return {
        "source": str(source), "front_porch_blocks": front_porch_blocks,
        "ufs": str(ufs_output), "ufs_size": ufs_output.stat().st_size, "ufs_sha256": sha256_file(ufs_output),
        "label": str(label_output), "label_size": LABEL_SIZE, "label_sha256": sha256_file(label_output),
    }


def label_candidates(label: bytes, value: int) -> dict[str, list[int]]:
    if len(label) != LABEL_SIZE:
        raise ReopenstepError(f"NeXT label template must be {LABEL_SIZE} bytes")
    result: dict[str, list[int]] = {}
    for name, fmt in (("u16be", ">H"), ("u16le", "<H"), ("u32be", ">I"), ("u32le", "<I")):
        try:
            needle = struct.pack(fmt, value)
        except struct.error:
            result[name] = []
            continue
        result[name] = [offset for offset in range(0, len(label) - len(needle) + 1) if label[offset:offset + len(needle)] == needle]
    return result


def _directory_records(data: bytes):
    index = 0
    while index < len(data):
        length = data[index]
        if length == 0:
            index = ((index // SECTOR_SIZE) + 1) * SECTOR_SIZE
            continue
        record = data[index:index + length]
        if len(record) < 34:
            break
        yield {
            "extent": struct.unpack_from("<I", record, 2)[0],
            "size": struct.unpack_from("<I", record, 10)[0],
            "flags": record[25],
            "name": record[33:33 + record[32]],
        }
        index += length


def iso_root_extent(path: Path, filename: str) -> tuple[int, int]:
    targets = {filename.upper().encode("ascii"), (filename.upper() + ";1").encode("ascii")}
    with path.open("rb") as handle:
        handle.seek(16 * SECTOR_SIZE)
        pvd = handle.read(SECTOR_SIZE)
        if len(pvd) != SECTOR_SIZE or pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise ReopenstepError(f"no primary ISO volume descriptor in {path}")
        extent = struct.unpack_from("<I", pvd, 158)[0]
        size = struct.unpack_from("<I", pvd, 166)[0]
        handle.seek(extent * SECTOR_SIZE)
        directory = handle.read(size)
    for record in _directory_records(directory):
        if record["name"] in targets:
            return record["extent"], record["size"]
    raise ReopenstepError(f"could not locate root file {filename} in {path}")


def iso_path_extent(path: Path, iso_path: str) -> tuple[int, int]:
    components = [component for component in iso_path.split("/") if component]
    with path.open("rb") as handle:
        handle.seek(16 * SECTOR_SIZE)
        pvd = handle.read(SECTOR_SIZE)
        if len(pvd) != SECTOR_SIZE or pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise ReopenstepError(f"no primary ISO volume descriptor in {path}")
        extent = struct.unpack_from("<I", pvd, 158)[0]
        size = struct.unpack_from("<I", pvd, 166)[0]
        for index, component in enumerate(components):
            handle.seek(extent * SECTOR_SIZE)
            directory = handle.read(size)
            targets = {component.upper().encode("ascii"), (component.upper() + ";1").encode("ascii")}
            match = next((record for record in _directory_records(directory) if record["name"] in targets), None)
            if match is None:
                raise ReopenstepError(f"could not locate {iso_path} in {path}")
            extent, size = int(match["extent"]), int(match["size"])
            if index < len(components) - 1 and not (int(match["flags"]) & 2):
                raise ReopenstepError(f"non-directory component in ISO path {iso_path}: {component}")
    return extent, size


def patch_label(label: bytes, offset: int, blocks: int, field_format: str) -> bytes:
    if len(label) != LABEL_SIZE:
        raise ReopenstepError(f"NeXT label template must be {LABEL_SIZE} bytes")
    formats = {"u16be": ">H", "u16le": "<H", "u32be": ">I", "u32le": "<I"}
    if field_format not in formats:
        raise ReopenstepError(f"unsupported label field format: {field_format}")
    result = bytearray(label)
    try:
        struct.pack_into(formats[field_format], result, offset, blocks)
    except (struct.error, OverflowError) as exc:
        raise ReopenstepError(f"cannot patch label offset {offset} with block {blocks}") from exc
    return bytes(result)


def build_iso_tree(stage: Path, boot_relative: Path, output: Path, volume: str) -> None:
    if tool := executable("xorriso"):
        run([tool, "-as", "mkisofs", "-r", "-J", "-l", "-iso-level", "3", "-V", volume,
             "-c", "boot/boot.catalog", "-b", boot_relative.as_posix(), "-o", str(output), str(stage)])
        return
    if tool := executable("genisoimage", "mkisofs"):
        run([tool, "-r", "-J", "-V", volume, "-c", "boot/boot.catalog", "-b", boot_relative.as_posix(),
             "-o", str(output), str(stage)])
        return
    if tool := executable("hdiutil"):
        # hdiutil takes an external boot image path and chooses floppy emulation from its size.
        run([tool, "makehybrid", "-iso", "-joliet", "-iso-volume-name", volume,
             "-eltorito-boot", str(stage / boot_relative), "-ov", "-o", str(output), str(stage)])
        generated = output.with_suffix(output.suffix + ".iso")
        if not output.exists() and generated.exists():
            generated.replace(output)
        # hdiutil 724.80.1 emits a zero sector-count for 2.88 MB floppy
        # emulation. SeaBIOS does not transfer boot sector zero in that case.
        report = inspect_el_torito(output)
        if report["media_type"] == 3 and report["boot_sectors"] == 0:
            with output.open("r+b") as handle:
                handle.seek(int(report["catalog_lba"]) * SECTOR_SIZE + 38)
                handle.write(struct.pack("<H", 1))
        return
    raise ReopenstepError("an ISO builder is required (xorriso, mkisofs, genisoimage, or hdiutil)")


def wrap_ufs(
    *, ufs: Path, boot_image: Path, label_template: Path, label_offset: int,
    label_format: str, output: Path, volume: str = "REOPENSTEP42",
    developer_ufs: Path | None = None,
) -> dict[str, object]:
    for path, label in ((ufs, "mastered UFS"), (boot_image, "boot image"), (label_template, "label template")):
        if not path.is_file():
            raise ReopenstepError(f"{label} not found: {path}")
    if developer_ufs is not None and not developer_ufs.is_file():
        raise ReopenstepError(f"Developer UFS not found: {developer_ufs}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reopenstep-wrap-") as temp:
        stage = Path(temp) / "stage"
        stage.mkdir(parents=True)
        # Keep the boot image lexically first. Some legacy BIOS paths fail to
        # load a floppy-emulation image placed hundreds of thousands of LBAs
        # into a full OPENSTEP disc.
        staged_boot = stage / "000BOOT.IMG"
        shutil.copy2(boot_image, staged_boot)
        hdiutil_only = executable("hdiutil") is not None and executable("xorriso", "genisoimage", "mkisofs") is None
        payload_name = "OPENSTEP42CD.UFS"
        developer_name = "OPENSTEP42DEV.UFS"
        if developer_ufs is not None and hdiutil_only:
            # hdiutil places a root-level data file before the contents of a
            # subdirectory. This keeps partition a inside dlV3's 16-bit porch
            # range regardless of the relative User/Developer media sizes.
            developer_dir = stage / "DEVELOPER"
            developer_dir.mkdir()
            staged_developer = developer_dir / developer_name
            shutil.copy2(developer_ufs, staged_developer)
        shutil.copy2(ufs, stage / payload_name)
        if developer_ufs is not None and not hdiutil_only:
            shutil.copy2(developer_ufs, stage / developer_name)
        build_iso_tree(stage, staged_boot.relative_to(stage), output, volume)
    payload_lba, payload_size = iso_root_extent(output, payload_name)
    developer_lba = developer_size = None
    if developer_ufs is not None:
        developer_path = f"DEVELOPER/{developer_name}" if hdiutil_only else developer_name
        developer_lba, developer_size = iso_path_extent(output, developer_path)
    label_bytes = label_template.read_bytes()
    if label_bytes[:4] == b"dlV3" and label_offset == 112 and label_format == "u16be":
        partition_b = None if developer_lba is None else (
            developer_lba - payload_lba, (developer_ufs.stat().st_size + SECTOR_SIZE - 1) // SECTOR_SIZE)
        label = update_template(label_bytes, front_porch=payload_lba,
            partition_blocks=(payload_size + SECTOR_SIZE - 1) // SECTOR_SIZE, partition_b=partition_b)
    else:
        label = patch_label(label_bytes, label_offset, payload_lba, label_format)
    with output.open("r+b") as handle:
        handle.seek(0)
        handle.write(label)
    el_torito = inspect_el_torito(output)
    require_bootable(el_torito)
    return {
        "output": str(output), "sha256": sha256_file(output), "ufs": str(ufs),
        "ufs_sha256": sha256_file(ufs), "ufs_lba": payload_lba, "ufs_size": payload_size,
        "boot_image": str(boot_image), "boot_image_sha256": sha256_file(boot_image),
        "label_offset": label_offset, "label_format": label_format, "eltorito": el_torito,
        "developer_ufs": str(developer_ufs) if developer_ufs else None,
        "developer_ufs_lba": developer_lba, "developer_ufs_size": developer_size,
    }
