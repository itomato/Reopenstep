from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import ReopenstepError
from .util import sha256_file
from .bigtar import BigTarArchive, BigTarEntry


PINNED_NEXTUFS_COMMIT = "6ef2908f3d7ef85f593ecb6501e8589ba55c8810"
ENTRY_RE = re.compile(r"^\s+ino=\d+\s+name='(.*)'$")
MODE_RE = re.compile(r"mode=0([0-7]+)")


@dataclass(frozen=True)
class UFSNode:
    path: str
    mode: int
    kind: str


def nextufs_executable() -> Path:
    configured = os.environ.get("NEXTUFS")
    candidate = Path(configured) if configured else Path("tools/nextufs/bin/nextufs")
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise ReopenstepError(
            "nextufs offline helper is missing; run `tools/nextufs/bootstrap.sh`"
        )
    receipt = candidate.parent / "SOURCE_COMMIT"
    if not receipt.is_file() or receipt.read_text(encoding="ascii").strip() != PINNED_NEXTUFS_COMMIT:
        raise ReopenstepError(f"unverified nextufs helper at {candidate}; rebuild it with the pinned bootstrap")
    return candidate


def _run(tool: Path, args: list[str], *, binary: bool = False) -> bytes | str:
    process = subprocess.run(
        [str(tool), *args], capture_output=True, check=False,
        text=not binary,
    )
    if process.returncode:
        stderr = process.stderr.decode(errors="replace") if binary else process.stderr
        raise ReopenstepError(f"nextufs {' '.join(args[:2])} failed: {stderr.strip()}")
    return process.stdout


def _describe(tool: Path, image: Path, path: str) -> tuple[int, list[str]]:
    output = str(_run(tool, ["browse", str(image), path]))
    marker = f"lookup '{path}':"
    if marker not in output:
        raise ReopenstepError(f"nextufs did not describe {path}")
    tail = output.split(marker, 1)[1]
    mode_match = MODE_RE.search(tail)
    if not mode_match:
        raise ReopenstepError(f"nextufs did not report a mode for {path}")
    entries = [match.group(1) for line in tail.splitlines() if (match := ENTRY_RE.match(line))]
    return int(mode_match.group(1), 8), [name for name in entries if name not in {".", ".."}]


def _exists(tool: Path, image: Path, path: str) -> bool:
    try:
        _describe(tool, image, path)
        return True
    except ReopenstepError:
        return False


def path_exists(image: Path, path: str, tool: Path | None = None) -> bool:
    helper = tool or nextufs_executable()
    return _exists(helper, image, path)


def overlay_bigtar(image: Path, output: Path, archive: BigTarArchive,
                   entries: list[BigTarEntry] | None = None) -> dict[str, object]:
    """Apply a NeXT package payload to a disposable UFS copy."""
    tool = nextufs_executable()
    if not image.is_file():
        raise ReopenstepError(f"UFS image not found: {image}")
    if image.resolve() == output.resolve():
        raise ReopenstepError("Patch overlay output must be different from its source image")
    members = entries if entries is not None else list(archive.entries())
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reopenstep-ufs-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        working = temp / output.name
        shutil.copy2(image, working)
        os.chmod(working, 0o644)
        completed: set[str] = set()
        for index, entry in enumerate(members):
            if entry.name == ".":
                completed.add(entry.name)
                continue
            target = "/" + entry.name
            exists = _exists(tool, working, target)
            if entry.kind == "directory":
                if not exists:
                    _run(tool, ["mkfile", "--mkdir", str(working), target])
            elif entry.kind == "file":
                host_file = temp / f"payload-{index:04d}"
                archive.copy_data(entry, host_file)
                if exists:
                    _run(tool, ["mkfile", "--unlink", str(working), target])
                _run(tool, ["mkfile", "--from-file", str(working), target, str(host_file)])
            elif entry.kind == "symlink":
                if entry.link_name is None:
                    raise ReopenstepError(f"symlink has no target: {entry.name}")
                if exists:
                    _run(tool, ["mkfile", "--unlink", str(working), target])
                _run(tool, ["mkfile", "--symlink", str(working), entry.link_name, target])
            elif entry.kind == "hardlink":
                if entry.link_name is None:
                    raise ReopenstepError(f"hardlink has no target: {entry.name}")
                source = "/" + entry.link_name
                if entry.link_name not in completed and not _exists(tool, working, source):
                    raise ReopenstepError(f"hardlink target does not exist: {source}")
                if exists:
                    _run(tool, ["mkfile", "--unlink", str(working), target])
                _run(tool, ["mkfile", "--link", str(working), source, target])
            _run(tool, ["mkfile", "--chmod", str(working), target, f"{entry.mode & 0o7777:o}"])
            _run(tool, ["mkfile", "--chown", str(working), target, str(entry.uid), str(entry.gid)])
            _run(tool, ["mkfile", "--utimes", str(working), target, str(entry.mtime), str(entry.mtime)])
            completed.add(entry.name)

        verified: dict[str, str] = {}
        for path in (
            "mach_kernel", "usr/standalone/i386/boot",
            "private/Drivers/i386/VBE20DisplayDriver.config/Default.table",
            "private/Drivers/i386/VBE20DisplayDriver.config/VBE20DisplayDriver",
            "private/Drivers/i386/VBE20DisplayDriver.config/VBE20DisplayDriver_reloc",
            "NextLibrary/Frameworks/AppKit.framework/Versions/B/AppKit",
            "NextLibrary/Frameworks/Foundation.framework/Versions/B/Foundation",
            "usr/shlib/libFoundation_s.E.shlib",
        ):
            entry = next((member for member in members if member.name == path), None)
            if entry is None or entry.kind != "file":
                continue
            expected = temp / ("expected-" + str(len(verified)))
            actual = temp / ("actual-" + str(len(verified)))
            archive.copy_data(entry, expected)
            _extract(tool, working, "/" + path, actual)
            if sha256_file(expected) != sha256_file(actual):
                raise ReopenstepError(f"post-overlay UFS verification failed for /{path}")
            verified["/" + path] = sha256_file(actual)
        os.replace(working, output)
    return {
        "image": str(image), "output": str(output), "entries": len(members),
        "files": sum(entry.kind == "file" for entry in members),
        "directories": sum(entry.kind == "directory" for entry in members),
        "links": sum(entry.kind in {"hardlink", "symlink"} for entry in members),
        "verified": verified, "sha256": sha256_file(output),
        "nextufs_commit": PINNED_NEXTUFS_COMMIT,
    }


