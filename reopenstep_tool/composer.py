from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .errors import ReopenstepError
from .util import atomic_json, executable, sha256_file


RECIPE_FORMAT = "reopenstep-installation-package-v1"
PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,62}$")
INFO_TOKEN = re.compile(r"^[^\s]+$")
SHELL_META = frozenset("!$^&*(){}[]\\|;<>?'\"`")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class PayloadEntry:
    path: str
    kind: str
    mode: int
    size: int
    mtime: int
    sha256: str | None = None
    target: str | None = None

    def recipe_value(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "path": self.path,
            "kind": self.kind,
            "mode": f"{self.mode:04o}",
            "size": self.size,
            "mtime": self.mtime,
        }
        if self.sha256 is not None:
            value["sha256"] = self.sha256
        if self.target is not None:
            value["target"] = self.target
        return value


def _safe_relative(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if not relative or relative == "." or any(character.isspace() for character in relative):
        raise ReopenstepError(f"payload contains an unsupported pathname: {relative!r}")
    if any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts):
        raise ReopenstepError(f"payload path is not safe: {relative}")
    try:
        relative.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReopenstepError(f"OPENSTEP package paths must be ASCII: {relative}") from exc
    if len("./" + relative) > 100:
        raise ReopenstepError(f"payload path exceeds the classic tar limit (100): {relative}")
    return relative


def payload_inventory(root: Path) -> list[PayloadEntry]:
    if not root.is_dir():
        raise ReopenstepError(f"package payload root is not a directory: {root}")
    entries: list[PayloadEntry] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().encode("utf-8")):
        relative = _safe_relative(path, root)
        details = path.lstat()
        mode = stat.S_IMODE(details.st_mode)
        mtime = int(details.st_mtime)
        if stat.S_ISDIR(details.st_mode):
            kind, size, digest, target = "directory", 0, None, None
        elif stat.S_ISREG(details.st_mode):
            kind, size, digest, target = "file", details.st_size, sha256_file(path), None
        elif stat.S_ISLNK(details.st_mode):
            target = os.readlink(path)
            if "\n" in target or "\r" in target or "\t" in target:
                raise ReopenstepError(f"payload symlink has an unsupported target: {relative}")
            kind, size, digest = "symlink", len(os.fsencode(target)), None
        else:
            raise ReopenstepError(f"payload contains an unsupported file type: {relative}")
        entries.append(PayloadEntry(relative, kind, mode, size, mtime, digest, target))
    if not any(entry.kind != "directory" for entry in entries):
        raise ReopenstepError("package payload contains no files")
    return entries


