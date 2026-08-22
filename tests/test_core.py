import json
import struct
import tempfile
import unittest
from pathlib import Path

from reopenstep_tool.buildspec import BuildSpec
from reopenstep_tool.errors import ReopenstepError
from reopenstep_tool.fat import inspect_fat, require_quad_fat
from reopenstep_tool.iso import inspect_el_torito, require_bootable
from reopenstep_tool.hybrid import label_candidates, patch_label
from reopenstep_tool.manifest import MediaManifest
from reopenstep_tool.nextlabel import CHECKSUM_OFFSET, checksum_v3, parse_label, update_template
from reopenstep_tool.profile import BuildProfile
from reopenstep_tool.disk import master_ufs_disk


ROOT = Path(__file__).resolve().parents[1]


class ExistingMediaTests(unittest.TestCase):
    def test_checked_in_iso_has_valid_boot_catalog(self):
        report = inspect_el_torito(ROOT / "test.iso")
        require_bootable(report)
        self.assertEqual(report["media_type"], 3)
        self.assertEqual(report["boot_lba"], 34)
        self.assertGreater(report["boot_sectors"], 0)


class ManifestTests(unittest.TestCase):
    def test_profiles_are_well_formed_and_reference_manifest(self):
        manifest = MediaManifest.load(ROOT / "media/manifest.toml")
        for path in (ROOT / "profiles").glob("*.toml"):
            profile = BuildProfile.load(path)
            profile.validate()
            for media_id in profile.media:
                manifest.by_id(media_id)

    def test_local_vault_manifest_resolves_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            payload = vault / "OpenStep-4.2-User.iso"
            payload.write_bytes(b"media")
            import hashlib
            digest = hashlib.sha256(b"media").hexdigest()
            (vault / "manifest.local.json").write_text(json.dumps({"openstep42-user": {"size": 5, "sha256": digest}}))
            manifest = MediaManifest.load(ROOT / "media/manifest.toml")
            report = {item["id"]: item for item in manifest.verify(vault)}
            self.assertEqual(report["openstep42-user"]["state"], "ok")


class FatBinaryTests(unittest.TestCase):
    def test_quad_fat_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quad"
            count = 4
            offset = 8 + count * 20
            table = bytearray(struct.pack(">II", 0xCAFEBABE, count))
            payload = bytearray()
            for cpu in (6, 7, 11, 14):
                table.extend(struct.pack(">IIIII", cpu, 0, offset + len(payload), 4, 0))
                payload.extend(b"test")
            path.write_bytes(table + payload)
            report = inspect_fat(path)
            require_quad_fat(report)
            self.assertEqual({a["architecture"] for a in report["architectures"]}, {"m68k", "i386", "hppa", "sparc"})


class HybridTests(unittest.TestCase):
    def test_label_patch_is_explicit_and_big_endian(self):
        label = patch_label(bytes(7680), 120, 0x1234, "u32be")
        self.assertEqual(label[120:124], b"\x00\x00\x12\x34")

    def test_label_candidate_offsets_are_reported_by_format(self):
        label = bytearray(7680)
        struct.pack_into(">I", label, 101, 80)
        candidates = label_candidates(bytes(label), 80)
        self.assertIn(101, candidates["u32be"])

    def test_next_v3_checksum_and_partition_update(self):
        label = bytearray(7680)
        label[:4] = b"dlV3"
        label[12:16] = b"TEST"
        struct.pack_into(">I", label, 92, 2048)
        struct.pack_into(">H", label, 112, 80)
        label[188:190] = b"ab"
        struct.pack_into(">H", label, CHECKSUM_OFFSET, checksum_v3(bytes(label)))
        report = parse_label(bytes(label))
        self.assertTrue(report["checksum_valid"])
        updated = update_template(bytes(label), front_porch=37, partition_blocks=1234)
        self.assertEqual(struct.unpack_from(">H", updated, 112)[0], 37)
        self.assertEqual(struct.unpack_from(">I", updated, 194)[0], 1234)
        self.assertEqual(struct.unpack_from(">H", updated, CHECKSUM_OFFSET)[0], checksum_v3(updated))

    def test_second_ufs_partition_is_described_relative_to_front_porch(self):
        label = bytearray(7680)
        label[:4] = b"dlV3"
        label[188:190] = b"ab"
        struct.pack_into(">I", label, 92, 2048)
        label[227:235] = b"4.3BSD\0\0"
        updated = update_template(bytes(label), front_porch=100, partition_blocks=200, partition_b=(300, 400))
        self.assertEqual(struct.unpack_from(">II", updated, 236), (300, 400))

    def test_ufs_disk_master_preserves_label_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ufs = root / "payload"
            label = root / "label"
            output = root / "disk.raw"
            boot_source = root / "boot-source"
            ufs.write_bytes(b"\0" * 8192 + b"\0\1\x19\x54" + b"payload")
            template = bytearray(7680)
            template[:4] = b"dlV3"
            struct.pack_into(">I", template, 92, 2048)
            label.write_bytes(template)
            boot_source.write_bytes(b"BOOT" + b"\0" * (8192 - 4) + label.read_bytes() + b"\0" * (80 * 2048 - 8192 - len(label.read_bytes())))
            report = master_ufs_disk(ufs=ufs, label_template=label, boot_source=boot_source,
                                     output=output, size_bytes=4 * 1024 * 1024)
            self.assertEqual(report["ufs_offset"], 80 * 2048)
            self.assertTrue(report["bootable_candidate"])


class BuildSpecTests(unittest.TestCase):
    def test_architecture_slice_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            path.write_text(json.dumps({
                "snapshot": "source-001", "project": "Hello", "target": "all", "profile": "quadfat",
                "architectures": ["m68k", "i386", "hppa", "sparc"],
                "toolchain_sha256": "1" * 64, "output": "products/Hello.app",
            }))
            spec = BuildSpec.load(path)
            self.assertEqual(len(spec.slices()), 4)

    def test_shell_like_project_is_rejected(self):
        spec = BuildSpec("snap", "hello;rm", "all", "quadfat", ("i386",), "1" * 64, "out/app")
        with self.assertRaises(ReopenstepError):
            spec.validate()


if __name__ == "__main__":
    unittest.main()
