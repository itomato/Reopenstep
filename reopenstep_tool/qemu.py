from __future__ import annotations

from pathlib import Path

from .errors import ReopenstepError
from .util import executable, run


PINNED_MACHINE = "pc-i440fx-7.2"


def qemu_command(iso: Path, disk: Path | None = None, *, headless: bool = False) -> list[str]:
    qemu = executable("qemu-system-i386")
    if not qemu:
        raise ReopenstepError("qemu-system-i386 is required")
    command = [
        qemu, "-machine", PINNED_MACHINE, "-cpu", "pentium", "-m", "128",
        "-boot", "order=d", "-cdrom", str(iso), "-vga", "cirrus",
        "-device", "ne2k_isa,netdev=net0", "-netdev", "user,id=net0",
    ]
    if disk:
        command.extend(["-drive", f"file={disk},format=raw,if=ide,index=0"])
    if headless:
        command.extend(["-display", "none", "-no-reboot"])
    return command


def qemu_version() -> str:
    qemu = executable("qemu-system-i386")
    if not qemu:
        raise ReopenstepError("qemu-system-i386 is required")
    return run([qemu, "--version"], capture=True).splitlines()[0]
