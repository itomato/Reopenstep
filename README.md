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

The label offset is deliberately explicit: guessing a disklabel field can make
an image appear valid while directing OPENSTEP at the wrong blocks.

Inspect or launch the result with the pinned QEMU hardware profile:

```sh
./reopenstep image inspect out/reopenstep-4.2-combined.iso --require-bootable
./reopenstep vm test --iso out/reopenstep-4.2-combined.iso --print-command
```

Launch the prompt-free EIDE installer and create a sparse 2 GB raw target disk
on first use with:

```sh
scripts/run-openstep-autoboot.sh
```

Override the defaults with `REOPENSTEP_QEMU_ISO`, `REOPENSTEP_QEMU_DISK`, or
`REOPENSTEP_QEMU_DISK_SIZE`. Additional QEMU arguments may be appended to the
command line.

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

## Quad-fat and farm workflow

## Minimal boot system

The Socket 370 target is defined by `profiles/minimal.toml` and
`media/driver-policy.toml`. It preserves the stock PS/2, EISA, PCI, and Intel
chipset boot path and adds EIDE before the installer starts. VGA, NE2000,
3Com, Matrox, and Voodoo2 remain installed-system drivers. Generate the
reproducible mastering contract
with:

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
