from __future__ import annotations

import hashlib
import math
import stat
import struct
from dataclasses import dataclass
from pathlib import Path

from .errors import ReopenstepError
from .nextlabel import inspect_labels
from .rhapsody_re import UFS1_MAGIC, UFS1_MAGIC_OFFSET
from .rhapsody_re import scan_ufs1_superblocks


ROOT_INO = 2
DINODE_SIZE = 128
NDADDR = 12
NIADDR = 3


@dataclass(frozen=True)
class RdrSuperblock:
    offset: int
    byte_order: str
    fs_sblkno: int
    fs_iblkno: int
    fs_dblkno: int
    fs_cgoffset: int
    fs_cgmask: int
    fs_size: int
    fs_dsize: int
    fs_ncg: int
    fs_bsize: int
    fs_fsize: int
    fs_frag: int
    fs_bshift: int
    fs_fshift: int
    fs_nindir: int
    fs_inopb: int
    fs_cpg: int
    fs_ipg: int
    fs_fpg: int

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RdrInode:
    ino: int
    mode: int
    nlink: int
    uid: int
    gid: int
    size: int
    direct: tuple[int, ...]
    indirect: tuple[int, ...]

    @property
    def kind(self) -> str:
        masked = stat.S_IFMT(self.mode)
        if masked == stat.S_IFDIR:
            return "directory"
        if masked == stat.S_IFREG:
            return "file"
        if masked == stat.S_IFLNK:
            return "symlink"
        if masked == stat.S_IFCHR:
            return "character"
        if masked == stat.S_IFBLK:
            return "block"
        if masked == stat.S_IFIFO:
            return "fifo"
        return "unknown"

    def as_dict(self) -> dict[str, object]:
        return {
            "ino": self.ino,
            "mode": oct(self.mode),
            "kind": self.kind,
            "nlink": self.nlink,
            "uid": self.uid,
            "gid": self.gid,
            "size": self.size,
            "direct": list(self.direct),
            "indirect": list(self.indirect),
        }


@dataclass(frozen=True)
class RdrDirectoryEntry:
    ino: int
    record_length: int
    file_type: int
    name_length: int
    name: str

    def as_dict(self) -> dict[str, object]:
        return {
            "ino": self.ino,
            "record_length": self.record_length,
            "file_type": self.file_type,
            "name_length": self.name_length,
            "name": self.name,
        }


def default_root_offset(image: Path) -> int:
    preferred_fragment_size = None
    labelled_offset = None
    try:
        label = inspect_labels(image)
        labelled_offset = int(label["ufs_byte_offset"])
        if _has_native_superblock(image, labelled_offset):
            return labelled_offset
        partition = label.get("root_partition_info", {})
        preferred_fragment_size = (
            int(partition["fragment_size"])
            if isinstance(partition, dict) and int(partition.get("fragment_size", 0))
            else None
        )
    except ReopenstepError:
        pass
    prefix = _read_prefix(image, 4 * 1024 * 1024)
    candidates = [
        candidate for candidate in scan_ufs1_superblocks(prefix)
        if candidate.plausible and candidate.superblock_offset >= 0x2000
    ]
    if preferred_fragment_size is not None:
        matching = [candidate for candidate in candidates if candidate.fs_fsize == preferred_fragment_size]
        if matching:
            return matching[0].superblock_offset - 0x2000
    if candidates:
        return candidates[0].superblock_offset - 0x2000
    if labelled_offset is not None:
        return labelled_offset
    raise ReopenstepError(f"no native UFS1 superblock found in {image}")


def open_image(image: Path, *, root_offset: int | None = None) -> "RdrUfsImage":
    return RdrUfsImage(image, default_root_offset(image) if root_offset is None else root_offset)


