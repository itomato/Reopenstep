from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .errors import ReopenstepError
from .iso import inspect_el_torito, require_bootable
from .hybrid import extract_raw_cd, iso_path_extent, iso_root_extent, label_candidates, wrap_ufs
from .fat import inspect_fat, require_quad_fat
from .buildspec import BuildSpec
from .boot2 import patch_autoinstall
from .cdis import DEFAULT_DEVELOPER_PACKAGES, patch_cdis_image
from .composer import (
    build_package, inspect_bom, inspect_package, package_recipe,
    write_openstep_bom, write_package_recipe,
)
from .manifest import MediaManifest, default_vault
from .media import inspect_media
from .packages import collision_report, package_inventory
from .patch4 import extract_patch4, inspect_patch4, overlay_patch4, set_vesa_mode
from .nextlabel import inspect_labels
from .profile import BuildProfile
from .qemu import qemu_command, qemu_version
from .box86 import command as box_command
from .disk import master_ufs_disk
from .recipe import mastering_recipe, write_recipe
from .rhapsody import ROOT_KINDS, inspect_native_boot, inspect_xnu_root, mastering_gap, validate_root_kind
from .util import atomic_json, sha256_file
from .ufs import extract_file, extract_tree, insert_tree, replace_file, replace_tree, tree_inventory


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def profile_path(name: str) -> Path:
    supplied = Path(name)
    return supplied if supplied.suffix == ".toml" or supplied.parent != Path(".") else Path("profiles") / f"{name}.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reopenstep", description="Reproducible OPENSTEP media tooling")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="group", required=True)

    media = sub.add_parser("media")
    media_sub = media.add_subparsers(dest="action", required=True)
    inventory = media_sub.add_parser("inventory")
    inventory.add_argument("--manifest", type=Path, default=Path("media/manifest.toml"))
    inventory.add_argument("--vault", type=Path, default=default_vault())
    adopt = media_sub.add_parser("adopt")
    adopt.add_argument("id")
    adopt.add_argument("path", type=Path)
    adopt.add_argument("--manifest", type=Path, default=Path("media/manifest.toml"))
    adopt.add_argument("--vault", type=Path, default=default_vault())
    inspect = media_sub.add_parser("inspect")
    inspect.add_argument("path", type=Path, nargs="+")
    packages = media_sub.add_parser("packages")
    packages.add_argument("path", type=Path)
    collisions = media_sub.add_parser("driver-collisions")
    collisions.add_argument("path", type=Path, nargs="+")

    slipstream = sub.add_parser("slipstream")
    slipstream_sub = slipstream.add_subparsers(dest="action", required=True)
    drivers = slipstream_sub.add_parser("drivers")
    drivers.add_argument("--source", required=True, type=Path)
    drivers.add_argument("--source-root", default="/private/Drivers/i386/EIDE.config")
    drivers.add_argument("--startup", required=True, type=Path)
    drivers.add_argument("--startup-root", default="/private/Drivers/i386/EIDE.config")
    drivers.add_argument("--output", required=True, type=Path)
    ufs_list = slipstream_sub.add_parser("list")
    ufs_list.add_argument("image", type=Path)
    ufs_list.add_argument("path")
    ufs_extract = slipstream_sub.add_parser("extract")
    ufs_extract.add_argument("image", type=Path)
    ufs_extract.add_argument("path")
    ufs_extract.add_argument("output", type=Path)
    ufs_extract_tree = slipstream_sub.add_parser("extract-tree")
    ufs_extract_tree.add_argument("image", type=Path)
    ufs_extract_tree.add_argument("path")
    ufs_extract_tree.add_argument("output", type=Path)
    ufs_replace = slipstream_sub.add_parser("replace-file")
    ufs_replace.add_argument("--image", required=True, type=Path)
    ufs_replace.add_argument("--path", required=True)
    ufs_replace.add_argument("--source", required=True, type=Path)
    ufs_replace.add_argument("--output", required=True, type=Path)
    ufs_replace.add_argument("--mode", type=lambda value: int(value, 8), default=0o444)
    ufs_insert = slipstream_sub.add_parser("insert-tree")
    ufs_insert.add_argument("--source", required=True, type=Path)
    ufs_insert.add_argument("--source-root", required=True)
    ufs_insert.add_argument("--destination", required=True, type=Path)
    ufs_insert.add_argument("--destination-root", required=True)
    ufs_insert.add_argument("--output", required=True, type=Path)
    boot2_autoinstall = slipstream_sub.add_parser("boot2-autoinstall")
    boot2_autoinstall.add_argument("--image", required=True, type=Path)
    boot2_autoinstall.add_argument("--output", required=True, type=Path)
    cdis_overlay = slipstream_sub.add_parser("cdis-developer")
    cdis_overlay.add_argument("--image", required=True, type=Path)
    cdis_overlay.add_argument("--output", required=True, type=Path)
    cdis_overlay.add_argument("--package", action="append", dest="packages")
    cdis_overlay.add_argument("--skip-installed-drivers", action="store_true")

    image = sub.add_parser("image")
    image_sub = image.add_subparsers(dest="action", required=True)
    image_inspect = image_sub.add_parser("inspect")
    image_inspect.add_argument("path", type=Path)
    image_inspect.add_argument("--require-bootable", action="store_true")
    image_build = image_sub.add_parser("build")
    image_build.add_argument("--profile", required=True)
    image_build.add_argument("--manifest", type=Path, default=Path("media/manifest.toml"))
    image_build.add_argument("--vault", type=Path, default=default_vault())
    image_build.add_argument("--output", type=Path, required=True)
    image_build.add_argument("--dry-run", action="store_true")
    image_build.add_argument("--recipe-output", type=Path)
    image_recipe = image_sub.add_parser("recipe")
    image_recipe.add_argument("--profile", required=True)
    image_recipe.add_argument("--manifest", type=Path, default=Path("media/manifest.toml"))
    image_recipe.add_argument("--vault", type=Path, default=default_vault())
    image_recipe.add_argument("--output", type=Path, required=True)
    image_wrap = image_sub.add_parser("wrap")
    image_wrap.add_argument("--ufs", required=True, type=Path)
    image_wrap.add_argument("--boot-image", required=True, type=Path)
    secondary = image_wrap.add_mutually_exclusive_group()
    secondary.add_argument("--developer-ufs", type=Path,
                           help="Optional Developer CD UFS exposed as partition b")
    secondary.add_argument("--secondary-ufs", dest="developer_ufs", type=Path,
                           help="Optional Developer, Rhapsody, or Darwin UFS exposed as partition b")
    image_wrap.add_argument("--boot-mode", choices=("floppy", "no-emulation"), default="floppy",
                            help="El Torito mode; BootE cdboot requires no-emulation")
    image_wrap.add_argument("--root-kind", choices=ROOT_KINDS, default="openstep",
                            help="Expected kernel handoff/filesystem family for the primary UFS")
    image_wrap.add_argument("--label-template", required=True, type=Path)
    image_wrap.add_argument("--label-offset", required=True, type=lambda value: int(value, 0))
    image_wrap.add_argument("--label-format", choices=("u16be", "u16le", "u32be", "u32le"), default="u16be")
    image_wrap.add_argument("--volume", default="REOPENSTEP42")
    image_wrap.add_argument("--output", required=True, type=Path)
    image_extract = image_sub.add_parser("extract-ufs")
    image_extract.add_argument("--source", required=True, type=Path)
    image_extract.add_argument("--front-porch-blocks", type=int, default=80)
    image_extract.add_argument("--ufs-output", required=True, type=Path)
    image_extract.add_argument("--label-output", required=True, type=Path)
    image_candidates = image_sub.add_parser("label-candidates")
    image_candidates.add_argument("--label", required=True, type=Path)
    image_candidates.add_argument("--value", required=True, type=lambda value: int(value, 0))
    image_disk = image_sub.add_parser("disk")
    image_disk.add_argument("--ufs", required=True, type=Path)
    image_disk.add_argument("--label-template", required=True, type=Path)
    image_disk.add_argument("--output", required=True, type=Path)
    image_disk.add_argument("--size", required=True, type=lambda value: int(value, 0))
    image_disk.add_argument("--front-porch-blocks", type=int, default=80)
    image_disk.add_argument("--boot-source", required=True, type=Path,
                            help="raw NeXT media whose front porch contains boot blocks")

    package = sub.add_parser("package")
    package_sub = package.add_subparsers(dest="action", required=True)
    package_plan = package_sub.add_parser("plan")
    package_plan.add_argument("--root", required=True, type=Path)
    package_plan.add_argument("--name", required=True)
    package_plan.add_argument("--title", required=True)
    package_plan.add_argument("--version", required=True)
    package_plan.add_argument("--description", required=True)
    package_plan.add_argument("--default-location", default="/")
    package_plan.add_argument("--disk-name")
    package_plan.add_argument("--relocatable", action="store_true")
    package_plan.add_argument("--application", action="store_true")
    package_plan.add_argument("--no-authorization", action="store_true")
    package_plan.add_argument("--owner", dest="owner_uid", type=int, default=0)
    package_plan.add_argument("--group", dest="owner_gid", type=int, default=0)
    package_plan.add_argument("--output", required=True, type=Path)
    package_build = package_sub.add_parser("build")
    package_build.add_argument("--recipe", required=True, type=Path)
    package_build.add_argument("--output", required=True, type=Path)
    package_bom = package_sub.add_parser("bom")
    package_bom.add_argument("--root", required=True, type=Path)
    package_bom.add_argument("--output", required=True, type=Path)
    package_bom.add_argument("--owner", dest="owner_uid", type=int, default=0)
    package_bom.add_argument("--group", dest="owner_gid", type=int, default=0)
    package_bom_inspect = package_sub.add_parser("bom-inspect")
    package_bom_inspect.add_argument("path", type=Path)
    package_inspect = package_sub.add_parser("inspect")
    package_inspect.add_argument("path", type=Path)

    patch4 = sub.add_parser("patch4", help="Inspect and apply NeXT's OPENSTEP 4.2 Patch 4 archives")
    patch4_sub = patch4.add_subparsers(dest="action", required=True)
    patch4_inspect = patch4_sub.add_parser("inspect")
    patch4_inspect.add_argument("package", type=Path)
    patch4_extract = patch4_sub.add_parser("extract")
    patch4_extract.add_argument("package", type=Path)
    patch4_extract.add_argument("--output", required=True, type=Path)
    patch4_overlay = patch4_sub.add_parser("overlay")
    patch4_overlay.add_argument("package", type=Path)
    patch4_overlay.add_argument("--image", required=True, type=Path)
    patch4_overlay.add_argument("--output", required=True, type=Path)
    patch4_vesa = patch4_sub.add_parser("set-vesa-mode")
    patch4_vesa.add_argument("--image", required=True, type=Path)
    patch4_vesa.add_argument("--output", required=True, type=Path)
    patch4_vesa.add_argument("--mode", required=True, type=lambda value: int(value, 0),
                             help="VBE BIOS mode number, e.g. 0x118 for QEMU 1024x768x32")

    vm = sub.add_parser("vm")
    vm_sub = vm.add_subparsers(dest="action", required=True)
    vm_test = vm_sub.add_parser("test")
    vm_test.add_argument("--iso", type=Path, required=True)
    vm_test.add_argument("--disk", type=Path)
    vm_test.add_argument("--print-command", action="store_true")
    vm_box = vm_sub.add_parser("86box")
    vm_box.add_argument("--config", required=True, type=Path)
    vm_box.add_argument("--binary")
    vm_box.add_argument("--print-command", action="store_true")

    quadfat = sub.add_parser("quadfat")
    quadfat_sub = quadfat.add_subparsers(dest="action", required=True)
    quadfat_validate = quadfat_sub.add_parser("validate")
    quadfat_validate.add_argument("path", type=Path)

    farm = sub.add_parser("farm")
    farm_sub = farm.add_subparsers(dest="action", required=True)
    farm_plan = farm_sub.add_parser("plan")
    farm_plan.add_argument("spec", type=Path)

    rhapsody = sub.add_parser("rhapsody", help="Inspect Rhapsody/XNU UFS mastering readiness")
    rhapsody_sub = rhapsody.add_subparsers(dest="action", required=True)
    rhapsody_inspect = rhapsody_sub.add_parser("inspect-root")
    rhapsody_inspect.add_argument("image", type=Path)
    rhapsody_inspect.add_argument("--root-kind", choices=ROOT_KINDS, default="rhapsodios")
    rhapsody_native = rhapsody_sub.add_parser("inspect-native-boot")
    rhapsody_native.add_argument("image", type=Path)
    rhapsody_gap = rhapsody_sub.add_parser("gap")
    rhapsody_gap.add_argument("--project", type=Path, default=Path("."))
    rhapsody_gap.add_argument("--xnu-ufs", type=Path)
    rhapsody_gap.add_argument("--root-kind", choices=ROOT_KINDS, default="rhapsodios")

    return parser