def inventory_digest(entries: Iterable[PayloadEntry]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(json.dumps(entry.recipe_value(), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_metadata(name: str, title: str, version: str, description: str,
                      default_location: str, disk_name: str) -> None:
    if not PACKAGE_NAME.fullmatch(name):
        raise ReopenstepError("package name must be 1-63 ASCII letters, digits, dots, underscores, pluses, or hyphens")
    for label, value, maximum in (
        ("title", title, 49), ("version", version, 1023), ("description", description, 1023),
    ):
        if not value or "\n" in value or "\r" in value or "\t" in value or len(value) > maximum:
            raise ReopenstepError(f"package {label} is empty, multiline, or longer than {maximum} characters")
    if not default_location.startswith("/") and not default_location.startswith("~/"):
        raise ReopenstepError("default location must be an absolute path or begin with ~/")
    for label, value in (("default location", default_location), ("disk name", disk_name)):
        if any(character.isspace() for character in value) and label == "default location":
            raise ReopenstepError("default location cannot contain whitespace")
        if any(character in SHELL_META for character in value):
            raise ReopenstepError(f"package {label} contains an Installer-forbidden shell metacharacter")


def package_recipe(*, root: Path, name: str, title: str, version: str, description: str,
                   default_location: str, disk_name: str | None = None,
                   relocatable: bool = False, application: bool = False,
                   needs_authorization: bool = True, owner: int = 0, group: int = 0) -> dict[str, Any]:
    disk_name = disk_name or name
    validate_metadata(name, title, version, description, default_location, disk_name)
    if owner < 0 or group < 0:
        raise ReopenstepError("package owner and group IDs cannot be negative")
    resolved = root.resolve()
    entries = payload_inventory(resolved)
    return {
        "format": RECIPE_FORMAT,
        "package": {
            "name": name,
            "title": title,
            "version": version,
            "description": description,
            "default_location": default_location,
            "disk_name": disk_name,
            "relocatable": relocatable,
            "application": application,
            "needs_authorization": needs_authorization,
            "owner": owner,
            "group": group,
        },
        "payload": {
            "root": str(resolved),
            "digest": inventory_digest(entries),
            "files": sum(entry.kind == "file" for entry in entries),
            "symlinks": sum(entry.kind == "symlink" for entry in entries),
            "directories": sum(entry.kind == "directory" for entry in entries),
            "installed_bytes": sum(entry.size for entry in entries if entry.kind == "file"),
            "entries": [entry.recipe_value() for entry in entries],
        },
        "bom": {
            "format": "openstep-text",
            "directory_policy": "archive-only",
            "ownership": f"{owner}/{group}",
        },
    }


def write_package_recipe(path: Path, recipe: dict[str, Any]) -> None:
    atomic_json(path, recipe)


def load_package_recipe(path: Path) -> dict[str, Any]:
    try:
        recipe = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReopenstepError(f"cannot read package recipe {path}: {exc}") from exc
    if recipe.get("format") != RECIPE_FORMAT or not isinstance(recipe.get("package"), dict) or not isinstance(recipe.get("payload"), dict):
        raise ReopenstepError(f"unsupported package recipe: {path}")
    return recipe


def _permission_text(mode: int) -> str:
    return stat.filemode(mode)[1:]


def _bom_line(entry: PayloadEntry, owner: int, group: int) -> str:
    moment = datetime.fromtimestamp(entry.mtime)
    timestamp = f"{MONTHS[moment.month - 1]} {moment.day:2d} {moment:%H:%M} {moment.year:04d}"
    return f"./{entry.path}\t{_permission_text(entry.mode)}\t{owner}/{group}\t{entry.size}\t{timestamp}\n"


def write_openstep_bom(root: Path, output: Path, *, owner: int = 0, group: int = 0) -> dict[str, Any]:
    entries = payload_inventory(root)
    material = [entry for entry in entries if entry.kind != "directory"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(_bom_line(entry, owner, group) for entry in material), encoding="ascii")
    return {
        "path": str(output),
        "format": "openstep-text",
        "entries": len(material),
        "sha256": sha256_file(output),
    }


def inspect_bom(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    report: dict[str, Any] = {"path": str(path), "size": len(data), "sha256": sha256_file(path)}
    if data.startswith(b"BOMStore"):
        report.update({"format": "darwin-bomstore", "compatible_with_openstep_transport": False})
        return report
    if len(data) >= 32 and data[0x16:0x18] == b"BI" and data[0x1c:0x20] == b"allo":
        report.update({"format": "openstep-installed-binary", "compatible_with_openstep_transport": True})
        return report
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError:
        report.update({"format": "unknown-binary", "compatible_with_openstep_transport": False})
        return report
    malformed: list[int] = []
    paths: list[str] = []
    pattern = re.compile(r"^(\./\S+)\s+[rwxStTs-]{9}\s+\d+/\d+\s+\d+\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}\s+\d{4}$")
    for number, line in enumerate(lines, 1):
        match = pattern.fullmatch(line)
        if not match:
            malformed.append(number)
        else:
            paths.append(match.group(1))
    report.update({
        "format": "openstep-text" if lines and not malformed else "unknown-text",
        "compatible_with_openstep_transport": bool(lines) and not malformed,
        "entries": len(paths),
        "malformed_lines": malformed,
    })
    return report


def _info_text(metadata: dict[str, Any]) -> str:
    yesno = lambda value: "YES" if value else "NO"
    fields = (
        ("Title", metadata["title"]),
        ("Version", metadata["version"]),
        ("Description", metadata["description"]),
        ("DefaultLocation", metadata["default_location"]),
        ("Relocatable", yesno(metadata["relocatable"])),
        ("Diskname", metadata["disk_name"]),
        ("NeedsAuthorization", yesno(metadata["needs_authorization"])),
        ("Application", yesno(metadata["application"])),
        ("InstallOnly", "YES"),
        ("LongFilenames", "NO"),
    )
    return "# Generated by ReopenStep Installation Composer\n\n" + "".join(f"{key}\t\t{value}\n" for key, value in fields)


def _archive_payload(root: Path, output: Path, entries: list[PayloadEntry], owner: int, group: int) -> None:
    with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as archive:
        root_info = archive.gettarinfo(str(root), arcname="./")
        root_info.uid, root_info.gid, root_info.uname, root_info.gname = owner, group, "root", "wheel"
        archive.addfile(root_info)
        for entry in entries:
            source = root / entry.path
            info = archive.gettarinfo(str(source), arcname="./" + entry.path)
            info.uid, info.gid, info.uname, info.gname = owner, group, "root", "wheel"
            if info.isfile():
                with source.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                archive.addfile(info)


def _compress_tar(source: Path, output: Path) -> str:
    tool = executable("compress", "ncompress")
    if not tool:
        raise ReopenstepError("compress or ncompress is required to create OPENSTEP .tar.Z payloads")
    compressed = source.with_name(source.name + ".Z")
    result = subprocess.run([tool, "-f", str(source)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ReopenstepError(f"compress failed ({result.returncode})" + (f": {detail}" if detail else ""))
    if not compressed.is_file():
        raise ReopenstepError("compress completed without producing a .Z archive")
    os.replace(compressed, output)
    if output.read_bytes()[:2] != b"\x1f\x9d":
        raise ReopenstepError("compress did not produce a UNIX compress .Z stream")
    return tool


def _kilobytes(size: int) -> int:
    return (size + 1023) // 1024


def build_package(recipe_path: Path, output: Path) -> dict[str, Any]:
    recipe = load_package_recipe(recipe_path)
    metadata = recipe["package"]
    root = Path(recipe["payload"]["root"])
    validate_metadata(metadata["name"], metadata["title"], metadata["version"], metadata["description"],
                      metadata["default_location"], metadata["disk_name"])
    entries = payload_inventory(root)
    actual_digest = inventory_digest(entries)
    if actual_digest != recipe["payload"].get("digest"):
        raise ReopenstepError("payload changed after the recipe was created; generate and review a new recipe")
    if output.suffix != ".pkg":
        raise ReopenstepError("package output must end in .pkg")
    if output.stem != metadata["name"]:
        raise ReopenstepError(f"package output must be named {metadata['name']}.pkg")
    if output.exists():
        raise ReopenstepError(f"package output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    owner, group = int(metadata["owner"]), int(metadata["group"])
    name = metadata["name"]
    with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=output.parent) as temporary:
        package = Path(temporary) / output.name
        package.mkdir(mode=0o755)
        bom_path = package / f"{name}.bom"
        info_path = package / f"{name}.info"
        sizes_path = package / f"{name}.sizes"
        archive_path = package / f"{name}.tar.Z"
        write_openstep_bom(root, bom_path, owner=owner, group=group)
        info_path.write_text(_info_text(metadata), encoding="ascii")
        with tempfile.NamedTemporaryFile(prefix=f"{name}-", suffix=".tar", dir=output.parent, delete=False) as handle:
            tar_path = Path(handle.name)
        try:
            _archive_payload(root, tar_path, entries, owner, group)
            compressor = _compress_tar(tar_path, archive_path)
        finally:
            tar_path.unlink(missing_ok=True)
        material = [entry for entry in entries if entry.kind != "directory"]
        installed_kb = sum(max(1, _kilobytes(entry.size)) for entry in material)
        sizes_path.write_text(f"NumFiles {len(material)}\nInstalledSize {installed_kb}\nCompressedSize 0\n", encoding="ascii")
        compressed_kb = sum(max(1, _kilobytes(path.stat().st_size)) for path in package.iterdir()) + 3
        sizes_path.write_text(f"NumFiles {len(material)}\nInstalledSize {installed_kb}\nCompressedSize {compressed_kb}\n", encoding="ascii")
        for path in package.iterdir():
            path.chmod(0o444)
        os.replace(package, output)
    return {
        "output": str(output),
        "name": name,
        "files": len([entry for entry in entries if entry.kind == "file"]),
        "symlinks": len([entry for entry in entries if entry.kind == "symlink"]),
        "payload_digest": actual_digest,
        "compressor": compressor,
        "components": sorted(path.name for path in output.iterdir()),
    }


def _parse_pairs(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="latin-1").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) == 2 and INFO_TOKEN.fullmatch(parts[0]):
            values[parts[0]] = parts[1]
    return values


def inspect_package(path: Path) -> dict[str, Any]:
    if not path.is_dir() or path.suffix != ".pkg":
        raise ReopenstepError(f"OPENSTEP package must be a .pkg directory: {path}")
    name = path.stem
    expected = {suffix: path / f"{name}.{suffix}" for suffix in ("tar.Z", "bom", "info", "sizes")}
    missing = [item.name for item in expected.values() if not item.is_file()]
    report: dict[str, Any] = {"path": str(path), "name": name, "complete": not missing, "missing": missing}
    if expected["info"].is_file():
        report["info"] = _parse_pairs(expected["info"])
    if expected["sizes"].is_file():
        report["sizes"] = _parse_pairs(expected["sizes"])
    if expected["bom"].is_file():
        report["bom"] = inspect_bom(expected["bom"])
    if expected["tar.Z"].is_file():
        report["archive"] = {
            "size": expected["tar.Z"].stat().st_size,
            "sha256": sha256_file(expected["tar.Z"]),
            "unix_compress": expected["tar.Z"].read_bytes()[:2] == b"\x1f\x9d",
        }
    report["compatible_candidate"] = bool(
        report["complete"]
        and report.get("bom", {}).get("compatible_with_openstep_transport")
        and report.get("archive", {}).get("unix_compress")
    )
    return report
