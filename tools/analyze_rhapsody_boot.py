#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reopenstep_tool.rhapsody_re import analyze_boot_image


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Rhapsody DR2 i386 boot media and native UFS signatures",
    )
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--max-full-scan-bytes",
        type=lambda value: int(value, 0),
        help="Limit whole-image UFS signature scanning for large CD images.",
    )
    args = parser.parse_args()
    print(json.dumps(
        analyze_boot_image(args.image, max_full_scan_bytes=args.max_full_scan_bytes),
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
