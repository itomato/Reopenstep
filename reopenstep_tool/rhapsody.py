from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import ReopenstepError
from .nextlabel import LABEL_SCAN_SIZE, inspect_labels
from .ufs import nextufs_executable, path_exists
from .util import sha256_file


ROOT_KINDS = ("openstep", "nextstep", "rhapsody-dr2", "rhapsodios", "darwin")

ROOT_KIND_DETAILS = {
    "openstep": {
        "filesystem_family": "openstep-mach-ufs",
        "path_probe_supported": True,
        "notes": "OPENSTEP/NeXTStep Mach uses the original big-endian m68k UFS format.",
    },
    "nextstep": {
        "filesystem_family": "openstep-mach-ufs",
        "path_probe_supported": True,
        "notes": "NeXTStep Mach uses the original big-endian m68k UFS format.",
    },
    "rhapsody-dr2": {
        "filesystem_family": "rdr-intel-bsd44-native-ufs",
        "path_probe_supported": True,
        "path_probe": "rdrufs",
        "notes": (
            "Rhapsody Developer Release on Intel uses a native BSD 4.4 UFS variant "
            "without OPENSTEP's byte-swapping compatibility."
        ),
    },
    "rhapsodios": {
        "filesystem_family": "xnu-ufs",
        "path_probe_supported": True,
        "path_probe": "nextufs",
        "notes": "RhapsodiOS/Darwin experiments are probed as UFS until a more specific format is identified.",
    },
    "darwin": {
        "filesystem_family": "darwin-ufs",
        "path_probe_supported": True,
        "path_probe": "nextufs-or-native-ufs",
        "notes": "Darwin UFS roots are probed separately from the OPENSTEP kernel handoff path.",
    },
}

REQUIRED_BOOT_PATHS = {
    "openstep": ("/mach_kernel", "/private/Drivers/i386/System.config"),
    "nextstep": ("/mach_kernel", "/private/Drivers/i386/System.config"),
    "rhapsody-dr2": ("/mach_kernel", "/System/Library", "/usr"),
    "rhapsodios": ("/mach_kernel", "/System/Library", "/usr"),
    "darwin": ("/mach_kernel", "/System/Library", "/usr"),
}

BOOT_HINT_PATHS = (
    "/Library/Preferences/SystemConfiguration/com.apple.Boot.plist",
    "/System/Library/CoreServices/BootX",
    "/private/Drivers/i386/VBE20DisplayDriver.config",
    "/System/Library/Extensions",
)

BOOT1_LABEL_SECTOR = 15
BOOT1_LABEL_LOAD_ADDRESS = 0x1000
BOOT1_ENTRY_ADDRESS = 0x3000
BOOT1_BOOT2_SECTORS = 0x58
BOOT1_MEDIA_SECTOR_SIZE_OFFSET = 0x5C
BOOT1_BOOT2_BLOCK_OFFSET = 0x7C


@dataclass(frozen=True)
class ArtifactCheck:
    id: str
    path: Path
    required: bool


def validate_root_kind(root_kind: str) -> str:
    if root_kind not in ROOT_KINDS:
        raise ReopenstepError(f"unsupported root kind: {root_kind}")
    return root_kind


def _path_state(path: Path) -> dict[str, object]:
    exists = path.is_file()
    state: dict[str, object] = {"path": str(path), "exists": exists}
    if exists:
        state["size"] = path.stat().st_size
        state["sha256"] = sha256_file(path)
    return state


def _ufs_paths(image: Path, paths: tuple[str, ...]) -> dict[str, bool]:
    try:
        tool = nextufs_executable()
    except ReopenstepError:
        return {path: False for path in paths}
    found: dict[str, bool] = {}
    for path in paths:
        try:
            found[path] = path_exists(image, path, tool)
        except ReopenstepError:
            found[path] = False
    return found


def _native_ufs_paths(image: Path, paths: tuple[str, ...],
                      root_offset: int | None = None) -> dict[str, bool]:
    from .rdrufs import open_image

    found: dict[str, bool] = {}
    with open_image(image, root_offset=root_offset) as fs:
        for path in paths:
            try:
                fs.resolve(path)
                found[path] = True
            except ReopenstepError:
                found[path] = False
    return found


