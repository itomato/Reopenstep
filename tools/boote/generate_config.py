#!/usr/bin/env python3
"""Generate Chameleon's Kconfig outputs without building the curses UI."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path


SYMBOL = re.compile(r"^[A-Z][A-Z0-9_]*$")


def atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.boote.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def load_profile(path: Path) -> tuple[str, dict[str, str], dict[str, bool]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    name = data.get("name")
    strings = data.get("strings", {})
    booleans = data.get("booleans", {})
    if not isinstance(name, str) or not name:
        raise SystemExit("BootE profile requires a non-empty name")
    if not isinstance(strings, dict) or not isinstance(booleans, dict):
        raise SystemExit("BootE strings and booleans must be TOML tables")
    for key, value in strings.items():
        if not SYMBOL.fullmatch(key) or not isinstance(value, str):
            raise SystemExit(f"invalid string setting {key!r}")
    for key, value in booleans.items():
        if not SYMBOL.fullmatch(key) or not isinstance(value, bool):
            raise SystemExit(f"invalid boolean setting {key!r}")
    overlap = set(strings) & set(booleans)
    if overlap:
        raise SystemExit(f"symbols have conflicting types: {', '.join(sorted(overlap))}")
    return name, strings, booleans


def render(profile: Path) -> dict[str, str]:
    name, strings, booleans = load_profile(profile)
    banner = f"Generated deterministically from {profile.name} ({name}); do not edit."
    config = ["#", f"# {banner}", "#"]
    header = ["//", f"// {banner}", "//", "#define CONFIG_IS_BUILTIN 1", "#define CONFIG_IS_MODULE 2"]
    assembly = [";", f"; {banner}", ";"]

    for key in sorted(strings):
        escaped = strings[key].replace("\\", "\\\\").replace('"', '\\"')
        config.append(f'CONFIG_{key}="{escaped}"')
        header.append(f'#define CONFIG_{key} "{escaped}"')
    for key in sorted(booleans):
        enabled = booleans[key]
        config.append(f"CONFIG_{key}=y" if enabled else f"# CONFIG_{key} is not set")
        assembly.append(f"CONFIG_{key} EQU {1 if enabled else 0}")
        if enabled:
            header.append(f"#define CONFIG_{key} CONFIG_IS_BUILTIN")

    common = "\n".join(config) + "\n"
    return {
        ".config": common,
        "auto.conf": common,
        "autoconf.h": "\n".join(header) + "\n",
        "autoconf.inc": "\n".join(assembly) + "\n",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = render(args.profile)
    if args.check:
        print(json.dumps({name: len(value.encode()) for name, value in outputs.items()}, sort_keys=True))
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required unless --check is used")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Write .config first so every generated dependent is at least as new.
    for name in (".config", "auto.conf", "autoconf.h", "autoconf.inc"):
        atomic_text(args.output_dir / name, outputs[name])
    print(json.dumps({"profile": str(args.profile), "output_dir": str(args.output_dir), "files": list(outputs)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
