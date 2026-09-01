from __future__ import annotations

import gzip
import io
import os
import shutil
import stat
import struct
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from .errors import ReopenstepError
from .rdrufs import open_image
from .util import atomic_json, sha256_file


EXPECTED_PAYLOADS = (
    "Glide/Packages/Glide2.pkg/Glide2.pax.gz",
    "Glide/Packages/GlidePreferences.pkg/GlidePreferences.pax.gz",
    "Glide/Packages/Voodoo2Driver.pkg/Voodoo2Driver.pax.gz",
)

MACH_CPU_NAMES = {7: "i386", 18: "ppc"}
MACH_FILE_NAMES = {2: "executable", 5: "preload", 6: "dylib", 8: "bundle"}

DR2_REFERENCE_PATHS = {
    "Driver.projectType": "/System/Developer/ProjectTypes/Driver.projectType",
    "KernelServer.projectType": "/System/Developer/ProjectTypes/KernelServer.projectType",
    "pb_makefiles": "/System/Developer/Makefiles/pb_makefiles",
    "System-Headers-B": "/System/Library/Frameworks/System.framework/Versions/B/Headers",
    "PCIBus.config": "/private/Drivers/i386/PCIBus.config",
    "ATIMach64DisplayDriver.config": "/private/Drivers/i386/ATIMach64DisplayDriver.config",
    "DEC21142Network.config": "/private/Drivers/i386/DEC21142Network.config",
}


def _safe_name(name: str) -> Path:
    pure = PurePosixPath(name)
    parts = tuple(part for part in pure.parts if part not in {"", "."})
    if pure.is_absolute() or not parts or any(part == ".." for part in parts):
        raise ReopenstepError(f"unsafe Glide archive path: {name!r}")
    return Path(*parts)


