from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .errors import ReopenstepError
from .util import executable, sha256_file


SUPPORTED_QEMU_FORMATS = {"qcow", "qcow2"}


def inspect_installer_image(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReopenstepError(f"Darwin installer image not found: {path}")
    qemu_img = executable("qemu-img")
    if not qemu_img:
        raise ReopenstepError("Darwin installer image inspection requires qemu-img")
    try:
        result = subprocess.run(
            [qemu_img, "info", "--output=json", str(path)],
            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        value = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise ReopenstepError(f"cannot inspect Darwin installer image {path}: {detail.strip()}") from exc
    image_format = value.get("format")
    return {
        "path": str(path),
        "format": image_format,
        "supported_overlay_source": image_format in SUPPORTED_QEMU_FORMATS,
        "virtual_size": value.get("virtual-size"),
        "actual_size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def prepare_installer_overlay(source: Path, output: Path) -> dict[str, Any]:
    source_report = inspect_installer_image(source)
    source_format = source_report["format"]
    if source_format not in SUPPORTED_QEMU_FORMATS:
        raise ReopenstepError(f"unsupported Darwin installer source format: {source_format}")
    if output.exists():
        raise ReopenstepError(f"Darwin installer overlay already exists: {output}")
    qemu_img = executable("qemu-img")
    assert qemu_img is not None
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([
            qemu_img, "create", "-f", "qcow2", "-F", source_format,
            "-b", str(source.resolve()), str(output),
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        raise ReopenstepError(f"cannot create Darwin installer overlay: {exc.stderr.strip()}") from exc
    report = inspect_installer_image(output)
    report.update({
        "format_version": "reopenstep-darwin-installer-overlay-v1",
        "backing_image": str(source.resolve()),
        "backing_format": source_format,
        "source_sha256": source_report["sha256"],
    })
    return report


def darwin_qemu_command(qemu: str, image: Path, image_format: str,
                        display: str = "none", snapshot: bool = True,
                        machine: str = "pc-i440fx-7.2") -> list[str]:
    if image_format not in SUPPORTED_QEMU_FORMATS:
        raise ReopenstepError(f"unsupported Darwin QEMU image format: {image_format}")
    command = [
        qemu, "-machine", f"{machine},accel=tcg,acpi=off,hpet=off",
        "-cpu", "pentium", "-smp", "1", "-m", "128",
        "-boot", "order=c,menu=off",
    ]
    if snapshot:
        command.append("-snapshot")
    command.extend([
        "-drive", f"file={image},if=ide,index=0,media=disk,format={image_format}",
        "-vga", "cirrus", "-nic", "none", "-rtc", "base=localtime,clock=vm",
        "-display", display, "-monitor", "stdio", "-serial", "none",
        "-parallel", "none", "-no-reboot",
    ])
    return command
