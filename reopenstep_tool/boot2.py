from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .errors import ReopenstepError
from .util import sha256_file


# boot1 loads the boot2 region at disk offset 0x5000 to physical address zero.
# Ghidra identifies the install confirmation guard at runtime 0x375a, hence
# disk-image offset 0x875a.  JZ skips the prompt only for non-install boots;
# replacing it with a short JMP preserves its target at runtime 0x37a0.
AUTOINSTALL_OFFSET = 0x875A
CONFIRM_GUARD = bytes.fromhex("85 db 74 44 c7 45 f4 39 b9 00 00")
AUTOINSTALL_GUARD = bytes.fromhex("85 db eb 44 c7 45 f4 39 b9 00 00")
LANGUAGE_OFFSET = 0x8A93
LANGUAGE_GUARD = bytes.fromhex("0f 84 a1 00 00 00 8d 45 f4 50 8d 45 f8")
# Jump directly to push 0xba3c ("English") at runtime 0x3b44.  The trailing
# NOP preserves the original six-byte instruction width.
ENGLISH_GUARD = bytes.fromhex("e9 ac 00 00 00 90 8d 45 f4 50 8d 45 f8")


def patch_autoinstall(image: Path, output: Path) -> dict[str, object]:
    if not image.is_file():
        raise ReopenstepError(f"boot image not found: {image}")
    data = image.read_bytes()
    confirm_start = AUTOINSTALL_OFFSET - 2
    confirm_end = confirm_start + len(CONFIRM_GUARD)
    language_start = LANGUAGE_OFFSET
    language_end = language_start + len(LANGUAGE_GUARD)
    if max(confirm_end, language_end) > len(data):
        raise ReopenstepError("boot image is too small to contain the OPENSTEP boot2 guard")
    confirm = data[confirm_start:confirm_end]
    language = data[language_start:language_end]
    if confirm not in (CONFIRM_GUARD, AUTOINSTALL_GUARD):
        raise ReopenstepError(
            f"unexpected confirmation bytes at 0x{confirm_start:x}: {confirm.hex()}; "
            "refusing an unverified patch"
        )
    if language not in (LANGUAGE_GUARD, ENGLISH_GUARD):
        raise ReopenstepError(
            f"unexpected language bytes at 0x{language_start:x}: {language.hex()}; "
            "refusing an unverified patch"
        )
    state = "already-patched" if confirm == AUTOINSTALL_GUARD and language == ENGLISH_GUARD else "patched"
    mutable = bytearray(data)
    mutable[AUTOINSTALL_OFFSET] = 0xEB
    mutable[language_start:language_end] = ENGLISH_GUARD
    data = bytes(mutable)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{output.name}.", dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        shutil.copymode(image, temporary)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    verified = output.read_bytes()
    if (verified[confirm_start:confirm_end] != AUTOINSTALL_GUARD or
            verified[language_start:language_end] != ENGLISH_GUARD):
        raise ReopenstepError("boot2 autoinstall patch verification failed")
    return {
        "image": str(image), "output": str(output), "state": state,
        "confirmation_offset": AUTOINSTALL_OFFSET,
        "language_offset": LANGUAGE_OFFSET,
        "sha256": sha256_file(output),
    }