def inspect_xnu_root(image: Path, root_kind: str = "rhapsodios",
                     root_offset: int | None = None) -> dict[str, object]:
    validate_root_kind(root_kind)
    if not image.is_file():
        raise ReopenstepError(f"XNU/Rhapsody UFS root not found: {image}")
    details = ROOT_KIND_DETAILS[root_kind]
    required = REQUIRED_BOOT_PATHS[root_kind]
    if not details["path_probe_supported"]:
        return {
            "root_kind": root_kind,
            "filesystem_family": details["filesystem_family"],
            "path_probe_supported": False,
            "image": str(image),
            "size": image.stat().st_size,
            "sha256": sha256_file(image),
            "required_paths": {path: None for path in required},
            "boot_hints": {path: None for path in BOOT_HINT_PATHS},
            "bootable_candidate": False,
            "missing": [],
            "unverified": list(required),
            "notes": details["notes"],
        }
    probe = str(details.get("path_probe", "nextufs"))
    path_probe_error = None
    if probe == "rdrufs":
        try:
            paths = _native_ufs_paths(image, required + BOOT_HINT_PATHS, root_offset)
        except ReopenstepError as exc:
            paths = {path: False for path in required + BOOT_HINT_PATHS}
            path_probe_error = str(exc)
        path_probe = "rdrufs"
    elif probe == "nextufs-or-native-ufs":
        if root_offset is not None:
            try:
                paths = _native_ufs_paths(image, required + BOOT_HINT_PATHS, root_offset)
                path_probe = "rdrufs"
            except ReopenstepError as exc:
                paths = {path: False for path in required + BOOT_HINT_PATHS}
                path_probe = "rdrufs"
                path_probe_error = str(exc)
        else:
            paths = _ufs_paths(image, required + BOOT_HINT_PATHS)
            path_probe = "nextufs"
            if not all(paths[path] for path in required):
                try:
                    paths = _native_ufs_paths(image, required + BOOT_HINT_PATHS, root_offset)
                    path_probe = "rdrufs"
                except ReopenstepError as exc:
                    path_probe_error = str(exc)
    else:
        paths = _ufs_paths(image, required + BOOT_HINT_PATHS)
        path_probe = "nextufs"
    missing = [path for path in required if not paths[path]]
    return {
        "root_kind": root_kind,
        "filesystem_family": details["filesystem_family"],
        "path_probe_supported": True,
        "path_probe": path_probe,
        "path_probe_error": path_probe_error,
        "root_offset": root_offset,
        "image": str(image),
        "size": image.stat().st_size,
        "sha256": sha256_file(image),
        "required_paths": {path: paths[path] for path in required},
        "boot_hints": {path: paths[path] for path in BOOT_HINT_PATHS},
        "bootable_candidate": not missing,
        "missing": missing,
        "notes": details["notes"],
    }