def verified_profile(args: argparse.Namespace) -> tuple[BuildProfile, MediaManifest, list[dict]]:
    profile = BuildProfile.load(profile_path(args.profile))
    profile.validate()
    manifest = MediaManifest.load(args.manifest)
    for media_id in profile.media:
        manifest.by_id(media_id)
    report = manifest.verify(args.vault)
    relevant = [item for item in report if item["id"] in profile.media]
    return profile, manifest, relevant


def dispatch(args: argparse.Namespace) -> int:
    if args.group == "media" and args.action == "inventory":
        manifest = MediaManifest.load(args.manifest)
        report = manifest.verify(args.vault)
        emit(report)
        return 1 if any(item["state"] not in {"ok", "optional-missing"} for item in report) else 0
    if args.group == "media" and args.action == "adopt":
        manifest = MediaManifest.load(args.manifest)
        entry = manifest.by_id(args.id)
        if entry.location != "vault":
            raise ReopenstepError(f"{entry.id} is a repository-managed input and cannot be adopted")
        if not args.path.is_file():
            raise ReopenstepError(f"input not found: {args.path}")
        args.vault.mkdir(parents=True, exist_ok=True)
        destination = args.vault / entry.filename
        if destination.exists() and sha256_file(destination) != sha256_file(args.path):
            raise ReopenstepError(f"vault destination already contains different data: {destination}")
        if not destination.exists():
            shutil.copy2(args.path, destination)
        local_path = args.vault / "manifest.local.json"
        overrides = json.loads(local_path.read_text(encoding="utf-8")) if local_path.is_file() else {}
        overrides[entry.id] = {"size": destination.stat().st_size, "sha256": sha256_file(destination)}
        atomic_json(local_path, overrides)
        emit({"id": entry.id, "path": str(destination), **overrides[entry.id]})
        return 0
    if args.group == "media" and args.action == "inspect":
        emit([inspect_media(path) for path in args.path])
        return 0
    if args.group == "media" and args.action == "packages":
        emit([record.__dict__ for record in package_inventory(args.path)])
        return 0
    if args.group == "media" and args.action == "driver-collisions":
        report = collision_report(args.path)
        emit(report)
        return 1 if report else 0
    if args.group == "slipstream" and args.action == "list":
        emit([node.__dict__ for node in tree_inventory(args.image, args.path)])
        return 0
    if args.group == "slipstream" and args.action == "extract":
        emit(extract_file(args.image, args.path, args.output))
        return 0
    if args.group == "slipstream" and args.action == "extract-tree":
        emit(extract_tree(args.image, args.path, args.output))
        return 0
    if args.group == "slipstream" and args.action == "replace-file":
        emit(replace_file(args.image, args.path, args.source, args.output, args.mode))
        return 0
    if args.group == "slipstream" and args.action == "insert-tree":
        emit(insert_tree(args.source, args.source_root, args.destination,
                         args.destination_root, args.output))
        return 0
    if args.group == "slipstream" and args.action == "boot2-autoinstall":
        emit(patch_autoinstall(args.image, args.output))
        return 0
    if args.group == "slipstream" and args.action == "cdis-developer":
        packages = tuple(args.packages) if args.packages else DEFAULT_DEVELOPER_PACKAGES
        emit(patch_cdis_image(
            args.image, args.output, packages,
            persist_drivers=not args.skip_installed_drivers,
        ))
        return 0
    if args.group == "slipstream" and args.action == "drivers":
        emit(replace_tree(args.source, args.source_root, args.startup, args.startup_root, args.output))
        return 0
    if args.group == "image" and args.action == "inspect":
        report = inspect_el_torito(args.path)
        report["ufs_payload"] = None
        for name in ("OPENSTEP42CD.UFS", "ZZZOPENSTEP42CD.UFS"):
            try:
                extent, size = iso_root_extent(args.path, name)
                report["ufs_payload"] = {"name": name, "lba": extent, "size": size}
                break
            except ReopenstepError:
                pass
        try:
            report["next_label"] = inspect_labels(args.path)
        except ReopenstepError:
            report["next_label"] = None
        try:
            extent, size = iso_path_extent(args.path, "DEVELOPER/OPENSTEP42DEV.UFS")
            report["developer_ufs_payload"] = {"lba": extent, "size": size}
        except ReopenstepError:
            report["developer_ufs_payload"] = None
        if args.require_bootable:
            require_bootable(report)
        emit(report)
        return 0
    if args.group == "image" and args.action == "build":
        profile, manifest, report = verified_profile(args)
        failures = [item for item in report if item["state"] != "ok"]
        build_plan = {
            "profile": profile.name, "output": str(args.output), "inputs": report,
            "default_packages": profile.default_packages, "optional_packages": profile.optional_packages,
            "native_overlay_packages": profile.native_packages,
            "boot_drivers": profile.boot_drivers, "install_drivers": profile.install_drivers,
            "architectures": profile.architectures,
        }
        if failures:
            emit(build_plan)
            raise ReopenstepError("required vault inputs are not ready; run `./reopenstep media inventory`")
        if args.recipe_output:
            write_recipe(args.recipe_output, mastering_recipe(profile, manifest, args.vault))
            build_plan["recipe"] = str(args.recipe_output)
        if not args.dry_run:
            raise ReopenstepError("native mastering must produce the recipe outputs before `image wrap`; pass --recipe-output and --dry-run")
        emit(build_plan)
        return 0
    if args.group == "image" and args.action == "recipe":
        profile, manifest, report = verified_profile(args)
        failures = [item for item in report if item["state"] != "ok"]
        if failures:
            emit(report)
            raise ReopenstepError("cannot create recipe until required vault inputs verify")
        recipe = mastering_recipe(profile, manifest, args.vault)
        write_recipe(args.output, recipe)
        emit({"output": str(args.output), "recipe": recipe})
        return 0
    if args.group == "image" and args.action == "wrap":
        validate_root_kind(args.root_kind)
        emit(wrap_ufs(
            ufs=args.ufs, boot_image=args.boot_image, label_template=args.label_template,
            label_offset=args.label_offset, label_format=args.label_format,
            output=args.output, volume=args.volume, developer_ufs=args.developer_ufs,
            boot_mode=args.boot_mode, root_kind=args.root_kind,
        ))
        return 0
    if args.group == "image" and args.action == "extract-ufs":
        emit(extract_raw_cd(args.source, args.ufs_output, args.label_output, args.front_porch_blocks))
        return 0
    if args.group == "image" and args.action == "label-candidates":
        emit(label_candidates(args.label.read_bytes(), args.value))
        return 0
    if args.group == "image" and args.action == "disk":
        emit(master_ufs_disk(
            ufs=args.ufs, label_template=args.label_template, boot_source=args.boot_source, output=args.output,
            size_bytes=args.size, front_porch_blocks=args.front_porch_blocks,
        ))
        return 0
    if args.group == "package" and args.action == "plan":
        recipe = package_recipe(
            root=args.root, name=args.name, title=args.title, version=args.version,
            description=args.description, default_location=args.default_location,
            disk_name=args.disk_name, relocatable=args.relocatable, application=args.application,
            needs_authorization=not args.no_authorization, owner=args.owner_uid, group=args.owner_gid,
        )
        write_package_recipe(args.output, recipe)
        emit({"output": str(args.output), "recipe": recipe})
        return 0
    if args.group == "package" and args.action == "build":
        emit(build_package(args.recipe, args.output))
        return 0
    if args.group == "package" and args.action == "bom":
        emit(write_openstep_bom(args.root, args.output, owner=args.owner_uid, group=args.owner_gid))
        return 0
    if args.group == "package" and args.action == "bom-inspect":
        emit(inspect_bom(args.path))
        return 0
    if args.group == "package" and args.action == "inspect":
        emit(inspect_package(args.path))
        return 0
    if args.group == "patch4" and args.action == "inspect":
        emit(inspect_patch4(args.package))
        return 0
    if args.group == "patch4" and args.action == "extract":
        emit(extract_patch4(args.package, args.output))
        return 0
    if args.group == "patch4" and args.action == "overlay":
        emit(overlay_patch4(args.package, args.image, args.output))
        return 0
    if args.group == "patch4" and args.action == "set-vesa-mode":
        emit(set_vesa_mode(args.image, args.output, args.mode))
        return 0
    if args.group == "vm" and args.action == "test":
        require_bootable(inspect_el_torito(args.iso))
        command = qemu_command(args.iso, args.disk)
        emit({"qemu_version": qemu_version(), "command": command})
        if not args.print_command:
            from .util import run
            run(command)
        return 0
    if args.group == "vm" and args.action == "86box":
        command = box_command(args.config, binary=args.binary)
        emit({"command": command, "config": str(args.config)})
        if not args.print_command:
            from .util import run
            run(command)
        return 0
    if args.group == "quadfat" and args.action == "validate":
        report = inspect_fat(args.path)
        require_quad_fat(report)
        emit(report)
        return 0
    if args.group == "farm" and args.action == "plan":
        spec = BuildSpec.load(args.spec)
        emit({"spec": spec.__dict__, "jobs": spec.slices()})
        return 0
    if args.group == "rhapsody" and args.action == "inspect-root":
        emit(inspect_xnu_root(args.image, args.root_kind))
        return 0
    if args.group == "rhapsody" and args.action == "inspect-native-boot":
        emit(inspect_native_boot(args.image))
        return 0
    if args.group == "rhapsody" and args.action == "gap":
        emit(mastering_gap(args.project.resolve(), args.xnu_ufs, args.root_kind))
        return 0
    raise ReopenstepError("unsupported command")


def main(argv: list[str] | None = None) -> int:
    try:
        return dispatch(build_parser().parse_args(argv))
    except (ReopenstepError, FileNotFoundError) as exc:
        print(f"reopenstep: {exc}", file=sys.stderr)
        return 2