def tree_inventory(image: Path, root: str, tool: Path | None = None) -> list[UFSNode]:
    helper = tool or nextufs_executable()
    result: list[UFSNode] = []

    def visit(path: str) -> None:
        mode, entries = _describe(helper, image, path)
        kind = "directory" if mode & 0o170000 == 0o040000 else "file"
        result.append(UFSNode(path, mode, kind))
        if kind == "directory":
            for name in entries:
                visit(str(PurePosixPath(path) / name))

    visit(root)
    return result


def _extract(tool: Path, image: Path, path: str, destination: Path) -> None:
    data = _run(tool, ["browse", "--raw", str(image), path], binary=True)
    destination.write_bytes(bytes(data))


def extract_file(image: Path, path: str, destination: Path) -> dict[str, object]:
    tool = nextufs_executable()
    mode, entries = _describe(tool, image, path)
    if mode & 0o170000 == 0o040000:
        raise ReopenstepError(f"UFS path is a directory: {path}")
    if entries:
        raise ReopenstepError(f"unexpected directory entries for UFS file: {path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _extract(tool, image, path, destination)
    return {
        "image": str(image), "path": path, "output": str(destination),
        "mode": mode & 0o7777, "size": destination.stat().st_size,
        "sha256": sha256_file(destination), "nextufs_commit": PINNED_NEXTUFS_COMMIT,
    }


def extract_tree(image: Path, root: str, destination: Path) -> dict[str, object]:
    tool = nextufs_executable()
    nodes = tree_inventory(image, root, tool)
    if nodes[0].kind != "directory":
        raise ReopenstepError(f"UFS path is not a directory: {root}")
    if destination.exists() and any(destination.iterdir()):
        raise ReopenstepError(f"extraction destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    source_root = PurePosixPath(root)
    files = 0
    for node in nodes[1:]:
        relative = PurePosixPath(node.path).relative_to(source_root)
        target = destination / Path(*relative.parts)
        if node.kind == "directory":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            _extract(tool, image, node.path, target)
            files += 1
        os.chmod(target, node.mode & 0o7777)
    return {
        "image": str(image), "root": root, "output": str(destination),
        "files": files, "directories": sum(node.kind == "directory" for node in nodes),
        "nextufs_commit": PINNED_NEXTUFS_COMMIT,
    }


def replace_file(image: Path, path: str, source: Path, output: Path,
                 mode: int = 0o444) -> dict[str, object]:
    tool = nextufs_executable()
    if not source.is_file():
        raise ReopenstepError(f"replacement source is not a file: {source}")
    _describe(tool, image, path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reopenstep-ufs-", dir=output.parent) as temp_name:
        working = Path(temp_name) / output.name
        shutil.copy2(image, working)
        os.chmod(working, 0o644)
        _run(tool, ["mkfile", "--unlink", str(working), path])
        _run(tool, ["mkfile", "--from-file", str(working), path, str(source)])
        _run(tool, ["mkfile", "--chmod", str(working), path, f"{mode:o}"])
        extracted = Path(temp_name) / "verify"
        _extract(tool, working, path, extracted)
        if extracted.read_bytes() != source.read_bytes():
            raise ReopenstepError("post-write UFS file verification failed")
        os.replace(working, output)
    return {
        "image": str(image), "path": path, "source": str(source),
        "output": str(output), "mode": mode, "size": source.stat().st_size,
        "sha256": sha256_file(output), "nextufs_commit": PINNED_NEXTUFS_COMMIT,
    }


def insert_tree(source: Path, source_root: str, destination: Path,
                destination_root: str, output: Path) -> dict[str, object]:
    tool = nextufs_executable()
    source_nodes = tree_inventory(source, source_root, tool)
    if source_nodes[0].kind != "directory":
        raise ReopenstepError(f"source UFS path is not a directory: {source_root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reopenstep-ufs-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        working = temp / output.name
        shutil.copy2(destination, working)
        os.chmod(working, 0o644)
        _run(tool, ["mkfile", "--mkdir", str(working), destination_root])
        source_base = PurePosixPath(source_root)
        for index, node in enumerate(source_nodes[1:], start=1):
            relative = PurePosixPath(node.path).relative_to(source_base)
            target = str(PurePosixPath(destination_root) / relative)
            if node.kind == "directory":
                _run(tool, ["mkfile", "--mkdir", str(working), target])
            else:
                host_file = temp / f"file-{index:04d}"
                _extract(tool, source, node.path, host_file)
                _run(tool, ["mkfile", "--from-file", str(working), target, str(host_file)])
            _run(tool, ["mkfile", "--chmod", str(working), target, f"{node.mode & 0o7777:o}"])
        verification = tree_inventory(working, destination_root, tool)
        if len(verification) != len(source_nodes):
            raise ReopenstepError("post-insert UFS tree verification failed")
        os.replace(working, output)
    return {
        "source": str(source), "source_root": source_root,
        "destination": str(destination), "destination_root": destination_root,
        "output": str(output), "files": sum(node.kind == "file" for node in source_nodes),
        "directories": sum(node.kind == "directory" for node in source_nodes),
        "sha256": sha256_file(output), "nextufs_commit": PINNED_NEXTUFS_COMMIT,
    }


def replace_tree(source: Path, source_root: str, destination: Path, destination_root: str,
                 output: Path) -> dict[str, object]:
    tool = nextufs_executable()
    source_nodes = tree_inventory(source, source_root, tool)
    destination_nodes = tree_inventory(destination, destination_root, tool)
    if source_nodes[0].kind != "directory" or destination_nodes[0].kind != "directory":
        raise ReopenstepError("driver bundle roots must both be directories")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reopenstep-ufs-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        working = temp / output.name
        shutil.copy2(destination, working)
        # Installer boot images are commonly distributed read-only; the
        # disposable working copy must be writable for offline UFS mutation.
        os.chmod(working, 0o644)
        for node in reversed(destination_nodes[1:]):
            operation = "--rmdir" if node.kind == "directory" else "--unlink"
            _run(tool, ["mkfile", operation, str(working), node.path])

        mapping: dict[str, str] = {}
        for node in source_nodes[1:]:
            relative = PurePosixPath(node.path).relative_to(PurePosixPath(source_root))
            target = str(PurePosixPath(destination_root) / relative)
            mapping[node.path] = target
            if node.kind == "directory":
                _run(tool, ["mkfile", "--mkdir", str(working), target])
            else:
                host_file = temp / f"file-{len(mapping):04d}"
                _extract(tool, source, node.path, host_file)
                _run(tool, ["mkfile", "--from-file", str(working), target, str(host_file)])
            _run(tool, ["mkfile", "--chmod", str(working), target, f"{node.mode & 0o7777:o}"])

        verification = tree_inventory(working, destination_root, tool)
        expected = {mapping[node.path] for node in source_nodes[1:]}
        actual = {node.path for node in verification[1:]}
        if expected != actual:
            raise ReopenstepError("post-write UFS tree verification failed")
        os.replace(working, output)
    return {
        "source": str(source), "source_root": source_root,
        "destination": str(destination), "destination_root": destination_root,
        "output": str(output), "files": sum(node.kind == "file" for node in source_nodes),
        "directories": sum(node.kind == "directory" for node in source_nodes),
        "sha256": sha256_file(output), "nextufs_commit": PINNED_NEXTUFS_COMMIT,
    }
