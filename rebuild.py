#!/usr/bin/env python3
"""
Build OpenStep 4.2 El Torito test images and fuller rebuilt User images.

This script supports three practical paths:

1. Minimal boot testing
   - Build a tiny El Torito ISO around a supplied raw boot image.

2. Tree-based rebuilds
   - Extract a normal ISO-9660 base tree and rebuild around it.

3. Raw OpenStep CD wrapping
   - Take a raw OpenStep/NeXT CD image that is not ISO-9660.
   - Extract its UFS payload by skipping the front porch.
   - Place that UFS blob into a new El Torito ISO.
   - Locate where that UFS blob landed in the new ISO.
   - Optionally patch a NeXT block-0 label overlay so its front-porch value
     points at the landed UFS payload.

Notes
-----
- The supplied OpenStep floppy images are not DOS/FAT floppies. They carry
  NeXT boot code and UFS-style content.
- This script does not attempt to synthesize a fresh bootable 2.88MB NeXT
  floppy image from scratch. Use a known-good raw boot image such as F288.img.
- The label-patching support here is intentionally conservative: it patches the
  front-porch field in a copied label blob when told where that field lives.
  That is enough for the common raw-CD wrapping experiment, but it does not try
  to understand every possible disklabel variant automatically.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Optional

SECTOR_SIZE = 2048
EL_TORITO_ID = b"EL TORITO SPECIFICATION"
DEFAULT_VOLUME_ID = "OPENSTEP42"
DEFAULT_BOOT_DIR = "boot"
DEFAULT_DRIVER_DIR = "drivers/floppies"
DEFAULT_PATCH_DIR = "patches"
DEFAULT_USER_DIR = "user"
DEFAULT_UFS_FILENAME = "OPENSTEP42CD.UFS"
EXPECTED_LABEL_OVERLAY_SIZE = 7680
KNOWN_FLOPPY_SIZES = {1474560: "1.44MB", 2949120: "2.88MB"}
DEFAULT_Y2K_ISO_URL = "https://juddy.org/Openstep/NSOSY2K.iso"
DEFAULT_Y2K_ISO_CACHE = "NSOSY2K.iso"


class BuildError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[+] {message}")


def warn(message: str) -> None:
    print(f"[!] {message}", file=sys.stderr)


def which_any(*names: str) -> Optional[str]:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    log("Running: " + " ".join(cmd))
    try:
        subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"Command failed with exit code {exc.returncode}: {' '.join(cmd)}") from exc


def ensure_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise BuildError(f"{label} not found: {path}")


def ensure_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise BuildError(f"{label} not found: {path}")


def normalize_install_floppy(source: Path, dest_dir: Path) -> Path:
    ensure_file(source, "Install floppy")
    if source.suffix.lower() != ".zip":
        out = dest_dir / source.name
        shutil.copy2(source, out)
        return out

    with zipfile.ZipFile(source) as zf:
        members = [
            m for m in zf.infolist()
            if not m.is_dir() and not Path(m.filename).name.startswith("._")
        ]
        if len(members) != 1:
            names = ", ".join(m.filename for m in members) or "<none>"
            raise BuildError(f"Expected exactly one image inside {source}, found: {names}")
        member = members[0]
        out = dest_dir / Path(member.filename).name
        with zf.open(member) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return out


def resolve_boot_image(boot_image: Optional[Path], install_floppy: Optional[Path], dest_dir: Path) -> Path:
    if boot_image is not None:
        ensure_file(boot_image, "Boot image")
        out = dest_dir / boot_image.name
        shutil.copy2(boot_image, out)
        return out
    if install_floppy is not None:
        return normalize_install_floppy(install_floppy, dest_dir)
    raise BuildError("Provide either --boot-image or --install-floppy")


def probe_boot_image(image_path: Path) -> dict[str, object]:
    ensure_file(image_path, "Boot image")
    data = image_path.read_bytes()
    size = len(data)
    head = data[:4096]
    ascii_markers = []
    for marker in [
        b"OPENSTEP boot1",
        b"4.3BSD",
        b"mach_kernel",
        b"sarld",
        b"Floppy Drive-512",
        b"removable_rw_floppy",
    ]:
        if marker in head or marker in data:
            ascii_markers.append(marker.decode("ascii", errors="ignore"))
    return {
        "path": str(image_path),
        "size": size,
        "size_label": KNOWN_FLOPPY_SIZES.get(size, "unknown"),
        "has_mbr_signature": data[510:512] == b"\x55\xAA" if len(data) >= 512 else False,
        "markers": ascii_markers,
    }


def extract_source_iso(base_iso: Path, out_dir: Path) -> None:
    ensure_file(base_iso, "Base ISO")
    xorriso = which_any("xorriso")
    bsdtar = which_any("bsdtar")
    sevenz = which_any("7z", "7za")

    if xorriso:
        run([xorriso, "-osirrox", "on", "-indev", str(base_iso), "-extract", "/", str(out_dir)])
        return
    if bsdtar:
        run([bsdtar, "-C", str(out_dir), "-xf", str(base_iso)])
        return
    if sevenz:
        run([sevenz, "x", str(base_iso), f"-o{out_dir}"])
        return
    raise BuildError("No extractor found. Install xorriso, bsdtar, or 7z.")


def extract_raw_cd_ufs(base_raw_cd: Path, out_file: Path, front_porch_blocks: int) -> Path:
    ensure_file(base_raw_cd, "Base raw CD")
    if front_porch_blocks < 0:
        raise BuildError("front porch blocks must be non-negative")
    skip_bytes = front_porch_blocks * SECTOR_SIZE
    size = base_raw_cd.stat().st_size
    if skip_bytes >= size:
        raise BuildError(f"front porch skip {skip_bytes} is beyond end of {base_raw_cd}")
    with open(base_raw_cd, "rb") as src, open(out_file, "wb") as dst:
        src.seek(skip_bytes)
        shutil.copyfileobj(src, dst)
    return out_file


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path, overwrite: bool = True) -> None:
    ensure_dir(src, f"Directory to copy ({src})")
    for root, _, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_root = dst / rel
        target_root.mkdir(parents=True, exist_ok=True)
        for name in files:
            s = Path(root) / name
            d = target_root / name
            if d.exists() and not overwrite:
                continue
            shutil.copy2(s, d)


def merge_named_payload(payload_dir: Path, stage_dir: Path, payload_name: str, fallback_parent: str) -> None:
    ensure_dir(payload_dir, f"{payload_name} payload")
    root_payload = payload_dir / "root"
    if root_payload.is_dir():
        log(f"Merging {payload_name} payload root/ into staged CD tree")
        copy_tree(root_payload, stage_dir, overwrite=True)
    else:
        target = stage_dir / fallback_parent / payload_name
        log(f"Placing {payload_name} payload under {target}")
        copy_tree(payload_dir, target, overwrite=True)


def merge_required_root_payload(payload_dir: Path, stage_dir: Path, payload_name: str) -> None:
    ensure_dir(payload_dir, f"{payload_name} payload")
    root_payload = payload_dir / "root"
    if not root_payload.is_dir():
        raise BuildError(f"{payload_name} payload must contain a top-level root/ directory: {payload_dir}")
    log(f"Merging required {payload_name} root/ into staged CD tree")
    copy_tree(root_payload, stage_dir, overwrite=True)


def inject_driver_floppies(driver_floppies: Iterable[Path], stage_dir: Path) -> None:
    target_dir = stage_dir / DEFAULT_DRIVER_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    for src in driver_floppies:
        ensure_file(src, "Driver floppy")
        copy_file(src, target_dir / src.name)


def merge_patch_isos(patch_isos: Iterable[Path], stage_dir: Path, work_dir: Path) -> None:
    for iso in patch_isos:
        ensure_file(iso, "Patch ISO")
        extract_dir = work_dir / f"patch_iso_{iso.stem}"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        log(f"Extracting patch ISO: {iso}")
        extract_source_iso(iso, extract_dir)
        log(f"Merging patch ISO contents from {iso}")
        copy_tree(extract_dir, stage_dir, overwrite=True)


def apply_overlays(overlays: Iterable[Path], stage_dir: Path) -> None:
    for overlay in overlays:
        ensure_dir(overlay, f"Overlay directory ({overlay})")
        log(f"Applying overlay: {overlay}")
        copy_tree(overlay, stage_dir, overwrite=True)


def write_manifest(
    stage_dir: Path,
    boot_image: Path,
    driver_floppies: list[Path],
    user_payload: Optional[Path],
    patch_payload: Optional[Path],
    patch_isos: list[Path],
    driver_payload: Optional[Path],
    overlays: list[Path],
    label_overlay: Optional[Path],
    raw_cd_source: Optional[Path],
    raw_cd_ufs_name: Optional[str],
) -> None:
    manifest = stage_dir / "REOPENSTEP_BUILD_MANIFEST.txt"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        try:
            manifest.chmod(0o644)
        except OSError:
            warn(f"Could not adjust permissions on existing manifest: {manifest}")
    lines = [
        "Rebuilt OpenStep 4.2 El Torito image",
        "",
        f"Boot image: {boot_image.name}",
        f"Raw CD source: {raw_cd_source if raw_cd_source else '<none>'}",
        f"Wrapped UFS blob: {raw_cd_ufs_name if raw_cd_ufs_name else '<none>'}",
        "Driver floppies:",
    ]
    lines.extend(f"  - {p.name}" for p in driver_floppies)
    if not driver_floppies:
        lines.append("  - <none>")
    lines.append("")
    lines.append(f"User payload: {user_payload if user_payload else '<none>'}")
    lines.append(f"Patch payload: {patch_payload if patch_payload else '<none>'}")
    lines.append("Patch ISOs:")
    if patch_isos:
        lines.extend(f"  - {p}" for p in patch_isos)
    else:
        lines.append("  - <none>")
    lines.append(f"Driver payload: {driver_payload if driver_payload else '<none>'}")
    lines.append(f"Label overlay: {label_overlay if label_overlay else '<none>'}")
    lines.append("Overlays:")
    if overlays:
        lines.extend(f"  - {p}" for p in overlays)
    else:
        lines.append("  - <none>")
    manifest.write_text(" ".join(lines) + " ", encoding="utf-8")

def create_minimal_boot_tree(stage_dir: Path, boot_source: Path) -> Path:
    boot_dir = stage_dir / DEFAULT_BOOT_DIR
    boot_dir.mkdir(parents=True, exist_ok=True)
    boot_image = boot_dir / boot_source.name
    shutil.copy2(boot_source, boot_image)
    readme = stage_dir / "README.TXT"
    readme.write_text( "OpenStep 4.2 El Torito boot test image " "This ISO intentionally contains only the boot image and minimal metadata. ",
        encoding="utf-8",
    )
    return boot_image


def stage_boot_image(boot_source: Path, stage_dir: Path) -> Path:
    boot_dir = stage_dir / DEFAULT_BOOT_DIR
    boot_dir.mkdir(parents=True, exist_ok=True)
    boot_image = boot_dir / boot_source.name
    shutil.copy2(boot_source, boot_image)
    return boot_image


def build_iso(stage_dir: Path, boot_image_rel: Path, output_iso: Path, volume_id: str, eltorito_emulation: str = "floppy") -> None:
    xorriso = which_any("xorriso")
    mkisofs = which_any("genisoimage", "mkisofs")
    if xorriso:

        cmd = [
                xorriso, "-as", "mkisofs",
                "-r",
                "-J",
                "-l",
                "-iso-level", "3",
                "-V", volume_id,
                "-c", f"{DEFAULT_BOOT_DIR}/boot.catalog",
                "-b", boot_image_rel.as_posix(),
                ]

        if eltorito_emulation == "noemul":
            cmd.append("-no-emul-boot")
        elif eltorito_emulation != "floppy":
            raise BuildError(f"Unsupported El Torito emulation mode: {eltorito_emulation}")
        cmd.extend(["-o", str(output_iso), str(stage_dir)])
        run(cmd)
        return
    if mkisofs:
        cmd = [
                mkisofs,
                "-r",
                "-J",
                "-V", volume_id,
                "-c", f"{DEFAULT_BOOT_DIR}/boot.catalog",
                "-b", boot_image_rel.as_posix(),
                ]
        if eltorito_emulation == "noemul":
            cmd.append("-no-emul-boot")
        elif eltorito_emulation != "floppy":
            raise BuildError(f"Unsupported El Torito emulation mode: {eltorito_emulation}")
        cmd.extend(["-o", str(output_iso), str(stage_dir)])
        run(cmd)
        return
    raise BuildError("No ISO builder found. Install xorriso, genisoimage, or mkisofs.")


def read_sector(fh, lba: int) -> bytes:
    fh.seek(lba * SECTOR_SIZE)
    return fh.read(SECTOR_SIZE)


def _parse_dir_records(data: bytes) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    i = 0
    while i < len(data):
        length = data[i]
        if length == 0:
            i = ((i // SECTOR_SIZE) + 1) * SECTOR_SIZE
            continue
        rec = data[i:i + length]
        if len(rec) < 34:
            break
        extent = struct.unpack_from("<I", rec, 2)[0]
        size = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        records.append({"extent": extent, "size": size, "flags": flags, "name": name})
        i += length
    return records


def find_iso_file_extent(iso_path: Path, iso_name: str) -> tuple[int, int]:
    ensure_file(iso_path, "Output ISO")
    target = iso_name.upper().encode("ascii")
    alt_target = (iso_name.upper() + ";1").encode("ascii")
    with open(iso_path, "rb") as fh:
        pvd = read_sector(fh, 16)
        if len(pvd) != SECTOR_SIZE or pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise BuildError("Output ISO is missing a readable primary volume descriptor")
        root_extent = struct.unpack_from("<I", pvd, 158)[0]
        root_size = struct.unpack_from("<I", pvd, 166)[0]
        fh.seek(root_extent * SECTOR_SIZE)
        root = fh.read(root_size)
        for rec in _parse_dir_records(root):
            name = rec["name"]
            if name in (target, alt_target):
                return int(rec["extent"]), int(rec["size"])
    raise BuildError(f"Could not locate {iso_name} in output ISO")


def ensure_y2k_patch_iso(cache_path: Path, source_url: str) -> Path:
    if cache_path.is_file():
        log(f"Using cached Y2K patch ISO: {cache_path}")
        return cache_path
    if not source_url:
        raise BuildError("No Y2K ISO URL supplied and cache file is missing")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading Y2K patch ISO from {source_url}")
    try:
        with urllib.request.urlopen(source_url) as resp, open(cache_path, "wb") as dst:
            shutil.copyfileobj(resp, dst)
    except Exception as exc:  # pragma: no cover - network errors vary
        raise BuildError(f"Failed to download Y2K ISO from {source_url}: {exc}") from exc
    return cache_path


def apply_label_overlay(image_path: Path, label_bytes: bytes) -> None:
    ensure_file(image_path, "Output ISO")
    if len(label_bytes) != EXPECTED_LABEL_OVERLAY_SIZE:
        raise BuildError(f"Label overlay must be exactly {EXPECTED_LABEL_OVERLAY_SIZE} bytes, got {len(label_bytes)} bytes")
    with open(image_path, "r+b") as fh:
        fh.seek(0)
        fh.write(label_bytes)


def patch_label_front_porch(label_bytes: bytes, field_offset: int, value_blocks: int, field_format: str) -> bytes:
    if len(label_bytes) != EXPECTED_LABEL_OVERLAY_SIZE:
        raise BuildError("label blob has unexpected size")
    if field_offset < 0:
        raise BuildError("field offset must be non-negative")
    fmt_map = {
        "u16le": ("<H", 2),
        "u16be": (">H", 2),
        "u32le": ("<I", 4),
        "u32be": (">I", 4),
    }
    if field_format not in fmt_map:
        raise BuildError(f"unsupported field format: {field_format}")
    pack_fmt, width = fmt_map[field_format]
    if field_offset + width > len(label_bytes):
        raise BuildError("field offset extends beyond label blob")
    patched = bytearray(label_bytes)
    struct.pack_into(pack_fmt, patched, field_offset, value_blocks)
    return bytes(patched)


def validate_el_torito(iso_path: Path) -> dict[str, object]:
    ensure_file(iso_path, "Output ISO")
    result: dict[str, object] = {
        "iso": str(iso_path),
        "primary_volume_descriptor": False,
        "boot_record": False,
        "boot_catalog_lba": None,
        "boot_catalog_validation_header": False,
    }
    with open(iso_path, "rb") as fh:
        found_end = False
        found_boot_catalog_lba: Optional[int] = None
        for lba in range(16, 64):
            sector = read_sector(fh, lba)
            if len(sector) != SECTOR_SIZE:
                break
            vtype = sector[0]
            ident = sector[1:6]
            version = sector[6]
            if ident == b"CD001" and version == 1 and vtype == 1:
                result["primary_volume_descriptor"] = True
            if ident == b"CD001" and version == 1 and vtype == 0:
                boot_system_id = sector[7:39].rstrip(b" ")
                if boot_system_id.startswith(EL_TORITO_ID):
                    result["boot_record"] = True
                    found_boot_catalog_lba = struct.unpack_from("<I", sector, 71)[0]
                    result["boot_catalog_lba"] = found_boot_catalog_lba
            if ident == b"CD001" and version == 1 and vtype == 255:
                found_end = True
                break
        if not found_end:
            warn("Did not encounter ISO volume descriptor terminator in the expected range")
        if found_boot_catalog_lba is not None:
            boot_catalog = read_sector(fh, found_boot_catalog_lba)
            if boot_catalog and boot_catalog[0] == 0x01:
                checksum = 0
                for i in range(0, 32, 2):
                    checksum = (checksum + struct.unpack_from("<H", boot_catalog, i)[0]) & 0xFFFF
                result["boot_catalog_validation_header"] = checksum == 0
    return result


def require_valid(validation: dict[str, object]) -> None:
    problems = []
    if not validation["primary_volume_descriptor"]:
        problems.append("missing ISO-9660 primary volume descriptor")
    if not validation["boot_record"]:
        problems.append("missing El Torito boot record")
    if validation["boot_catalog_lba"] is None:
        problems.append("missing boot catalog LBA")
    if not validation["boot_catalog_validation_header"]:
        problems.append("invalid or missing boot catalog validation entry")
    if problems:
        raise BuildError("Output ISO validation failed: " + "; ".join(problems))


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build OpenStep 4.2 El Torito test and wrapped raw-CD images.")
    p.add_argument("--base-iso", type=Path, help="Source ISO-9660 image to extract in tree-based mode")
    p.add_argument("--base-raw-cd", type=Path, help="Source raw OpenStep/NeXT CD image to wrap")
    p.add_argument("--raw-cd-front-porch-blocks", type=int, default=80, help="2048-byte blocks to skip before the raw CD UFS payload (default: 80)")
    p.add_argument("--raw-cd-ufs-name", default=DEFAULT_UFS_FILENAME, help=f"Filename for wrapped UFS payload inside the new ISO (default: {DEFAULT_UFS_FILENAME})")
    p.add_argument("--boot-image", type=Path, help="Raw El Torito boot image, e.g. a prepared 2.88MB F288 image")
    p.add_argument("--install-floppy", type=Path, help="4.2 install floppy image or zip (used if --boot-image is not supplied)")
    p.add_argument("--driver-floppy", action="append", default=[], type=Path, help="Driver floppy image to include on the rebuilt CD (repeatable)")
    p.add_argument("--user-payload", type=Path, help="User payload directory")
    p.add_argument("--patch-payload", type=Path, help="Patch/Y2K/Patch 4 payload directory")
    p.add_argument("--driver-payload", type=Path, help="Default driver payload directory, e.g. VESA/Matrox")
    p.add_argument("--patch-iso", action="append", default=[], type=Path, help="Patch ISO to merge into the staged CD tree (repeatable)")
    p.add_argument("--skip-y2k-iso", action="store_true", help="Skip automatic NS/OS Y2K ISO download and merge")
    p.add_argument("--y2k-iso-url", default=DEFAULT_Y2K_ISO_URL, help="Source URL for the NS/OS Y2K ISO")
    p.add_argument("--y2k-iso-cache", type=Path, default=Path(DEFAULT_Y2K_ISO_CACHE), help="Cache path for the downloaded NS/OS Y2K ISO")
    p.add_argument("--overlay", action="append", default=[], type=Path, help="Overlay directory applied onto staged CD tree (repeatable)")
    p.add_argument("--volume-id", default=DEFAULT_VOLUME_ID, help=f"ISO volume ID (default: {DEFAULT_VOLUME_ID})")
    p.add_argument("--output", required=True, type=Path, help="Output ISO path")
    p.add_argument("--test-boot-only", action="store_true", help="Build only a minimal El Torito ISO for boot testing")
    p.add_argument("--eltorito-emulation", choices=["floppy", "noemul"], default="floppy", help="El Torito emulation mode for the boot image")
    p.add_argument("--label-overlay", type=Path, help="Optional 7680-byte NeXT disklabel blob template")
    p.add_argument("--label-front-porch-offset", type=lambda s: int(s, 0), help="Byte offset of the front-porch field inside the label blob")
    p.add_argument("--label-front-porch-format", choices=["u16le", "u16be", "u32le", "u32be"], default="u16be", help="Encoding of the front-porch field in the label blob")
    p.add_argument("--keep-work", action="store_true", help="Keep temporary working directory")
    args = p.parse_args(argv)
    if args.base_iso and args.base_raw_cd:
        raise SystemExit("Use only one of --base-iso or --base-raw-cd")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    work_ctx = tempfile.TemporaryDirectory(prefix="openstep-el-torito-")
    work_dir = Path(work_ctx.name)
    if args.keep_work:
        work_ctx.cleanup = lambda: None  # type: ignore[assignment]
        log(f"Keeping work directory: {work_dir}")
    try:
        stage_dir = work_dir / "stage"
        source_extract_dir = work_dir / "source"
        source_extract_dir.mkdir(parents=True, exist_ok=True)
        stage_dir.mkdir(parents=True, exist_ok=True)

        log("Resolving boot image")
        boot_image_source = resolve_boot_image(args.boot_image, args.install_floppy, work_dir)
        boot_probe = probe_boot_image(boot_image_source)
        log(f"Boot image: {boot_probe['path']} | size={boot_probe['size']} bytes ({boot_probe['size_label']})")
        if boot_probe["markers"]:
            log("Boot image markers: " + ", ".join(str(m) for m in boot_probe["markers"]))

        patch_isos: list[Path] = list(args.patch_iso)
        if not args.skip_y2k_iso:
            try:
                y2k_iso = ensure_y2k_patch_iso(args.y2k_iso_cache, args.y2k_iso_url)
                patch_isos.append(y2k_iso)
            except BuildError as exc:
                raise BuildError(f"Failed to prepare NS/OS Y2K ISO: {exc}") from exc

        wrapped_ufs_name: Optional[str] = None
        if args.test_boot_only:
            log("Creating minimal boot-test ISO tree")
            boot_image = create_minimal_boot_tree(stage_dir, boot_image_source)
            boot_image_rel = boot_image.relative_to(stage_dir)
        elif args.base_raw_cd:
            log("Creating raw-CD wrapper tree")
            boot_image = stage_boot_image(boot_image_source, stage_dir)
            boot_image_rel = boot_image.relative_to(stage_dir)
            wrapped_ufs_name = args.raw_cd_ufs_name
            extracted_ufs = extract_raw_cd_ufs(args.base_raw_cd, work_dir / wrapped_ufs_name, args.raw_cd_front_porch_blocks)
            copy_file(extracted_ufs, stage_dir / wrapped_ufs_name)
            if patch_isos:
                log("Merging patch ISOs into raw-CD wrapper tree")
                merge_patch_isos(patch_isos, stage_dir, work_dir)
            write_manifest(
                stage_dir=stage_dir,
                boot_image=boot_image_source,
                driver_floppies=list(args.driver_floppy),
                user_payload=args.user_payload,
                patch_payload=args.patch_payload,
                patch_isos=patch_isos,
                driver_payload=args.driver_payload,
                overlays=list(args.overlay),
                label_overlay=args.label_overlay,
                raw_cd_source=args.base_raw_cd,
                raw_cd_ufs_name=wrapped_ufs_name,
            )
        else:
            if not args.base_iso:
                raise BuildError("Need one of --test-boot-only, --base-raw-cd, or --base-iso")
            log("Extracting base CD image")
            extract_source_iso(args.base_iso, source_extract_dir)
            log("Creating staged CD tree")
            copy_tree(source_extract_dir, stage_dir, overwrite=True)
            log("Staging El Torito boot image")
            boot_image = stage_boot_image(boot_image_source, stage_dir)
            boot_image_rel = boot_image.relative_to(stage_dir)
            if patch_isos:
                log("Merging patch ISOs into staged CD tree")
                merge_patch_isos(patch_isos, stage_dir, work_dir)
            if args.driver_floppy:
                log("Injecting driver floppies")
                inject_driver_floppies(args.driver_floppy, stage_dir)
            else:
                warn("No driver floppies were supplied")
            if args.user_payload:
                merge_named_payload(args.user_payload, stage_dir, "user", DEFAULT_USER_DIR)
            else:
                warn("No user payload supplied")
            if args.patch_payload:
                merge_required_root_payload(args.patch_payload, stage_dir, "patch4_y2k")
            else:
                warn("No patch/Y2K/Patch 4 payload supplied")
            if args.driver_payload:
                merge_required_root_payload(args.driver_payload, stage_dir, "default_drivers")
            else:
                warn("No default driver payload supplied (VESA/Matrox not merged)")
            if args.overlay:
                apply_overlays(args.overlay, stage_dir)
            write_manifest(
                stage_dir=stage_dir,
                boot_image=boot_image_source,
                driver_floppies=list(args.driver_floppy),
                user_payload=args.user_payload,
                patch_payload=args.patch_payload,
                patch_isos=patch_isos,
                driver_payload=args.driver_payload,
                overlays=list(args.overlay),
                label_overlay=args.label_overlay,
                raw_cd_source=None,
                raw_cd_ufs_name=None,
            )

        log("Building El Torito ISO")
        build_iso(stage_dir, boot_image_rel, args.output, args.volume_id, args.eltorito_emulation)

        landed_ufs_lba: Optional[int] = None
        landed_ufs_size: Optional[int] = None
        if wrapped_ufs_name:
            landed_ufs_lba, landed_ufs_size = find_iso_file_extent(args.output, wrapped_ufs_name)
            log(f"Wrapped UFS landed at LBA {landed_ufs_lba}, size {landed_ufs_size} bytes")

        if args.label_overlay:
            label_bytes = args.label_overlay.read_bytes()
            if wrapped_ufs_name and args.label_front_porch_offset is not None:
                label_bytes = patch_label_front_porch(
                    label_bytes,
                    args.label_front_porch_offset,
                    landed_ufs_lba,
                    args.label_front_porch_format,
                )
                log(f"Patched label front-porch field to block {landed_ufs_lba}")
            elif wrapped_ufs_name and args.label_front_porch_offset is None:
                warn("label overlay supplied but no --label-front-porch-offset was given; using label blob unchanged")
            log("Applying label overlay")
            apply_label_overlay(args.output, label_bytes)

        log("Validating output ISO")
        validation = validate_el_torito(args.output)
        require_valid(validation)

        print()
        print("ISO build complete")
        print(textwrap.dedent(f"""
            Output ISO: {args.output}
            Boot image source: {boot_image_source}
            Boot image in ISO: {boot_image_rel.as_posix()}
            Wrapped UFS file: {wrapped_ufs_name if wrapped_ufs_name else '<none>'}
            Wrapped UFS LBA:  {landed_ufs_lba if landed_ufs_lba is not None else '<none>'}
            Label overlay:    {args.label_overlay if args.label_overlay else '<none>'}
            Validation:
              - Primary Volume Descriptor: {validation['primary_volume_descriptor']}
              - El Torito Boot Record:    {validation['boot_record']}
              - Boot Catalog LBA:         {validation['boot_catalog_lba']}
              - Boot Catalog Valid:       {validation['boot_catalog_validation_header']}
        """).strip())
        return 0
    except BuildError as exc:
        print(f"[x] {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            work_ctx.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
