from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ReopenstepError


ARCHITECTURES = ("m68k", "i386", "hppa", "sparc")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.+-]+$")


@dataclass(frozen=True)
class BuildSpec:
    snapshot: str
    project: str
    target: str
    profile: str
    architectures: tuple[str, ...]
    toolchain_sha256: str
    output: str

    @classmethod
    def load(cls, path: Path) -> "BuildSpec":
        try:
            value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReopenstepError(f"cannot read build specification {path}: {exc}") from exc
        required = {"snapshot", "project", "target", "profile", "architectures", "toolchain_sha256", "output"}
        missing = sorted(required - value.keys())
        if missing:
            raise ReopenstepError("build specification is missing: " + ", ".join(missing))
        result = cls(
            snapshot=value["snapshot"], project=value["project"], target=value["target"],
            profile=value["profile"], architectures=tuple(value["architectures"]),
            toolchain_sha256=value["toolchain_sha256"], output=value["output"],
        )
        result.validate()
        return result

    def validate(self) -> None:
        for label, value in (("snapshot", self.snapshot), ("project", self.project), ("target", self.target), ("profile", self.profile)):
            if not SAFE_NAME.fullmatch(value):
                raise ReopenstepError(f"unsafe {label}: {value!r}")
        if tuple(dict.fromkeys(self.architectures)) != self.architectures:
            raise ReopenstepError("build specification repeats an architecture")
        if set(self.architectures) - set(ARCHITECTURES):
            raise ReopenstepError("build specification contains an unsupported architecture")
        if len(self.toolchain_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.toolchain_sha256.lower()):
            raise ReopenstepError("invalid toolchain SHA-256")
        output = Path(self.output)
        if output.is_absolute() or ".." in output.parts:
            raise ReopenstepError("output must be a relative path without '..'")

    def slices(self) -> list[dict[str, str]]:
        return [{"architecture": arch, "job_id": f"{self.snapshot}-{self.target}-{arch}"} for arch in self.architectures]
