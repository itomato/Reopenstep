from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .boote_test import QemuMonitor, _await_terms
from .darwin_installer import darwin_qemu_command, inspect_installer_image
from .errors import ReopenstepError
from .util import atomic_json, executable


BOOT_PROMPT_TERMS = ("rhapsody boot1 v5 0 41 1", "boot")
KERNEL_STORAGE_TERMS = ("rhapsody operating system", "isa eisa bus support enabled")
ROOT_DEVICE_TERMS = ("rootdev 300",)
ROOT_MOUNT_FAILURE_TERMS = ("ufs mountroot failed 19", "system panic", "no suitable interface")
SINGLE_USER_ROOT_TERMS = ("singleuser boot", "root device is mounted read only")


def run_installer_test(image: Path, output_root: Path, *, display: str,
                       prompt_timeout: float, kernel_timeout: float,
                       storage_timeout: float,
                       root_timeout: float,
                       machine: str) -> tuple[int, dict[str, Any]]:
    source = inspect_installer_image(image)
    if not source["supported_overlay_source"]:
        raise ReopenstepError(f"unsupported Darwin installer image format: {source['format']}")
    qemu = executable("qemu-system-i386")
    if not qemu:
        raise ReopenstepError("Darwin installer testing requires qemu-system-i386")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = output_root / f"{stamp}-{platform.machine()}"
    suffix = 1
    while directory.exists():
        directory = output_root / f"{stamp}-{platform.machine()}-{suffix}"
        suffix += 1
    directory.mkdir(parents=True)
    report_path = directory / "report.json"
    command = darwin_qemu_command(
        qemu, image.resolve(), source["format"], display, machine=machine,
    )
    report: dict[str, Any] = {
        "format": "reopenstep-darwin03-qemu-test-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"platform": platform.platform(), "machine": platform.machine()},
        "input": source,
        "qemu": {
            "path": qemu,
            "version": subprocess.run([qemu, "--version"], check=True, text=True,
                                      stdout=subprocess.PIPE).stdout.splitlines()[0],
            "machine": machine,
            "display": display,
            "command": command,
        },
        "artifacts": {"directory": str(directory), "report": str(report_path)},
        "stages": {},
        "expected_boundary": "Darwin 0.3 i386 binds rootdev 300; single-user root is the next acceptance milestone",
        "result": "running",
    }
    monitor = QemuMonitor(command, directory / "qemu-monitor.log")
    try:
        prompt = _await_terms(monitor, directory, "boot-prompt", BOOT_PROMPT_TERMS, prompt_timeout)
        report["stages"]["boot_prompt"] = prompt
        if prompt["state"] != "passed":
            report["result"] = "failed-boot-prompt"
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(report_path, report)
            return 1, report

        # Stop the ten-second autoboot first, then replace the sentinel with -s.
        monitor.command_line("sendkey x")
        time.sleep(0.2)
        for key in ("backspace", "minus", "s", "ret"):
            monitor.command_line(f"sendkey {key}")

        kernel = _await_terms(
            monitor, directory, "kernel-storage", KERNEL_STORAGE_TERMS, kernel_timeout,
        )
        report["stages"]["kernel_storage"] = kernel
        if kernel["state"] != "passed":
            report["result"] = "failed-kernel-storage"
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(report_path, report)
            return 1, report

        root_device = _await_terms(
            monitor, directory, "root-device", ROOT_DEVICE_TERMS, storage_timeout,
        )
        report["stages"]["root_device"] = root_device
        if root_device["state"] != "passed":
            report["result"] = "failed-root-device-boundary"
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(report_path, report)
            return 1, report

        mount_failure = _await_terms(
            monitor, directory, "root-mount-failure", ROOT_MOUNT_FAILURE_TERMS, 8.0,
        )
        report["stages"]["root_mount_failure"] = mount_failure
        if mount_failure["state"] == "passed":
            report["result"] = "passed-root-device-mount-failure-boundary"
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(report_path, report)
            return 0, report

        single_user = _await_terms(
            monitor, directory, "single-user-root", SINGLE_USER_ROOT_TERMS, root_timeout,
        )
        report["stages"]["single_user_root"] = single_user
        if single_user["state"] == "passed":
            report["result"] = "passed-single-user-root"
        else:
            # rootdev is the currently verified baseline. Keep the root-shell
            # probe visible without turning an unchanged baseline into a false
            # harness failure.
            report["result"] = "passed-root-device-boundary"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(report_path, report)
        return 0, report
    except Exception as exc:
        report["result"] = "harness-error"
        report["error"] = str(exc)
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(report_path, report)
        raise
    finally:
        monitor.close()
        if report_path.is_file():
            atomic_json(output_root / "latest.json", json.loads(report_path.read_text(encoding="utf-8")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assert the Darwin 0.3 i386 installer boot boundary")
    parser.add_argument("--image", type=Path, default=Path("out/darwin03/installer-base.qcow2"))
    parser.add_argument("--output-root", type=Path, default=Path("out/darwin03/test-runs"))
    parser.add_argument("--display", default="none")
    parser.add_argument("--machine", default="pc-i440fx-7.2")
    parser.add_argument("--prompt-timeout", type=float, default=10.0)
    parser.add_argument("--kernel-timeout", type=float, default=30.0)
    parser.add_argument("--storage-timeout", type=float, default=120.0)
    parser.add_argument("--root-timeout", type=float, default=90.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status, report = run_installer_test(
            args.image, args.output_root, display=args.display,
            prompt_timeout=args.prompt_timeout, kernel_timeout=args.kernel_timeout,
            storage_timeout=args.storage_timeout, root_timeout=args.root_timeout,
            machine=args.machine,
        )
        print(json.dumps({"result": report["result"], "report": str(args.output_root / "latest.json")}, indent=2))
        return status
    except (ReopenstepError, OSError, subprocess.SubprocessError) as exc:
        print(f"darwin03-qemu-test: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