class RdrUfsImage:
    def __init__(self, image: Path, root_offset: int):
        if not image.is_file():
            raise ReopenstepError(f"RDR UFS image not found: {image}")
        self.image = image
        self.root_offset = root_offset
        self._handle = image.open("rb")
        self.superblock = self._read_superblock(root_offset + 0x2000)

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "RdrUfsImage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def inspect(self) -> dict[str, object]:
        return {
            "image": str(self.image),
            "size": self.image.stat().st_size,
            "sha256": _sha256_file(self.image),
            "root_offset": self.root_offset,
            "superblock": self.superblock.as_dict(),
            "root_inode": self.read_inode(ROOT_INO).as_dict(),
        }

    def _read_at(self, offset: int, size: int) -> bytes:
        self._handle.seek(offset)
        data = self._handle.read(size)
        if len(data) != size:
            raise ReopenstepError(f"short read at 0x{offset:x}: expected {size}, got {len(data)}")
        return data

    def _fs_offset(self, fragment_address: int) -> int:
        return self.root_offset + fragment_address * self.superblock.fs_fsize

    def _endian_prefix(self) -> str:
        return "<" if self.superblock.byte_order == "little" else ">"

    def _read_superblock(self, offset: int) -> RdrSuperblock:
        data = self._read_at(offset, 0x600)
        byte_order = None
        for candidate_order, prefix in (("little", "<"), ("big", ">")):
            if struct.unpack_from(prefix + "I", data, UFS1_MAGIC_OFFSET)[0] == UFS1_MAGIC:
                byte_order = candidate_order
                break
        if byte_order is None:
            magic = struct.unpack_from("<I", data, UFS1_MAGIC_OFFSET)[0]
            raise ReopenstepError(f"not a native UFS1 superblock at 0x{offset:x}: magic=0x{magic:08x}")
        prefix = "<" if byte_order == "little" else ">"
        return RdrSuperblock(
            offset=offset,
            byte_order=byte_order,
            fs_sblkno=_i32(data, 0x08, prefix),
            fs_iblkno=_i32(data, 0x10, prefix),
            fs_dblkno=_i32(data, 0x14, prefix),
            fs_cgoffset=_i32(data, 0x18, prefix),
            fs_cgmask=_i32(data, 0x1C, prefix),
            fs_size=_i32(data, 0x24, prefix),
            fs_dsize=_i32(data, 0x28, prefix),
            fs_ncg=_i32(data, 0x2C, prefix),
            fs_bsize=_i32(data, 0x30, prefix),
            fs_fsize=_i32(data, 0x34, prefix),
            fs_frag=_i32(data, 0x38, prefix),
            fs_bshift=_i32(data, 0x50, prefix),
            fs_fshift=_i32(data, 0x54, prefix),
            fs_nindir=_i32(data, 0x74, prefix),
            fs_inopb=_i32(data, 0x78, prefix),
            fs_cpg=_i32(data, 0xB4, prefix),
            fs_ipg=_i32(data, 0xB8, prefix),
            fs_fpg=_i32(data, 0xBC, prefix),
        )

    def read_inode(self, ino: int) -> RdrInode:
        if ino < ROOT_INO:
            raise ReopenstepError(f"invalid inode number: {ino}")
        sb = self.superblock
        cg = ino // sb.fs_ipg
        inode_index = ino % sb.fs_ipg
        inode_fragment = self._cgbase(cg) + sb.fs_iblkno
        inode_block_index = inode_index // sb.fs_inopb
        inode_offset = (
            self.root_offset
            + (inode_fragment + inode_block_index * sb.fs_frag) * sb.fs_fsize
            + (inode_index % sb.fs_inopb) * DINODE_SIZE
        )
        data = self._read_at(inode_offset, DINODE_SIZE)
        prefix = self._endian_prefix()
        mode = _u16(data, 0x00, prefix)
        if mode == 0:
            raise ReopenstepError(f"inode {ino} is unallocated")
        direct = struct.unpack_from(prefix + "I" * NDADDR, data, 0x28)
        indirect = struct.unpack_from(prefix + "I" * NIADDR, data, 0x58)
        return RdrInode(
            ino=ino,
            mode=mode,
            nlink=_u16(data, 0x02, prefix),
            uid=_u16(data, 0x04, prefix),
            gid=_u16(data, 0x06, prefix),
            size=_u64(data, 0x08, prefix),
            direct=direct,
            indirect=indirect,
        )

    def _cgbase(self, cg: int) -> int:
        sb = self.superblock
        return sb.fs_fpg * cg + sb.fs_cgoffset * (cg & ~sb.fs_cgmask)

    def read_file(self, inode: RdrInode) -> bytes:
        if inode.kind not in {"file", "directory", "symlink"}:
            raise ReopenstepError(f"inode {inode.ino} is not readable as file data: {inode.kind}")
        chunks: list[bytes] = []
        blocks_needed = math.ceil(inode.size / self.superblock.fs_bsize)
        block_addresses = list(inode.direct[:min(blocks_needed, NDADDR)])
        remaining = blocks_needed - len(block_addresses)
        if remaining > 0 and inode.indirect[0]:
            indirect_data = self._read_at(self._fs_offset(inode.indirect[0]), self.superblock.fs_bsize)
            entries = struct.unpack_from(self._endian_prefix() + "I" * self.superblock.fs_nindir, indirect_data, 0)
            block_addresses.extend(entries[:remaining])
            remaining = blocks_needed - len(block_addresses)
        if remaining > 0:
            raise ReopenstepError(
                f"inode {inode.ino} needs double/triple indirect blocks; not implemented"
            )
        for address in block_addresses:
            if address == 0:
                chunks.append(bytes(self.superblock.fs_bsize))
            else:
                chunks.append(self._read_at(self._fs_offset(address), self.superblock.fs_bsize))
        return b"".join(chunks)[:inode.size]

    def list_dir(self, path: str = "/") -> list[RdrDirectoryEntry]:
        inode = self.resolve(path)
        if inode.kind != "directory":
            raise ReopenstepError(f"not a directory: {path}")
        return parse_directory(self.read_file(inode), self._endian_prefix())

    def resolve(self, path: str) -> RdrInode:
        if not path.startswith("/"):
            raise ReopenstepError(f"RDR UFS paths must be absolute: {path}")
        inode = self.read_inode(ROOT_INO)
        for component in [part for part in path.split("/") if part]:
            if inode.kind != "directory":
                raise ReopenstepError(f"path component is not a directory before {component}: {path}")
            entries = parse_directory(self.read_file(inode), self._endian_prefix())
            match = next((entry for entry in entries if entry.name == component), None)
            if match is None:
                raise ReopenstepError(f"path not found in RDR UFS: {path}")
            inode = self.read_inode(match.ino)
        return inode

    def extract(self, path: str, output: Path) -> dict[str, object]:
        inode = self.resolve(path)
        data = self.read_file(inode)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        return {
            "path": path,
            "output": str(output),
            "inode": inode.as_dict(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }


def parse_directory(data: bytes, endian: str = "<") -> list[RdrDirectoryEntry]:
    entries: list[RdrDirectoryEntry] = []
    offset = 0
    while offset + 8 <= len(data):
        ino = _u32(data, offset, endian)
        record_length = _u16(data, offset + 4, endian)
        if ino == 0 and record_length == 0:
            break
        if record_length < 8 or offset + record_length > len(data):
            break
        file_type = data[offset + 6]
        name_length = data[offset + 7]
        if ino != 0 and name_length <= record_length - 8:
            raw_name = data[offset + 8:offset + 8 + name_length]
            name = raw_name.decode("utf-8", errors="replace")
            entries.append(RdrDirectoryEntry(ino, record_length, file_type, name_length, name))
        offset += record_length
    return entries


def inspect_image(image: Path, *, root_offset: int | None = None) -> dict[str, object]:
    with open_image(image, root_offset=root_offset) as fs:
        return fs.inspect()


def list_path(image: Path, path: str, *, root_offset: int | None = None) -> list[dict[str, object]]:
    with open_image(image, root_offset=root_offset) as fs:
        return [entry.as_dict() for entry in fs.list_dir(path)]


def extract_path(image: Path, path: str, output: Path, *,
                 root_offset: int | None = None) -> dict[str, object]:
    with open_image(image, root_offset=root_offset) as fs:
        return fs.extract(path, output)


def _u16(data: bytes, offset: int, endian: str = "<") -> int:
    return struct.unpack_from(endian + "H", data, offset)[0]


def _u32(data: bytes, offset: int, endian: str = "<") -> int:
    return struct.unpack_from(endian + "I", data, offset)[0]


def _i32(data: bytes, offset: int, endian: str = "<") -> int:
    return struct.unpack_from(endian + "i", data, offset)[0]


def _u64(data: bytes, offset: int, endian: str = "<") -> int:
    return struct.unpack_from(endian + "Q", data, offset)[0]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_native_superblock(image: Path, root_offset: int) -> bool:
    try:
        with image.open("rb") as handle:
            handle.seek(root_offset + 0x2000 + UFS1_MAGIC_OFFSET)
            magic = handle.read(4)
            return magic in {struct.pack("<I", UFS1_MAGIC), struct.pack(">I", UFS1_MAGIC)}
    except OSError:
        return False


def _read_prefix(image: Path, size: int) -> bytes:
    with image.open("rb") as handle:
        return handle.read(size)
