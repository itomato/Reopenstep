# Reopenstep

Reopenstep is a reproducible media and build-farm project for i386 OPENSTEP
4.2. Its target progression is:

1. Rebuild the User + Developer media as one El Torito installer.
2. Put required drivers on both the startup filesystem and installed system.
3. Slipstream Patch 4/Y2K and expose vetted third-party package profiles.
4. Boot an i386 developer image that produces m68k, i386, hppa, and sparc fat
   binaries.
5. Distribute architecture-slice builds through an OPENSTEP-native Distributed
   Objects farm.

The cross-platform graphical wrapper lives in `apps/ReopenStepWorkbench`. It
builds with GNUstep on supported Unix-like hosts and directly against Cocoa on
macOS, while delegating media work to the same `reopenstep` CLI used by
automated builds.

See `docs/implementation-status.md` for the milestone ledger, the current BootE
handoff boundary, and the Installation Composer contract.
See [`docs/architecture.md`](docs/architecture.md) for the build/mastering,
BootE handoff, runtime, and quad-fat farm architecture.
See [`docs/project-vision.md`](docs/project-vision.md) for the public six-page
vision, technical constraints, installation strategy, and maintenance roadmap.

## Installation Composer

Create a classic OPENSTEP Installer package from a staged filesystem tree:

```sh
./reopenstep package plan \
  --root out/composer/payload --name ReopenStepExtras \
  --title "ReopenStep Extras" --version 1.0 \
  --description "Custom OPENSTEP software and drivers" \
  --default-location / \
  --output out/composer/ReopenStepExtras.recipe.json

./reopenstep package build \
  --recipe out/composer/ReopenStepExtras.recipe.json \
  --output out/composer/ReopenStepExtras.pkg
```

The recipe fingerprints the payload and the builder emits the classic
`.tar.Z`, `.bom`, `.info`, and `.sizes` package components. See
`docs/installation-composer.md` for BOM format inspection, safety rules, and
the OPENSTEP acceptance-test boundary.

## Inputs and provenance

Proprietary inputs are never downloaded by the build and do not belong in Git.
Place them in the ignored `vault/` through the adoption command, which copies
the input and records its actual size and SHA-256 in
`vault/manifest.local.json`:

```sh
./reopenstep media adopt openstep42-user /path/to/user-image.iso
./reopenstep media adopt openstep42-developer /path/to/developer-image.iso
./reopenstep media adopt openstep42-install-floppy /path/to/install.floppyimage
./reopenstep media adopt openstep42-patch4-user /path/to/OS42MachUserPatch4.tar
./reopenstep media adopt openstep42-patch4-developer /path/to/OS42MachDevPatch4.tar
./reopenstep media inventory
```

The two beta driver floppies already in the repository are pinned directly by
`media/manifest.toml`. A missing or mismatched required input stops the build.

The offline UFS editor is pinned and built explicitly (it is never fetched by
an image build):

```sh
tools/nextufs/bootstrap.sh
./reopenstep slipstream drivers \
  --source 4.2_Beta_Drivers_1.floppyimage \
  --startup out/mastered/user-base/boot/F288.img \
  --output out/mastered/user-base/boot/F288-beta-eide.img
```

This replaces the installer EIDE bundle transactionally and verifies the
resulting UFS tree. The command currently targets the beta EIDE 4.03 bundle;
additional driver and Patch 4 inputs remain explicit vault prerequisites.

## Host workflow

Inspect media and enumerate native Installer packages:

```sh
./reopenstep media inspect vault/OpenStep-4.2-User.iso
./reopenstep media packages vault/OpenStep-4.2-Developer.iso
./reopenstep media driver-collisions 4.2_Beta_Drivers_1.floppyimage 4.2_Beta_Drivers_2.floppyimage
```

Validate a profile and emit the contract for the disposable native mastering
VM:

```sh
./reopenstep image build --profile combined --output out/combined.iso \
  --recipe-output out/mastering-recipe.json --dry-run
```

The native stage described in `guest/master/` produces a UFS payload, a 2.88 MB
boot image, and a NeXT label template. Wrap those outputs as a hybrid disc:

```sh
./reopenstep image wrap \
  --ufs out/mastered/combined/OPENSTEP42CD.UFS \
  --boot-image out/mastered/combined/OPENSTEP_BOOT_288.img \
  --label-template out/mastered/combined/NEXT_LABEL.bin \
  --label-offset 112 --label-format u16be \
  --output out/reopenstep-4.2-combined.iso
```

For the combined User + Developer disc, add
`--developer-ufs out/mastered/combined-base/OPENSTEP42DEV.UFS`.

Merely exposing that second UFS does not install Developer software. The
preferred host-only path patches `rc.cdrom` so it mounts optical partition `b`
and performs separate BOM-directed package passes during installation. The
native scripts under `guest/master/` remain available for producing a single
pre-expanded UFS, but they are not required for the combined disc.

The label offset is deliberately explicit: guessing a disklabel field can make
an image appear valid while directing OPENSTEP at the wrong blocks.

Patch a mastered 2.88 MB startup image to select English and bypass only the
two initial boot2 console prompts:

```sh
./reopenstep slipstream replace-file \
  --image out/mastered/user-base/boot/F288-eide-piix.img \
  --path /private/Drivers/i386/System.config/Instance0.table \
  --source boot/minimal-autoboot.table \
  --output out/mastered/user-base/boot/F288-eide-english.img
./reopenstep slipstream boot2-autoinstall \
  --image out/mastered/user-base/boot/F288-eide-english.img \
  --output out/mastered/user-base/boot/F288-eide-autoinstall.img
```

The boot2 patch is signature-checked and changes only the pre-kernel
confirmation branch. Installer disk selection and destructive partitioning
confirmations are intentionally retained.

Inspect or launch the result with the pinned QEMU hardware profile:

```sh
./reopenstep image inspect out/reopenstep-4.2-combined.iso --require-bootable
./reopenstep vm test --iso out/reopenstep-4.2-combined.iso --print-command
```

The current host-mastered combined test image is:

```text
out/reopenstep-4.2-eide-developer-v6.iso
```

Its User UFS `rc.cdrom` mounts the same optical device's partition `b` and
installs `DeveloperTools`, `DeveloperLibs`, `DeveloperDoc`, `GNUSource`, and
`ProfileLibs` through their original BOMs. It also copies the complete i386
driver directory after the base BOM pass. Reproduce the UFS patch with:

```sh
./reopenstep slipstream cdis-developer \
  --image out/mastered/user-base/OPENSTEP42CD-eide-persistent-v4.UFS \
  --output out/mastered/user-base/OPENSTEP42CD-eide-developer-v5.UFS
```

The v6 wrapper corrects NeXT's 24-bit partition fields and 64-byte partition
records, so partition `b` now points at the Developer UFS instead of merely
appearing valid to the former host inspector. Its SHA-256 is
`dd484a5085f6ee31a3cca043adc4b7c37271a20a5fa72b735da34a245e165ed5`.

Launch the prompt-free EIDE installer and create a sparse 2 GB raw target disk
on first use with:

```sh
scripts/run-openstep-autoboot.sh install
```

Override the defaults with `REOPENSTEP_QEMU_ISO`, `REOPENSTEP_QEMU_DISK`, or
`REOPENSTEP_QEMU_DISK_SIZE`. Additional QEMU arguments may be appended to the
command line.

The equivalent clean AM-BX133/PIIX4E test under 86Box is:

```sh
scripts/run-openstep-autoboot-86box.sh install
```

It creates a new dynamic 2 GB-class VHD on first use and generates a
single-disk, single-CD configuration under `out/`, leaving enough room for all
Developer packages. Override its paths with
`REOPENSTEP_86BOX_ISO`, `REOPENSTEP_86BOX_DISK`, or
`REOPENSTEP_86BOX_CONFIG`.

Both wrappers accept the same lifecycle modes: `install` uses the persistent
EIDE installer, `rescue` preloads EIDE and mounts the existing `sd0a`, and
`disk` ejects the ISO and boots the installed hard disk. `install` remains the
default when no mode is supplied.