def inspect_native_boot(image: Path) -> dict[str, object]:
    if not image.is_file():
        raise ReopenstepError(f"Rhapsody boot image not found: {image}")
    label = inspect_labels(image)
    with image.open("rb") as handle:
        handle.seek(label["offset"])
        label_bytes = handle.read(LABEL_SCAN_SIZE)
    if len(label_bytes) < BOOT1_BOOT2_BLOCK_OFFSET + 4:
        raise ReopenstepError(f"incomplete Rhapsody label in {image}")
    media_sector_size = struct.unpack_from(">I", label_bytes, BOOT1_MEDIA_SECTOR_SIZE_OFFSET)[0]
    boot2_block = struct.unpack_from(">I", label_bytes, BOOT1_BOOT2_BLOCK_OFFSET)[0]
    if media_sector_size < 512 or media_sector_size % 512 != 0:
        raise ReopenstepError(f"unsupported native media sector size: {media_sector_size}")
    boot2_lba = boot2_block * (media_sector_size // 512)
    boot2_offset = boot2_lba * 512
    boot2_size = BOOT1_BOOT2_SECTORS * 512
    boot2_end = boot2_offset + boot2_size
    image_size = image.stat().st_size
    boot1 = {
        "label_sector": BOOT1_LABEL_SECTOR,
        "label_load_address": BOOT1_LABEL_LOAD_ADDRESS,
        "entry_address": BOOT1_ENTRY_ADDRESS,
        "boot2_sector_count": BOOT1_BOOT2_SECTORS,
        "media_sector_size_offset": BOOT1_MEDIA_SECTOR_SIZE_OFFSET,
        "boot2_block_offset": BOOT1_BOOT2_BLOCK_OFFSET,
    }
    return {
        "image": str(image),
        "size": image_size,
        "label": label,
        "boot1": boot1,
        "media_sector_size": media_sector_size,
        "boot2_block": boot2_block,
        "boot2_lba": boot2_lba,
        "boot2_byte_offset": boot2_offset,
        "boot2_size": boot2_size,
        "boot2_end_offset": boot2_end,
        "boot2_present": boot2_end <= image_size,
    }


def mastering_gap(project: Path, xnu_ufs: Path | None = None,
                  root_kind: str = "rhapsodios",
                  root_offset: int | None = None) -> dict[str, object]:
    validate_root_kind(root_kind)
    candidate = xnu_ufs or (Path(os.environ["XNU_UFS"]) if "XNU_UFS" in os.environ else None)
    checks = (
        ArtifactCheck("openstep_user_iso", project / "vault/OpenStep-4.2-User.iso", True),
        ArtifactCheck("openstep_developer_iso", project / "vault/OpenStep-4.2-Developer.iso", False),
        ArtifactCheck("user_patch4", project / "vault/OS42MachUserPatch4.tar", True),
        ArtifactCheck("dev_patch4", project / "vault/OS42MachDevPatch4.tar", False),
        ArtifactCheck("next_label_template", project / "out/mastered/user-base/NEXT_LABEL.bin", True),
        ArtifactCheck("openstep_patch4_installer_ufs", project / "out/boote/openstep-user-patch4-beta-eide-cd.ufs", True),
        ArtifactCheck("boote_cdboot", project / "out/boote/boote-cdboot", True),
        ArtifactCheck("xnu_ufs", candidate or project / "vault/Rhapsody-XNU-root.ufs", True),
    )
    artifacts = {
        check.id: {**_path_state(check.path), "required": check.required}
        for check in checks
    }
    try:
        helper = nextufs_executable()
        nextufs = {
            "available": True,
            "path": str(helper),
            "can_mutate_existing_ufs": True,
            "can_create_new_ufs": False,
            "can_resize_ufs": False,
            "can_fsck_ufs": False,
        }
    except ReopenstepError as exc:
        nextufs = {
            "available": False,
            "error": str(exc),
            "can_mutate_existing_ufs": False,
            "can_create_new_ufs": False,
            "can_resize_ufs": False,
            "can_fsck_ufs": False,
        }
    root_report = None
    if candidate is not None and candidate.is_file():
        root_report = inspect_xnu_root(candidate, root_kind, root_offset)
    missing = [
        key for key, value in artifacts.items()
        if value["required"] and not value["exists"]
    ]
    gaps = []
    if "xnu_ufs" in missing:
        gaps.append("Provide or build a bootable Rhapsody/XNU UFS root image and pass it as XNU_UFS.")
    if not nextufs["can_create_new_ufs"]:
        gaps.append("Add a host-side UFS image creator or keep using seed UFS images for mutation.")
    if root_report is not None and root_report.get("path_probe_error"):
        gaps.append(f"Could not inspect candidate {root_kind} root: {root_report['path_probe_error']}")
    if root_report is not None and not root_report["path_probe_supported"]:
        gaps.append("No filesystem reader is available for this root kind.")
    elif root_report is not None and not root_report["bootable_candidate"]:
        gaps.append("Candidate XNU UFS is missing required boot paths.")
    ready = not missing and nextufs["available"] and root_report is not None and root_report["bootable_candidate"]
    return {
        "root_kind": root_kind,
        "ready_for_boote_xnu_wrap": ready,
        "artifacts": artifacts,
        "nextufs": nextufs,
        "xnu_root": root_report,
        "missing_required_artifacts": missing,
        "gaps": gaps,
    }
