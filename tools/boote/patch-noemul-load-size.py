#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path


SECTOR_SIZE = 2048
VIRTUAL_SECTOR_SIZE = 512
EL_TORITO_ID = b"EL TORITO SPECIFICATION"


def boot_catalog_lba(image: Path) -> int:
    with image.open("rb") as handle:
        for lba in range(16, 64):
            handle.seek(lba * SECTOR_SIZE)
            sector = handle.read(SECTOR_SIZE)
            if len(sector) != SECTOR_SIZE:
                break
            if sector[1:6] != b"CD001" or sector[6] != 1:
                continue
            if sector[0] == 0 and sector[7:39].rstrip(b" ").startswith(EL_TORITO_ID):
                return struct.unpack_from("<I", sector, 71)[0]
            if sector[0] == 255:
                break
    raise SystemExit(f"no El Torito boot catalog found in {image}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch hdiutil no-emulation El Torito load size for large cdboot payloads.",
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("boot_image", type=Path)
    args = parser.parse_args()
    load_sectors = math.ceil(args.boot_image.stat().st_size / VIRTUAL_SECTOR_SIZE)
    if load_sectors <= 0 or load_sectors > 0xFFFF:
        raise SystemExit(f"unsupported no-emulation load sector count: {load_sectors}")
    catalog_lba = boot_catalog_lba(args.image)
    with args.image.open("r+b") as handle:
        handle.seek(catalog_lba * SECTOR_SIZE + 38)
        handle.write(struct.pack("<H", load_sectors))
    print(
        f"patched no-emulation El Torito load size: "
        f"catalog_lba={catalog_lba} sectors={load_sectors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
