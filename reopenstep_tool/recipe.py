from __future__ import annotations

from pathlib import Path
from typing import Any

from .manifest import MediaManifest
from .profile import BuildProfile
from .util import atomic_json


def mastering_recipe(profile: BuildProfile, manifest: MediaManifest, vault: Path) -> dict[str, Any]:
    entries = {entry.id: manifest.resolved_by_id(entry.id, vault) for entry in manifest.entries}
    return {
        "format": 1,
        "profile": profile.name,
        "description": profile.description,
        "inputs": [
            {
                "id": entries[media_id].id,
                "role": entries[media_id].role,
                "path": str(((manifest.path.parent.parent / entries[media_id].filename)
                    if entries[media_id].location == "repository" else
                    (vault / entries[media_id].filename)).resolve()),
                "sha256": entries[media_id].sha256,
                "size": entries[media_id].size,
            }
            for media_id in profile.media
        ],
        "layers": {
            "packages_default": list(profile.default_packages),
            "packages_optional": list(profile.optional_packages),
            "drivers_boot": list(profile.boot_drivers),
            "drivers_installed": list(profile.install_drivers),
        },
        "build": {"architectures": list(profile.architectures)},
        "native_outputs": {
            "ufs": f"mastered/{profile.name}/OPENSTEP42CD.UFS",
            "boot_image": f"mastered/{profile.name}/OPENSTEP_BOOT_288.img",
            "label_template": f"mastered/{profile.name}/NEXT_LABEL.bin",
            "report": f"mastered/{profile.name}/native-report.plist",
        },
    }


def write_recipe(path: Path, value: dict[str, Any]) -> None:
    atomic_json(path, value)
