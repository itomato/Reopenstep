from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ReopenstepError
from .iso import inspect_el_torito, require_bootable
from .nextlabel import inspect_labels
from .util import atomic_json, executable, sha256_file


BOOT_PROMPT_TERMS = ("boot v5 0 133",)
UFS_PROMPT_TERMS = ("boot v5 0 133", "next ufs")
EISA_TERMS = ("next mach 4 2", "missing eisa kernel bus class", "system panic")
EIDE_TERMS = ("isa eisa bus support enabled", "disk label openstep 4 2", "rootdev")
CDROM_TERMS = ("isa eisa bus support enabled", "no scsi controller or cd rom drive found")


def normalized_screen_text(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def screen_has_terms(text: str, terms: tuple[str, ...]) -> bool:
    normalized = normalized_screen_text(text)
    return all(term in normalized for term in terms)


def sampled_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    size = path.stat().st_size
    offsets = sorted({0, max(0, size // 2 - chunk_size // 2), max(0, size - chunk_size)})
    digest = hashlib.sha256()
    digest.update(f"size:{size}\n".encode("ascii"))
    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            data = handle.read(chunk_size)
            digest.update(f"offset:{offset}:length:{len(data)}\n".encode("ascii"))
            digest.update(data)
    return digest.hexdigest()


def _disk_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".vhd":
        return "vpc"
    if suffix == ".qcow2":
        return "qcow2"
    return "raw"


def _convert_screenshot(source: Path, destination: Path) -> tuple[Path, str]:
    if tool := executable("magick"):
        subprocess.run([tool, str(source), str(destination)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return destination, tool
    if tool := executable("sips"):
        subprocess.run([tool, "-s", "format", "png", str(source), "--out", str(destination)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return destination, tool
    preserved = destination.with_suffix(".ppm")
    shutil.copy2(source, preserved)
    return preserved, "none"


def _ocr(path: Path) -> tuple[str, str]:
    tool = executable("tesseract")
    if not tool:
        raise ReopenstepError("BootE QEMU assertions require tesseract OCR")
    result = subprocess.run([tool, str(path), "stdout", "--psm", "6"], check=True,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout, tool


class QemuMonitor:
    def __init__(self, command: list[str], log: Path):
        self.command = command
        self.log_path = log
        self.log_handle = log.open("wb")
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )

    def command_line(self, value: str) -> None:
        if self.process.poll() is not None:
            self.log_handle.flush()
            detail = self.log_path.read_text(encoding="utf-8", errors="replace").strip()
            raise ReopenstepError(f"QEMU exited before monitor command ({self.process.returncode}): {detail}")
        assert self.process.stdin is not None
        self.process.stdin.write((value + "\n").encode("ascii"))
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.command_line("quit")
                self.process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired, ReopenstepError):
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        self.log_handle.close()


def _capture(monitor: QemuMonitor, directory: Path, name: str) -> tuple[Path, str, str, str]:
    ppm = directory / f".{name}-probe.ppm"
    png = directory / f"{name}.png"
    monitor.command_line(f"screendump {ppm}")
    time.sleep(0.2)
    if not ppm.is_file() or ppm.stat().st_size < 64:
        raise ReopenstepError(f"QEMU did not produce the {name} screenshot")
    image, converter = _convert_screenshot(ppm, png)
    text, ocr_tool = _ocr(image)
    ppm.unlink(missing_ok=True)
    (directory / f"{name}.txt").write_text(text, encoding="utf-8")
    return image, text, converter, ocr_tool


def _await_terms(monitor: QemuMonitor, directory: Path, name: str,
                 terms: tuple[str, ...], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    last_text = ""
    converter = ""
    ocr_tool = ""
    attempts = 0
    while time.monotonic() - started < timeout:
        attempts += 1
        image, last_text, converter, ocr_tool = _capture(monitor, directory, name)
        if screen_has_terms(last_text, terms):
            return {
                "state": "passed", "elapsed_seconds": round(time.monotonic() - started, 3),
                "attempts": attempts, "expected_terms": list(terms), "image": str(image),
                "transcript": str(directory / f"{name}.txt"), "text": last_text,
                "converter": converter, "ocr": ocr_tool,
            }
        time.sleep(0.8)
    return {
        "state": "failed", "elapsed_seconds": round(time.monotonic() - started, 3),
        "attempts": attempts, "expected_terms": list(terms), "text": last_text,
    }


def qemu_command(qemu: str, iso: Path, disk: Path | None, display: str,
                 cpu: str = "pentium3", cdrom: str = "ide") -> list[str]:
    command = [
        qemu, "-machine", "pc", "-cpu", cpu, "-m", "512",
        "-accel", "tcg,thread=single", "-boot", "d", "-snapshot",
    ]
    if disk is not None:
        command.extend(["-drive", f"file={disk},if=ide,index=0,media=disk,format={_disk_format(disk)}"])
    if cdrom == "ide":
        command.extend([
            # The installer EIDE table probes primary-master when no disk is
            # present; with a target disk, keep the CD on primary slave.
            "-drive", f"file={iso},if=ide,index={1 if disk is not None else 0},media=cdrom,readonly=on",
        ])
    elif cdrom == "amd-scsi":
        command.extend([
            "-device", "am53c974,id=openstep-scsi",
            "-drive", f"file={iso},if=none,id=openstep-cd,media=cdrom,readonly=on",
            "-device", "scsi-cd,drive=openstep-cd,bus=openstep-scsi.0,scsi-id=6",
        ])
    else:
        raise ReopenstepError(f"unsupported QEMU CD-ROM controller: {cdrom}")
    command.extend([
        "-display", display, "-monitor", "stdio", "-serial", "none",
        "-parallel", "none", "-nic", "none", "-rtc", "base=utc", "-no-reboot",
    ])
    return command


def run_qemu_test(iso: Path, disk: Path | None, output_root: Path, *, display: str,
                  prompt_timeout: float, handoff_timeout: float, expectation: str,
                  full_disk_hash: bool = False,
                  cpu: str = "pentium3", cdrom: str = "ide") -> tuple[int, dict[str, Any]]:
    if not iso.is_file():
        raise ReopenstepError(f"BootE ISO not found: {iso}")
    if disk is not None and not disk.is_file():
        raise ReopenstepError(f"BootE test disk not found: {disk}")
    qemu = executable("qemu-system-i386")
    if not qemu:
        raise ReopenstepError("BootE QEMU assertions require qemu-system-i386")
    require_bootable(inspect_el_torito(iso))
    label_source = disk if disk is not None else iso
    label = inspect_labels(label_source) if expectation != "prompt" or disk is not None else None
    if label is not None and (not label.get("checksum_valid") or label.get("version") != "dlV3"):
        medium = "disk" if disk is not None else "ISO"
        raise ReopenstepError(f"BootE test {medium} does not have a valid dlV3 label")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = output_root / f"{stamp}-{platform.machine()}"
    suffix = 1
    while directory.exists():
        directory = output_root / f"{stamp}-{platform.machine()}-{suffix}"
        suffix += 1
    directory.mkdir(parents=True)
    report_path = directory / "report.json"
    command = qemu_command(
        qemu, iso.resolve(), disk.resolve() if disk is not None else None, display, cpu, cdrom
    )
    disk_input = None
    if disk is not None:
        disk_input = {
            "path": str(disk), "size": disk.stat().st_size,
            "sampled_sha256": sampled_sha256(disk), "next_label": label,
        }
        if full_disk_hash:
            disk_input["sha256"] = sha256_file(disk)
    report: dict[str, Any] = {
        "format": "reopenstep-boote-qemu-test-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"platform": platform.platform(), "machine": platform.machine()},
        "artifacts": {"directory": str(directory), "report": str(report_path)},
        "inputs": {
            "iso": str(iso), "iso_sha256": sha256_file(iso),
            "iso_next_label": label if disk is None else None,
            "disk": disk_input,
        },
        "qemu": {
            "path": qemu, "display": display, "cdrom": cdrom, "command": command,
            "version": subprocess.run([qemu, "--version"], check=True, text=True,
                                      stdout=subprocess.PIPE).stdout.splitlines()[0],
        },
        "stages": {},
        "expectation": expectation,
        "expected_boundary": ({
            "eisa": "Missing EISA kernel bus class",
            "eide": "EISA linked; EIDE disk and hd0a root selected",
            "cdrom": "Patch 4 loaded from CD; native ATAPI attachment boundary",
        }).get(expectation),
        "result": "running",
    }
    monitor = QemuMonitor(command, directory / "qemu-monitor.log")
    try:
        prompt_terms = BOOT_PROMPT_TERMS if expectation == "prompt" else UFS_PROMPT_TERMS
        prompt_name = "boot-prompt" if expectation == "prompt" else "ufs-prompt"
        prompt = _await_terms(monitor, directory, prompt_name, prompt_terms, prompt_timeout)
        report["stages"][prompt_name.replace("-", "_")] = prompt
        if prompt["state"] != "passed":
            report["result"] = f"failed-{prompt_name}"
            atomic_json(report_path, report)
            return 1, report
        if expectation in {"prompt", "ufs"}:
            report["result"] = f"passed-{prompt_name}"
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            atomic_json(report_path, report)
            return 0, report
        monitor.command_line("sendkey ret")
        handoff_terms = {"eide": EIDE_TERMS, "cdrom": CDROM_TERMS}.get(expectation, EISA_TERMS)
        handoff = _await_terms(monitor, directory, "openstep-handoff", handoff_terms, handoff_timeout)
        report["stages"]["openstep_handoff"] = handoff
        kernbootstruct = (directory / "kernbootstruct.bin").resolve()
        monitor.command_line(f'pmemsave 0x11000 0xf000 "{kernbootstruct}"')
        time.sleep(0.2)
        if kernbootstruct.is_file():
            report["artifacts"]["kernbootstruct"] = str(kernbootstruct)
        if handoff["state"] != "passed":
            report["result"] = "failed-openstep-handoff"
            atomic_json(report_path, report)
            return 1, report
        report["result"] = f"passed-expected-{expectation}-boundary"
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
            latest = output_root / "latest.json"
            atomic_json(latest, json.loads(report_path.read_text(encoding="utf-8")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assert the BootE QEMU/OPENSTEP handoff ladder")
    parser.add_argument("--iso", type=Path, default=Path("out/boote/boote-smoke.iso"))
    parser.add_argument("--disk", type=Path, default=Path("out/openstep-user-ufs.raw"))
    parser.add_argument("--no-disk", action="store_true")
    parser.add_argument("--expect", choices=("prompt", "ufs", "eisa", "eide", "cdrom"), default="eisa")
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--test-vhd", type=Path, default=Path("test.VHD"))
    parser.add_argument("--full-disk-hash", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("out/boote/test-runs"))
    parser.add_argument("--display", default=("cocoa" if sys.platform == "darwin" else "sdl"))
    parser.add_argument("--cpu", default="pentium3")
    parser.add_argument("--cdrom", choices=("ide", "amd-scsi"), default="ide")
    parser.add_argument("--prompt-timeout", type=float, default=20.0)
    parser.add_argument("--handoff-timeout", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.matrix:
            started = datetime.now(timezone.utc).isoformat()
            cases: list[dict[str, Any]] = []
            status = 0
            for expectation, disk in (("prompt", None), ("ufs", args.test_vhd), ("eisa", args.disk)):
                case_status, report = run_qemu_test(
                    args.iso, disk, args.output_root, display=args.display, expectation=expectation,
                    prompt_timeout=args.prompt_timeout, handoff_timeout=args.handoff_timeout,
                    full_disk_hash=(args.full_disk_hash and expectation == "eisa"),
                    cpu=args.cpu,
                )
                status = max(status, case_status)
                cases.append({
                    "expectation": expectation, "result": report["result"],
                    "report": report["artifacts"]["report"],
                })
            matrix = {
                "format": "reopenstep-boote-qemu-matrix-v1", "started_utc": started,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "passed": status == 0, "cases": cases,
            }
            matrix_path = args.output_root / "matrix-latest.json"
            atomic_json(matrix_path, matrix)
            print(json.dumps({"passed": matrix["passed"], "report": str(matrix_path), "cases": cases}, indent=2))
            return status
        disk = None if args.no_disk else args.disk
        status, report = run_qemu_test(
            args.iso, disk, args.output_root, display=args.display, expectation=args.expect,
            prompt_timeout=args.prompt_timeout, handoff_timeout=args.handoff_timeout,
            full_disk_hash=args.full_disk_hash,
            cpu=args.cpu, cdrom=args.cdrom,
        )
        print(json.dumps({"result": report["result"], "report": str(args.output_root / "latest.json")}, indent=2))
        return status
    except (ReopenstepError, OSError, subprocess.SubprocessError) as exc:
        print(f"boote-qemu-test: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