QEMU also supports the independent AMD PCscsi lane:

```sh
REOPENSTEP_QEMU_STORAGE=amd-scsi scripts/run-openstep-autoboot.sh install
REOPENSTEP_QEMU_STORAGE=amd-scsi scripts/run-openstep-autoboot.sh disk
```

86Box uses its separate BusLogic BT-958D lane:

```sh
REOPENSTEP_86BOX_STORAGE=buslogic scripts/run-openstep-autoboot-86box.sh install
REOPENSTEP_86BOX_STORAGE=buslogic scripts/run-openstep-autoboot-86box.sh disk
```

The native-disk experiment is explicit and independently verifiable:

```sh
./reopenstep image disk \
  --ufs out/mastered/user-base/OPENSTEP42CD.UFS \
  --label-template out/mastered/user-base/NEXT_LABEL.bin \
  --boot-source NATIVE_HDD_BOOT_BLOCKS.bin \
  --size 0x80000000 \
  --output out/openstep-user-ufs.raw
```

`--boot-source` must be a hard-disk boot-block image containing the native
`boot0`/`boot1`/`boot2` chain. An optical User ISO is rejected deliberately:
its porch contains CD boot content and cannot make a raw HDD bootable. Produce
the boot-block source with BuildDisk.app or OpenStep's `disk` utility first.

## BootE alternative boot lane

BootE builds a pinned Chameleon/boot132 loader without the historical 32-bit
curses configuration utility. It discovers NeXT `dlV3`/UFS disks and now has a
selectable OPENSTEP handoff alongside the preserved Darwin/Marklar path:

```sh
make boote-test
make boote-build
make boote-iso
tools/boote/run-boote-smoke.sh out/openstep-user-ufs.raw
```

The handoff no longer triple-faults: OPENSTEP initializes paging with
`CR3=0x20000` and consumes the installed `System.config`. Standalone boot
drivers are the remaining boundary because their `*_reloc` images must be
linked by `sarld` before the kernel can register EISA, PCI, and storage classes.
See `docs/chameleon-ufs-boot.md` and `docs/boot-reverse-engineering.md`.

## Quad-fat and farm workflow

## Minimal boot system

The Socket 370 target is defined by `profiles/minimal.toml` and
`media/driver-policy.toml`. It preserves the stock PS/2, EISA, PCI, and Intel
chipset boot path and adds EIDE before the installer starts. VGA, NE2000,
3Com, Matrox, and Voodoo2 remain installed-system drivers. Generate the
reproducible mastering contract
with:

Storage is tested as separate controller-specific lanes; see
`docs/storage-matrix.md` and `media/storage-policy.toml`. PIIX EIDE/ATAPI is
the common default, AMD PCscsi is the QEMU SCSI target, and BusLogic BT-958D is
the 86Box SCSI target. Adaptec 2940 remains a physical/future-emulation target.

```sh
./reopenstep image build --profile minimal \
  --output out/minimal.iso \
  --recipe-output out/minimal-recipe.json --dry-run
```

The native mastering stage must copy every `boot` driver into the startup UFS
and every `installed` driver into the target system, then place the default
packages in the Installer package set. The policy intentionally keeps the
accelerator drivers out of the earliest boot path so a bad Matrox/Voodoo
extension cannot prevent installation.

The MS4 reference project is under `guest/reference/`. Build it inside the
builder image and validate the result on either side of the VM boundary:

```sh
./reopenstep quadfat validate /path/to/hello
```

`guest/farm/` contains the native Foundation/Distributed Objects controller,
worker, and `rsfarm` CLI. The host validates and expands a build request into
four architecture-slice jobs with:

```sh
./reopenstep farm plan examples/farm-build.json
```

The farm is for an isolated trusted build LAN. Workers use a dedicated account,
NetInfo membership, and an NFS source/artifact root; the protocol is not safe
for exposure to an untrusted or routed network.

## Verification

Run all host-side checks with:

```sh
make check
```

The checked-in `test.iso` is a structural El Torito fixture only. It contains a
real 2.88 MB OPENSTEP boot image but no installer payload or slipstreamed
packages.
