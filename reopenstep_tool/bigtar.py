from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator

from .errors import ReopenstepError


BLOCK_SIZE = 512
NAME_SIZE = 225


def _octal(field: bytes, label: str, offset: int) -> int:
    value = field.split(b"\0", 1)[0].strip()
    try:
        return int(value or b"0", 8)
    except ValueError as exc:
        raise ReopenstepError(f"invalid bigtar {label} at offset {offset}") from exc


def _safe_name(raw: bytes, offset: int) -> str:
    try:
        name = raw.split(b"\0", 1)[0].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReopenstepError(f"non-UTF-8 bigtar pathname at offset {offset}") from exc
    if name in {".", "./"}:
        return "."
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReopenstepError(f"unsafe bigtar pathname at offset {offset}: {name!r}")
    return str(path)


@dataclass(frozen=True)
class BigTarEntry:
    name: str
    mode: int
    uid: int
    gid: int
    size: int
    mtime: int
    kind: str
    link_name: str | None
    header_offset: int
    data_offset: int

    @property
    def consumes_data(self) -> bool:
        return self.kind == "file"


class BigTarArchive:
    """Reader for NeXT Installer's 225-byte-path `bigtar` format."""

    def __init__(self, path: Path):
        self.path = path

    def entries(self) -> Iterator[BigTarEntry]:
        with self.path.open("rb") as stream:
            yield from self._entries(stream)

    def _entries(self, stream: BinaryIO) -> Iterator[BigTarEntry]:
        offset = 0
        while True:
            stream.seek(offset)
            header = stream.read(BLOCK_SIZE)
            if not header or not header.strip(b"\0"):
                return
            if len(header) != BLOCK_SIZE:
                raise ReopenstepError(f"truncated bigtar header at offset {offset}")
            stored = _octal(header[273:281], "checksum", offset)
            checked = bytearray(header)
            checked[273:281] = b" " * 8
            if sum(checked) != stored:
                raise ReopenstepError(f"bigtar checksum mismatch at offset {offset}")

            raw_name = header[:NAME_SIZE].split(b"\0", 1)[0]
            is_directory_name = raw_name.rstrip().endswith(b"/")
            name = _safe_name(header[:NAME_SIZE], offset)
            mode = _octal(header[225:233], "mode", offset)
            uid = _octal(header[233:241], "uid", offset)
            gid = _octal(header[241:249], "gid", offset)
            size = _octal(header[249:261], "size", offset)
            mtime = _octal(header[261:273], "mtime", offset)
            type_flag = header[281:282]
            raw_link = header[282:507].split(b"\0", 1)[0]
            if type_flag in {b"", b"\0", b"0"}:
                kind = "directory" if is_directory_name else "file"
            elif type_flag == b"1":
                kind = "hardlink"
            elif type_flag == b"2":
                kind = "symlink"
            else:
                raise ReopenstepError(
                    f"unsupported bigtar type {type_flag!r} for {name} at offset {offset}"
                )
            name = name.rstrip("/")
            link_name = _safe_name(raw_link, offset) if raw_link else None
            entry = BigTarEntry(
                name, mode, uid, gid, size, mtime, kind, link_name,
                offset, offset + BLOCK_SIZE,
            )
            yield entry
            data_blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE if entry.consumes_data else 0
            offset += BLOCK_SIZE + data_blocks * BLOCK_SIZE

    def copy_data(self, entry: BigTarEntry, destination: Path) -> None:
        if entry.kind != "file":
            raise ReopenstepError(f"bigtar entry has no file data: {entry.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("rb") as source, destination.open("wb") as target:
            source.seek(entry.data_offset)
            remaining = entry.size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ReopenstepError(f"truncated bigtar data for {entry.name}")
                target.write(chunk)
                remaining -= len(chunk)

    def extract(self, destination: Path) -> dict[str, int]:
        if destination.exists():
            if not destination.is_dir() or any(destination.iterdir()):
                raise ReopenstepError(f"bigtar extraction destination is not empty: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        entries = list(self.entries())
        for entry in entries:
            if entry.name == ".":
                continue
            target = destination.joinpath(*PurePosixPath(entry.name).parts)
            if entry.kind == "directory":
                target.mkdir(parents=True, exist_ok=True)
            elif entry.kind == "file":
                self.copy_data(entry, target)
            elif entry.kind == "symlink":
                if entry.link_name is None:
                    raise ReopenstepError(f"symlink has no target: {entry.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(entry.link_name, target)
            elif entry.kind == "hardlink":
                if entry.link_name is None:
                    raise ReopenstepError(f"hardlink has no target: {entry.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                source = destination.joinpath(*PurePosixPath(entry.link_name).parts)
                if not source.exists():
                    raise ReopenstepError(f"hardlink target precedes no file: {entry.link_name}")
                os.link(source, target)
        for entry in reversed(entries):
            if entry.name == ".":
                continue
            target = destination.joinpath(*PurePosixPath(entry.name).parts)
            if not target.is_symlink():
                os.chmod(target, entry.mode & 0o7777)
                os.utime(target, (entry.mtime, entry.mtime))
        return {
            "entries": len(entries),
            "files": sum(entry.kind == "file" for entry in entries),
            "directories": sum(entry.kind == "directory" for entry in entries),
            "links": sum(entry.kind in {"hardlink", "symlink"} for entry in entries),
        }
