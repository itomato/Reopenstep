from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .bigtar import BigTarArchive, BigTarEntry
from .errors import ReopenstepError
from .ufs import extract_file, overlay_bigtar, replace_file
from .util import sha256_file


VBE_COMPONENTS = (
    "mach_kernel",
    "usr/standalone/i386/boot",
    "private/Drivers/i386/VBE20DisplayDriver.config/Default.table",
    "private/Drivers/i386/VBE20DisplayDriver.config/VBE20DisplayDriver",
    "private/Drivers/i386/VBE20DisplayDriver.config/VBE20DisplayDriver_reloc",
    "NextLibrary/Frameworks/AppKit.framework/Versions/B/AppKit",
    "NextLibrary/Frameworks/Foundation.framework/Versions/B/Foundation",
    "usr/shlib/libFoundation_s.E.shlib",
)


def _payload(package: Path, directory: Path) -> tuple[Path, dict[str, object]]:
    if not package.is_file():
        raise ReopenstepError(f"Patch 4 archive not found: {package}")
    try:
        with tarfile.open(package) as outer:
            members = [member for member in outer.getmembers() if member.isfile()]
            payloads = [member for member in members if member.name.endswith(".tar.Z")]
            if len(payloads) != 1:
                raise ReopenstepError(f"expected one .tar.Z payload in {package}, found {len(payloads)}")
            compressed = directory / "payload.tar.Z"
            source = outer.extractfile(payloads[0])
            if source is None:
                raise ReopenstepError(f"cannot read {payloads[0].name} from {package}")
            with compressed.open("wb") as output:
                shutil.copyfileobj(source, output)
            metadata = {
                "outer_members": [member.name for member in members],
                "payload_member": payloads[0].name,
            }
    except tarfile.TarError as exc:
        raise ReopenstepError(f"cannot read Patch 4 outer archive {package}: {exc}") from exc
    uncompress = shutil.which("uncompress")
    if not uncompress:
        raise ReopenstepError("the host `uncompress` utility is required for Patch 4 .tar.Z payloads")
    process = subprocess.run([uncompress, str(compressed)], capture_output=True, text=True, check=False)
    if process.returncode:
        raise ReopenstepError(f"uncompress failed: {process.stderr.strip()}")
    return directory / "payload.tar", metadata


def _entry_report(archive: BigTarArchive, entry: BigTarEntry) -> dict[str, object]:
    result: dict[str, object] = {
        "path": "/" + entry.name,
        "kind": entry.kind,
        "size": entry.size,
        "mode": f"{entry.mode & 0o7777:04o}",
        "uid": entry.uid,
        "gid": entry.gid,
    }
    if entry.kind == "file":
        import hashlib
        digest = hashlib.sha256()
        with archive.path.open("rb") as stream:
            stream.seek(entry.data_offset)
            remaining = entry.size
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ReopenstepError(f"truncated bigtar data for {entry.name}")
                digest.update(chunk)
                remaining -= len(chunk)
        result["sha256"] = digest.hexdigest()
    if entry.link_name:
        result["link_target"] = "/" + entry.link_name
    return result


def inspect_patch4(package: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="reopenstep-patch4-") as name:
        payload, metadata = _payload(package, Path(name))
        archive = BigTarArchive(payload)
        entries = list(archive.entries())
        by_name = {entry.name: entry for entry in entries}
        components = [
            _entry_report(archive, by_name[path]) for path in VBE_COMPONENTS if path in by_name
        ]
        return {
            "package": str(package),
            "sha256": sha256_file(package),
            **metadata,
            "entries": len(entries),
            "files": sum(entry.kind == "file" for entry in entries),
            "directories": sum(entry.kind == "directory" for entry in entries),
            "links": sum(entry.kind in {"hardlink", "symlink"} for entry in entries),
            "vesa_boot_components": components,
            "vesa_boot_complete": all(path in by_name for path in VBE_COMPONENTS),
        }


def extract_patch4(package: Path, output: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="reopenstep-patch4-") as name:
        payload, metadata = _payload(package, Path(name))
        report = BigTarArchive(payload).extract(output)
    return {"package": str(package), "output": str(output), **metadata, **report}


def overlay_patch4(package: Path, image: Path, output: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="reopenstep-patch4-") as name:
        payload, metadata = _payload(package, Path(name))
        archive = BigTarArchive(payload)
        entries = list(archive.entries())
        report = overlay_bigtar(image, output, archive, entries)
    return {
        "package": str(package), "package_sha256": sha256_file(package),
        **metadata, **report,
    }


def set_vesa_mode(image: Path, output: Path, mode: int) -> dict[str, object]:
    if not 0x100 <= mode <= 0x1ff:
        raise ReopenstepError(f"VBE mode must be in the BIOS range 0x100..0x1ff: {mode:#x}")
    path = "/private/Drivers/i386/VBE20DisplayDriver.config/Default.table"
    with tempfile.TemporaryDirectory(prefix="reopenstep-vesa-") as name:
        root = Path(name)
        source = root / "Default.table"
        extract_file(image, path, source)
        text = source.read_text(encoding="ascii")
        updated, count = re.subn(
            r'("VBE Mode"\s*=\s*")\d+(";)',
            lambda match: match.group(1) + str(mode) + match.group(2),
            text,
            count=1,
        )
        if count != 1:
            raise ReopenstepError(f"cannot find a unique VBE Mode property in {path}")
        replacement = root / "Default-updated.table"
        replacement.write_text(updated, encoding="ascii")
        report = replace_file(image, path, replacement, output, mode=0o444)
    report.pop("source", None)
    report["file_mode"] = f"{report.pop('mode'):04o}"
    report.update({
        "vesa_mode": mode, "vesa_mode_hex": f"0x{mode:x}",
        "table_path": path,
    })
    return report
