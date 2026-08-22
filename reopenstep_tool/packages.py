from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from .errors import ReopenstepError
from .util import executable, run, sha256_file


PACKAGE_COMPONENTS = (".info", ".bom", ".sizes", ".tar.Z")
DRIVER_NAME_BYTES = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.+-")


def config_names_in_bytes(data: bytes) -> list[str]:
    values: list[str] = []
    cursor = 0
    suffix = b".config"
    while (end := data.find(suffix, cursor)) >= 0:
        start = end
        floor = max(0, end - 128)
        while start > floor and data[start - 1] in DRIVER_NAME_BYTES:
            start -= 1
        if end - start >= 3:
            values.append(data[start:end + len(suffix)].decode("ascii"))
        cursor = end + len(suffix)
    return values


@dataclass(frozen=True)
class PackageRecord:
    name: str
    components: tuple[str, ...]
    complete: bool


def archive_members(path: Path) -> list[str]:
    tool = executable("bsdtar")
    if not tool:
        raise ReopenstepError("bsdtar is required to inventory package media")
    return [line.strip().lstrip("./") for line in run([tool, "-tf", str(path)], capture=True).splitlines() if line.strip()]


def package_inventory(path: Path) -> list[PackageRecord]:
    members = archive_members(path)
    packages: dict[str, set[str]] = {}
    for member in members:
        parts = PurePosixPath(member).parts
        for index, part in enumerate(parts):
            if part.lower().endswith(".pkg"):
                package_path = "/".join(parts[:index + 1])
                packages.setdefault(package_path, set()).add(member)
                break
    records: list[PackageRecord] = []
    for package, files in sorted(packages.items()):
        stem = PurePosixPath(package).name[:-4]
        basenames = {PurePosixPath(item).name for item in files}
        present = tuple(component for component in PACKAGE_COMPONENTS if stem + component in basenames)
        records.append(PackageRecord(package, present, len(present) == len(PACKAGE_COMPONENTS)))
    return records


def driver_configs(path: Path) -> tuple[str, ...]:
    if path.is_dir():
        values = [item.name for item in path.rglob("*.config") if item.is_dir()]
    elif path.stat().st_size in {1_474_560, 2_949_120}:
        values = config_names_in_bytes(path.read_bytes())
    else:
        try:
            values = [PurePosixPath(item).name for item in archive_members(path) if item.lower().endswith(".config")]
        except ReopenstepError:
            values = config_names_in_bytes(path.read_bytes())
    return tuple(sorted(set(values)))


def collision_report(paths: Iterable[Path]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for path in paths:
        for config in driver_configs(path):
            owners.setdefault(config.lower(), []).append(str(path))
    return {name: sources for name, sources in owners.items() if len(sources) > 1}


def fingerprint(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256_file(path)}