def _member_bytes(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    stream = archive.extractfile(member)
    if stream is None:
        raise ReopenstepError(f"cannot read Glide archive member: {member.name}")
    return stream.read()


def _extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    for member in archive:
        relative = _safe_name(member.name)
        target = destination / relative
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_member_bytes(archive, member))
            os.chmod(target, member.mode & 0o777)
        elif member.issym():
            link = PurePosixPath(member.linkname)
            if link.is_absolute() or ".." in link.parts:
                raise ReopenstepError(
                    f"unsafe Glide archive symlink: {member.name!r} -> {member.linkname!r}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(member.linkname)
        else:
            raise ReopenstepError(
                f"unsupported Glide archive member type: {member.name!r}"
            )


def _odc_octal(field: bytes, label: str, offset: int) -> int:
    try:
        return int(field, 8)
    except ValueError as exc:
        raise ReopenstepError(f"invalid cpio {label} at offset {offset}") from exc


def _extract_odc_cpio(payload: bytes, destination: Path) -> None:
    offset = 0
    deferred_links: list[tuple[Path, str]] = []
    while offset + 76 <= len(payload):
        header_offset = offset
        header = payload[offset:offset + 76]
        offset += 76
        if header[:6] != b"070707":
            raise ReopenstepError(f"invalid odc cpio magic at offset {header_offset}")
        mode = _odc_octal(header[18:24], "mode", header_offset)
        name_size = _odc_octal(header[59:65], "name size", header_offset)
        file_size = _odc_octal(header[65:76], "file size", header_offset)
        if name_size < 1 or offset + name_size + file_size > len(payload):
            raise ReopenstepError(f"truncated odc cpio entry at offset {header_offset}")
        raw_name = payload[offset:offset + name_size]
        offset += name_size
        if raw_name[-1:] != b"\0":
            raise ReopenstepError(f"unterminated odc cpio name at offset {header_offset}")
        try:
            name = raw_name[:-1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReopenstepError(f"non-UTF-8 odc cpio name at offset {header_offset}") from exc
        data = payload[offset:offset + file_size]
        offset += file_size
        if name == "TRAILER!!!":
            break
        if name in {".", "./"}:
            destination.mkdir(parents=True, exist_ok=True)
            continue
        relative = _safe_name(name)
        target = destination / relative
        kind = stat.S_IFMT(mode)
        if kind == stat.S_IFDIR:
            target.mkdir(parents=True, exist_ok=True)
        elif kind == stat.S_IFREG:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            os.chmod(target, mode & 0o777)
        elif kind == stat.S_IFLNK:
            try:
                link_name = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ReopenstepError(f"non-UTF-8 odc cpio symlink at {name!r}") from exc
            if PurePosixPath(link_name).is_absolute():
                raise ReopenstepError(f"unsafe absolute odc cpio symlink at {name!r}")
            deferred_links.append((target, link_name))
        else:
            raise ReopenstepError(f"unsupported odc cpio member type at {name!r}")
    for target, link_name in deferred_links:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(link_name)


def _macho(path: Path) -> dict[str, object] | None:
    with path.open("rb") as handle:
        header = handle.read(28)
    if len(header) < 28:
        return None
    magic = header[:4]
    if magic == b"\xfe\xed\xfa\xce":
        endian = ">"
    elif magic == b"\xce\xfa\xed\xfe":
        endian = "<"
    else:
        return None
    _, cpu_type, cpu_subtype, file_type, command_count, command_size, flags = struct.unpack(
        endian + "7I", header
    )
    return {
        "bits": 32,
        "byte_order": "big" if endian == ">" else "little",
        "cpu_type": cpu_type,
        "architecture": MACH_CPU_NAMES.get(cpu_type, f"cpu-{cpu_type}"),
        "cpu_subtype": cpu_subtype,
        "file_type": file_type,
        "kind": MACH_FILE_NAMES.get(file_type, f"file-{file_type}"),
        "load_command_count": command_count,
        "load_command_size": command_size,
        "flags": flags,
    }


def _extract_payload(payload: bytes, destination: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as nested:
            _extract_tar(nested, destination)
        return
    except tarfile.ReadError:
        _extract_odc_cpio(payload, destination)


def reference_manifest(root: Path, source: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            files.append({"path": relative, "kind": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            item: dict[str, object] = {
                "path": relative,
                "kind": "file",
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            if macho := _macho(path):
                item["mach_o"] = macho
            files.append(item)
    return {
        "format": "reopenstep-glide-reference-v1",
        "source": {
            "path": str(source),
            "size": source.stat().st_size,
            "sha256": sha256_file(source),
        },
        "files": files,
    }


def prepare_reference(source: Path, output: Path) -> dict[str, object]:
    if not source.is_file():
        raise ReopenstepError(f"Omni Glide archive not found: {source}")
    if output.exists() or output.is_symlink():
        raise ReopenstepError(f"Glide reference destination already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    try:
        with tarfile.open(source, "r:") as outer:
            members = {member.name: member for member in outer.getmembers()}
            missing = [name for name in EXPECTED_PAYLOADS if name not in members]
            if missing:
                raise ReopenstepError(f"Omni Glide archive is missing payloads: {', '.join(missing)}")
            package = temporary / "package"
            root = temporary / "root"
            package.mkdir()
            root.mkdir()
            for name in EXPECTED_PAYLOADS:
                payload = _member_bytes(outer, members[name])
                payload_path = package / Path(name).name
                payload_path.write_bytes(payload)
                try:
                    unpacked = gzip.decompress(payload)
                except gzip.BadGzipFile as exc:
                    raise ReopenstepError(f"invalid gzip payload in {name}") from exc
                _extract_payload(unpacked, root)
            readme = members.get("Glide/ReadMe.html")
            if readme is not None:
                (package / "ReadMe.html").write_bytes(_member_bytes(outer, readme))
        manifest = reference_manifest(root, source)
        atomic_json(temporary / "manifest.json", manifest)
        temporary.rename(output)
        return {**manifest, "output": str(output), "manifest": str(output / "manifest.json")}
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def prepare_dr2_reference(source: Path, output: Path,
                          *, root_offset: int | None = None) -> dict[str, object]:
    """Extract the small DR2 SDK/driver corpus needed by the Glide port."""
    if not source.is_file():
        raise ReopenstepError(f"Rhapsody DR2 UFS image not found: {source}")
    if output.exists() or output.is_symlink():
        raise ReopenstepError(f"DR2 reference destination already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    try:
        extracted: list[dict[str, object]] = []
        with open_image(source, root_offset=root_offset) as fs:
            for label, path in DR2_REFERENCE_PATHS.items():
                report = fs.extract_tree(path, temporary / label)
                extracted.append({
                    "label": label,
                    "source_path": path,
                    "entry_count": report["entry_count"],
                })
            resolved_offset = fs.root_offset
        manifest = {
            "format": "reopenstep-glide-dr2-reference-v1",
            "source": {
                "path": str(source),
                "size": source.stat().st_size,
                "sha256": sha256_file(source),
                "root_offset": resolved_offset,
            },
            "artifacts": extracted,
        }
        atomic_json(temporary / "manifest.json", manifest)
        temporary.rename(output)
        return {**manifest, "output": str(output), "manifest": str(output / "manifest.json")}
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def stage_rhapsody_driver(kernel: Path, server: Path, resources: Path,
                          output: Path) -> dict[str, object]:
    """Create a Voodoo2.config from native DR2 build products."""
    required = {
        "Voodoo2_reloc": kernel,
        "V2Server": server,
        "Default.table": resources / "Default.table",
        "Localizable.strings": resources / "Localizable.strings",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise ReopenstepError(f"Rhapsody Glide build products are missing: {', '.join(missing)}")
    if output.exists() or output.is_symlink():
        raise ReopenstepError(f"Rhapsody driver destination already exists: {output}")
    for label, binary in (("kernel", kernel), ("server", server)):
        metadata = _macho(binary)
        if metadata is None or metadata["architecture"] != "i386":
            raise ReopenstepError(
                f"Rhapsody {label} product is not a 32-bit i386 Mach-O: {binary}"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    try:
        files: list[dict[str, object]] = []
        for name, source in required.items():
            destination = temporary / name
            shutil.copy2(source, destination)
            if name in {"Voodoo2_reloc", "V2Server"}:
                os.chmod(destination, destination.stat().st_mode | 0o111)
            item: dict[str, object] = {
                "path": name,
                "size": destination.stat().st_size,
                "sha256": sha256_file(destination),
            }
            if macho := _macho(destination):
                item["mach_o"] = macho
            files.append(item)
        manifest = {
            "format": "reopenstep-rhapsody-voodoo2-config-v1",
            "files": files,
        }
        atomic_json(temporary / "manifest.json", manifest)
        temporary.rename(output)
        return {**manifest, "output": str(output), "manifest": str(output / "manifest.json")}
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
