from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ReopenstepError


@dataclass(frozen=True)
class BuildProfile:
    name: str
    description: str
    media: tuple[str, ...]
    default_packages: tuple[str, ...]
    optional_packages: tuple[str, ...]
    boot_drivers: tuple[str, ...]
    install_drivers: tuple[str, ...]
    architectures: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "BuildProfile":
        try:
            value: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ReopenstepError(f"profile not found: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ReopenstepError(f"invalid profile {path}: {exc}") from exc
        profile = value.get("profile", {})
        if not profile.get("name"):
            raise ReopenstepError(f"profile has no name: {path}")
        return cls(
            name=profile["name"],
            description=profile.get("description", ""),
            media=tuple(value.get("media", {}).get("required", [])),
            default_packages=tuple(value.get("packages", {}).get("default", [])),
            optional_packages=tuple(value.get("packages", {}).get("optional", [])),
            boot_drivers=tuple(value.get("drivers", {}).get("boot", [])),
            install_drivers=tuple(value.get("drivers", {}).get("installed", [])),
            architectures=tuple(value.get("build", {}).get("architectures", [])),
        )

    def validate(self) -> None:
        if len(self.media) != len(set(self.media)):
            raise ReopenstepError(f"profile {self.name} repeats a media id")
        overlap = set(self.default_packages) & set(self.optional_packages)
        if overlap:
            raise ReopenstepError(f"packages are both default and optional: {', '.join(sorted(overlap))}")
        allowed_arches = {"m68k", "i386", "hppa", "sparc"}
        unknown = set(self.architectures) - allowed_arches
        if unknown:
            raise ReopenstepError(f"unsupported architectures: {', '.join(sorted(unknown))}")
