import gzip
import io
import json
import struct
import tarfile
import tempfile
import unittest
from pathlib import Path

from reopenstep_tool.cli import build_parser
from reopenstep_tool.errors import ReopenstepError
from reopenstep_tool.glide import EXPECTED_PAYLOADS, prepare_reference, stage_rhapsody_driver


def tar_bytes(entries: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return stream.getvalue()


def odc_bytes(entries: list[tuple[str, int, bytes]]) -> bytes:
    output = bytearray()
    for ino, (name, mode, data) in enumerate(entries + [("TRAILER!!!", 0, b"")], 1):
        encoded = name.encode() + b"\0"
        fields = (
            b"070707",
            f"{0:o}".encode().rjust(6, b"0"),
            f"{ino:o}".encode().rjust(6, b"0"),
            f"{mode:o}".encode().rjust(6, b"0"),
            f"{0:o}".encode().rjust(6, b"0"),
            f"{0:o}".encode().rjust(6, b"0"),
            f"{1:o}".encode().rjust(6, b"0"),
            f"{0:o}".encode().rjust(6, b"0"),
            f"{0:o}".encode().rjust(11, b"0"),
            f"{len(encoded):o}".encode().rjust(6, b"0"),
            f"{len(data):o}".encode().rjust(11, b"0"),
        )
        output.extend(b"".join(fields))
        output.extend(encoded)
        output.extend(data)
    return bytes(output)


class GlideReferenceTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        macho = struct.pack(">7I", 0xFEEDFACE, 18, 0, 5, 0, 0, 0)
        payloads = {
            EXPECTED_PAYLOADS[0]: gzip.compress(tar_bytes({"./Library/Glide2": macho})),
            EXPECTED_PAYLOADS[1]: gzip.compress(tar_bytes({"./Library/Glide.pref": b"prefs"})),
            EXPECTED_PAYLOADS[2]: gzip.compress(tar_bytes({"./private/Drivers/Voodoo2_reloc": macho})),
            "Glide/ReadMe.html": b"reference",
        }
        archive = root / "Glide.tar"
        archive.write_bytes(tar_bytes(payloads))
        return archive

    def test_prepare_reference_extracts_payloads_and_describes_macho(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "reference"
            report = prepare_reference(self.fixture(root), output)
            manifest = json.loads((output / "manifest.json").read_text())
            binary = next(item for item in manifest["files"] if item["path"] == "Library/Glide2")
            self.assertEqual(binary["mach_o"]["architecture"], "ppc")
            self.assertEqual(binary["mach_o"]["kind"], "preload")
            self.assertEqual(report["output"], str(output))
            self.assertEqual((output / "package/ReadMe.html").read_bytes(), b"reference")

    def test_prepare_reference_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "reference"
            output.mkdir()
            with self.assertRaises(ReopenstepError):
                prepare_reference(self.fixture(root), output)

    def test_prepare_reference_accepts_next_odc_cpio_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cpio = odc_bytes([
                (".", 0o40775, b""),
                ("./private", 0o40775, b""),
                ("./private/Voodoo2_reloc", 0o100755, b"driver"),
            ])
            payloads = {name: gzip.compress(cpio) for name in EXPECTED_PAYLOADS}
            archive = root / "Glide.tar"
            archive.write_bytes(tar_bytes(payloads))
            output = root / "reference"
            prepare_reference(archive, output)
            self.assertEqual((output / "root/private/Voodoo2_reloc").read_bytes(), b"driver")

    def test_glide_cli_parses_reference_command(self):
        arguments = build_parser().parse_args([
            "glide", "prepare-reference", "Glide.tar", "out/glide/reference",
        ])
        self.assertEqual(arguments.group, "glide")
        self.assertEqual(arguments.action, "prepare-reference")

    def test_glide_cli_parses_dr2_reference_command(self):
        arguments = build_parser().parse_args([
            "glide", "prepare-dr2-reference", "dr2.ufs", "out/glide/dr2-sdk",
            "--root-offset", "0x200",
        ])
        self.assertEqual(arguments.action, "prepare-dr2-reference")
        self.assertEqual(arguments.root_offset, 0x200)

    def test_stage_rhapsody_driver_creates_config_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = root / "resources"
            resources.mkdir()
            (resources / "Default.table").write_text("driver")
            (resources / "Localizable.strings").write_text("strings")
            kernel = root / "kernel"
            server = root / "server"
            kernel.write_bytes(struct.pack("<7I", 0xFEEDFACE, 7, 0, 5, 0, 0, 0))
            server.write_bytes(struct.pack("<7I", 0xFEEDFACE, 7, 0, 2, 0, 0, 0))
            output = root / "Voodoo2.config"
            report = stage_rhapsody_driver(kernel, server, resources, output)
            self.assertEqual(report["output"], str(output))
            manifest = json.loads((output / "manifest.json").read_text())
            binaries = [item for item in manifest["files"] if "mach_o" in item]
            self.assertEqual({item["mach_o"]["architecture"] for item in binaries}, {"i386"})
            self.assertTrue((output / "V2Server").stat().st_mode & 0o111)

    def test_stage_rhapsody_driver_rejects_ppc_products(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = root / "resources"
            resources.mkdir()
            (resources / "Default.table").write_text("driver")
            (resources / "Localizable.strings").write_text("strings")
            ppc = struct.pack(">7I", 0xFEEDFACE, 18, 0, 5, 0, 0, 0)
            kernel = root / "kernel"
            server = root / "server"
            kernel.write_bytes(ppc)
            server.write_bytes(ppc)
            with self.assertRaises(ReopenstepError):
                stage_rhapsody_driver(
                    kernel, server, resources, root / "Voodoo2.config",
                )


if __name__ == "__main__":
    unittest.main()
