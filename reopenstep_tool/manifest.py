from __future__ import annotations

import os
import json
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ReopenstepError
from .util import sha256_file


ROLE_VALUES = {
    "user_cd", "developer_cd", "install_floppy", "driver_floppy",
    "patch4", "patch4_user_tar", "patch4_developer_tar", "package", "driver_package", "boot_image", "architecture_support",
}


@dataclass(frozen=True)
class MediaEntry:
    id: str
    role: str
    filename: str
    sha256: str
    size: int
    version: str
    provenance: str
    redistribution: str
    optional: bool = False
    location: str = "vault"

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "MediaEntry":
        required = {"id", "role", "filename", "sha256", "size", "version", "provenance", "redistribution"}
        missing = sorted(required - value.keys())
        if missing:
            raise ReopenstepError("media entry is missing: " + ", ".join(missing))
        entry = cls(**{key: value[key] for key in required}, optional=bool(value.get("optional", False)), location=value.get("location", "vault"))
        if entry.role not in ROLE_VALUES:
            raise ReopenstepError(f"unsupported media role for {entry.id}: {entry.role}")
        if len(entry.sha256) != 64 or any(c not in "0123456789abcdef" for c in entry.sha256.lower()):
            raise ReopenstepError(f"invalid SHA-256 for {entry.id}")
        if entry.size < 1:
            raise ReopenstepError(f"invalid size for {entry.id}")
        if entry.location not in {"vault", "repository"}:
            raise ReopenstepError(f"unsupported media location for {entry.id}: {entry.location}")
        return entry


class MediaManifest:
    def __init__(self, path: Path, entries: list[MediaEntry]):
        self.path = path
        self.entries = entries
        ids = [entry.id for entry in entries]
        if len(ids) != len(set(ids)):
            raise ReopenstepError(f"duplicate media id in {path}")

    @classmethod
    def load(cls, path: Path) -> "MediaManifest":
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ReopenstepError(f"media manifest not found: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ReopenstepError(f"invalid media manifest {path}: {exc}") from exc
        entries = [MediaEntry.from_mapping(item) for item in data.get("media", [])]
        if not entries:
            raise ReopenstepError(f"media manifest has no [[media]] entries: {path}")
        return cls(path, entries)

    def by_id(self, media_id: str) -> MediaEntry:
        for entry in self.entries:
            if entry.id == media_id:
                return entry
        raise ReopenstepError(f"unknown media id: {media_id}")

    def resolved_by_id(self, media_id: str, vault: Path) -> MediaEntry:
        entry = self.by_id(media_id)
        overrides_path = vault / "manifest.local.json"
        if not overrides_path.is_file():
            return entry
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
            value = overrides.get(media_id)
            return replace(entry, sha256=value["sha256"], size=int(value["size"])) if value else entry
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ReopenstepError(f"invalid local vault manifest {overrides_path}: {exc}") from exc

    def verify(self, vault: Path) -> list[dict[str, Any]]:
        report = []
        for original in self.entries:
            entry = self.resolved_by_id(original.id, vault)
            path = (self.path.parent.parent / entry.filename) if entry.location == "repository" else (vault / entry.filename)
            state = "ok"
            actual_size = None
            actual_sha256 = None
            if not path.is_file():
                state = "optional-missing" if entry.optional else "missing"
            else:
                actual_size = path.stat().st_size
                if actual_size != entry.size:
                    state = "size-mismatch"
                else:
                    actual_sha256 = sha256_file(path)
                    if actual_sha256.lower() != entry.sha256.lower():
                        state = "hash-mismatch"
            report.append({
                "id": entry.id, "role": entry.role, "path": str(path), "state": state,
                "expected_size": entry.size, "actual_size": actual_size,
                "expected_sha256": entry.sha256, "actual_sha256": actual_sha256,
                "optional": entry.optional,
            })
        return report


def default_vault() -> Path:
    return Path(os.environ.get("REOPENSTEP_VAULT", "vault"))
