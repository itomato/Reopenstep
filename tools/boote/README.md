# BootE

BootE is the minimal i386 BIOS/El Torito loader lane for OPENSTEP, Rhapsody,
and Darwin/Marklar experiments. It uses Chameleon's public Apple boot-132
lineage for the PC-facing stages and ReopenStep's NeXT `dlV3`/UFS scanner.

Unlike the historical Chameleon build, BootE has no interactive Kconfig step.
`generate_config.py` turns a reviewed TOML profile directly into `.config`,
`auto.conf`, `autoconf.h`, and `autoconf.inc`. The minimal profile disables
themes, modules, optional utilities, and EFI-oriented kernel patching.

Prepare and inspect the patched source without compiling:

```sh
tools/boote/test-config.sh
tools/boote/build-boote.sh prepare
```

Build `out/boote/boote-boot` and `out/boote/boote-cdboot`:

```sh
tools/boote/build-boote.sh build
```

BootE identifies the bundled loader as the itomato Chameleon fork
(`Darwin/x86 boot v5.0.133 - Chameleon itomato v2.3-itomato`).

Master a small El Torito test ISO from that loader:

```sh
tools/boote/make-boote-iso.sh
```

`out/boote/boote-smoke.iso` is intended to be booted with an installed NeXT
UFS disk attached. It contains no Apple system files or kernel of its own.

Build a self-contained optical image whose NeXT-labelled UFS payload carries
the Patch 4 OPENSTEP kernel, libraries, standalone drivers, and installer:

```sh
make boote-openstep-disc
```

For BIOSes that require floppy-emulation booting, build the same installer and
driver payload with a padded 2.88 MB El Torito entry:

```sh
make boote-openstep-floppy
```

This writes `out/boote/boote-openstep-2880.iso`. The 2.88 MB limit applies to
the boot image only; the installer and drivers remain in the ISO's UFS extent.
The generated `boote-cdboot-2880.img` is exactly 2,949,120 bytes.

Select a hardware lane when building the same UFS/installer payload:

```sh
BOOTE_CONFIG=tools/boote/config/disc.toml make boote-openstep-disc             # dual-channel EIDE/ATAPI
BOOTE_CONFIG=tools/boote/config/disc-pci-eide.toml make boote-openstep-disc   # PCI PIIX EIDE/ATAPI
BOOTE_CONFIG=tools/boote/config/disc-buslogic-scsi.toml make boote-openstep-disc # BusLogic PCI SCSI
BOOTE_CONFIG=tools/boote/config/disc-adaptec-scsi.toml make boote-openstep-disc  # Adaptec 2940 SCSI
```

The experimental XNU lane is prepared with:

```sh
BOOTE_CONFIG=tools/boote/config/xnu-ufs-vesa.toml tools/boote/build-boote.sh build
```

It disables the OPENSTEP `KERNBOOTSTRUCT` adapter, preserves the normal
Chameleon/XNU boot-argument path, and requests a VBE framebuffer for a NeXT
UFS root. Pair it with `--secondary-ufs` when mastering an installer extent;
the secondary extent is recorded as NeXT partition `b` for the running kernel.
This is an integration lane, not yet a claim that arbitrary XNU builds can
mount every secondary ISO extent.

Adopt or build an x86 Mach-O XNU kernel artifact:

```sh
XNU_KERNEL=/path/to/mach_kernel make xnu-kernel
./reopenstep xnu inspect-kernel out/xnu/mach_kernel --require-boote
```

For source builds, the wrapper deliberately requires an explicit build command
because XNU build systems differ substantially by era:

```sh
XNU_SOURCE=/path/to/xnu \
XNU_BUILD_COMMAND='make SDKROOT=/path/to/sdk ARCH_CONFIGS=I386 KERNEL_CONFIGS=RELEASE' \
XNU_BUILT_KERNEL=/path/to/xnu/BUILD/obj/RELEASE_I386/mach_kernel \
make xnu-kernel
```

Master a BootE test disc that carries the kernel on an HFS/ISO hybrid root:

```sh
make boote-xnu-kernel-iso
```

This writes `out/boote/boote-xnu-kernel.iso`. The HFS hybrid is intentional:
this Chameleon lineage's CD boot path uses filesystem callbacks that are
proven for HFS/HFS+ and NeXT UFS, not a plain ISO9660 root. The generated
disc is a kernel-entry test, not a complete OS install medium unless the staged
root also contains the matching extensions, boot plist, device tree assumptions,
and mountable root filesystem expected by that XNU vintage.

Master it from the actual generated installer artifact once an XNU/Rhapsody
UFS root is available:

```sh
XNU_UFS=path/to/xnu-root.ufs \
tools/boote/make-boote-xnu-ufs-vesa.sh out/boote/boote-xnu-ufs-vesa.iso
```

The wrapper defaults the secondary payload to
`out/boote/openstep-user-patch4-beta-eide-cd.ufs`, which is the generated
Patch 4 User installer with the EIDE driver overlay. Use
`INSTALLER_UFS=...` to substitute another mastered User/Developer payload;
use `BOOTE_BOOT_MODE=floppy` for the 2.88 MB El Torito variant. The primary
root is tagged as `rhapsodios` by default; set
`BOOTE_ROOT_KIND=rhapsody-dr2` or `BOOTE_ROOT_KIND=darwin` when testing those
filesystem families.

Measure the remaining Rhapsody/XNU filesystem-mastering gap with:

```sh
make rhapsody-gap
XNU_UFS=path/to/xnu-root.ufs ./reopenstep rhapsody gap --root-kind rhapsody-dr2
./reopenstep rhapsody inspect-root path/to/xnu-root.ufs --root-kind rhapsodios
./reopenstep rhapsody inspect-native-boot path/to/rhapsody_dr2_x86_InstallationFloppy.img
./reopenstep rhapsody inspect-native-boot path/to/rhapsody_dr2_x86.iso
./reopenstep floppy combine-2880 --install path/to/install.img --drivers path/to/driver.img --output out/install-driver-2880.img
```

The gap report distinguishes four states: existing OPENSTEP artifacts, BootE
build products, the pinned offline `nextufs` mutator, and the required
Rhapsody/XNU root. Current `nextufs` can mutate a seed UFS but cannot create,
resize, or fsck one on this host, so full source-to-UFS mastering still needs
either an imported seed/root image or a host-side UFS creator.

For `BOOTE_ROOT_KIND=rhapsody-dr2`, the report uses the native `rdrufs` reader
instead of `nextufs` to test for `/mach_kernel`. RhapsodyAnswers beta2 documents
that RDR/Intel uses a native-endian BSD 4.4-derived filesystem and cannot
exchange UFS media with OPENSTEP/NeXTStep Mach. `BOOTE_ROOT_KIND=darwin` first
tries the existing UFS probe and then falls back to `rdrufs`; pass
`--root-offset` when testing embedded Darwin partitions such as the
`Apple_Rhapsody_UFS` root in Darwin 0.3 or the nested Apple Boot/UFS helper in
Darwin 6.0.2 `cdboot.dmg`.

The native-boot inspector records the Rhapsody DR2 boot1 contract recovered
from the Titan1U boot floppy: boot1 reads label sector 15, reads the media
sector size at label offset `0x5c`, reads the boot2 block at label offset
`0x7c`, converts that media block to a 512-byte BIOS LBA, loads `0x58` sectors
to physical `0x3000`, and jumps there. This is the current BootE compatibility
target for Rhapsody DR2 media.

The native Rhapsody DR2 fallback DVD uses the same BIOS-facing 2.88 MB
floppy-emulation shape as the OPENSTEP fallback. Its boot image is
`out/rhapsody-dr2/rhapsody-dr2-install-driver-2880.img`: the installation
floppy occupies the first 1.44 MB and the Rhapsody driver disk occupies the
second 1.44 MB. If stock Rhapsody still prompts for a driver diskette, the next
fix belongs in the boot2/installer driver-media lookup, not the El Torito
catalog.

The profile controls the preloaded DriverKit classes and table selection; a
machine still needs matching virtual hardware (the loader cannot make an
absent controller attach).

This produces `out/boote/boote-openstep-patch4.iso`. BootE is the no-emulation
El Torito entry, while the same disc is labelled so BootE discovers the UFS
extent and loads `/mach_kernel` directly from the CD. The disc profile uses
the native installer convention `rootdev=cdrom`, rather than the installed
disk profile's `rootdev=hd0a`.

An optional second UFS can carry Developer, Rhapsody, or Darwin content:

```sh
BOOTE_SECONDARY_UFS=path/to/darwin.ufs make boote-openstep-disc
```

The secondary payload is mastered as NeXT partition `b`. A genuinely bootable
XNU lane still requires BootE to enumerate non-root NeXT partitions, plus a
version-matched i386 kernel, extensions/boot archive, and root filesystem. The
vault now has Darwin 0.3 and Darwin 6.0.2 images for reverse-engineering those
contracts, but they are different lanes: Darwin 0.3 is PowerPC/APM-oriented,
while Darwin 6.0.2 is the latest verified local x86 XNU kernel/media target.

Boot the ISO alone, or attach an installed raw/VHD/QCOW2 disk:

```sh
tools/boote/run-boote-smoke.sh
tools/boote/run-boote-smoke.sh path/to/openstep.raw
```

For early-kernel debugging, start the QEMU wrapper paused with a GDB stub:

```sh
REOPENSTEP_QEMU_ISO=out/boote/boote-openstep-patch4.iso \
REOPENSTEP_QEMU_GDB_PORT=1234 REOPENSTEP_QEMU_GDB_WAIT=yes \
scripts/run-openstep-autoboot.sh install
gdb /path/to/mach_kernel
(gdb) target remote :1234
(gdb) info registers
```

The QEMU monitor remains available on its console; use `info registers`,
`xp/32wx 0x11000`, and `x/16i $eip` to inspect the handoff structure and the
instruction where early Mach initialization stops. Omit `GDB_WAIT` to let the
guest run until the debugger attaches.

The wrapper uses 512 MB because this Chameleon revision reserves its allocator
at physical address `0x08100000`; a 128 MB VM corrupts boot2 before its prompt.
The QEMU smoke test reaches the text-mode itomato `Darwin/x86 boot v5.0.133` prompt.
Attached disks run under QEMU snapshot mode and are not modified.

## Automated QEMU assertions

Run the fast host/parser checks plus the full three-lane VM matrix:

```sh
make boote-qemu-matrix
```

The matrix launches separate snapshot-mode Pentium III/512 MB guests and
asserts visible VGA output with OCR:

1. **prompt:** the CD alone reaches the itomato-branded `Darwin/x86 boot v5.0.133` prompt;
2. **ufs:** `test.VHD` is discovered and offered as `NeXT UFS`;
3. **eisa:** `out/openstep-user-ufs.raw` enters OPENSTEP 4.2 and reaches the
   current expected `Missing EISA kernel bus class` boundary.

Every case stores its QEMU command, host identity, ISO hash, disk label, disk
sample fingerprint, timings, screenshot, OCR transcript, monitor log, and JSON
report under `out/boote/test-runs/`. The aggregate result is
`out/boote/test-runs/matrix-latest.json`; `latest.json` points to the most
recent individual case. A failing earlier stage identifies whether a change
broke El Torito execution, NeXT disk/UFS discovery, or OPENSTEP kernel handoff.

Run one boundary directly when iterating:

```sh
python3 tools/boote/test-qemu.py --expect prompt --no-disk
python3 tools/boote/test-qemu.py --expect ufs --disk test.VHD
python3 tools/boote/test-qemu.py --expect eisa \
  --disk out/openstep-user-ufs.raw
```

The default disk fingerprint hashes three 1 MB regions plus the exact size so
the 2 GB fixture does not dominate every test. Add `--full-disk-hash` when a
release or provenance record requires the complete SHA-256. On macOS the
harness uses QEMU's Cocoa display backend; `tesseract` plus ImageMagick or
`sips` is required for screen assertions. Override `--display` for another
host backend.

NASM is required for the 16-bit BIOS/El Torito stages. Host conversion tools
are built only for the native build host; only the loader products are i386.
The i386 code targets i686 without SSE/SSE2 so it remains valid on Socket 370
Pentium III and Celeron systems rather than requiring a Pentium 4.
The source revision and embedded build timestamp are pinned, so identical
toolchains produce stable loader artifacts.

The current build proves BIOS execution, NeXT `dlV3` discovery, big-endian UFS
access, and loading/handoff of the installed `mach_kernel`. On a NeXT UFS
volume, `CONFIG_OPENSTEP_HANDOFF` now selects a legacy adapter while other
filesystems retain Chameleon's Darwin path. The adapter creates the fixed
`KERNBOOTSTRUCT` at physical `0x11000`, supplies memory sizes and the required
low-memory allocation floor, and imports the installed
`System.config/Default.table`. QEMU confirms that OPENSTEP enables paging with
`CR3=0x20000`, initializes Mach, and services interrupts.

BootE masks hardware IRQs immediately after entering protected mode and keeps
them masked through the loader-to-kernel jump (the legacy path intentionally
leaves interrupts disabled until the kernel establishes its IDT). This is important on
86Box/CUBX, where the periodic timer can otherwise arrive during the short
handoff window with `IDT=0`, causing a double/triple fault and an apparent
CD reboot loop. If a loop persists, enable 86Box's CPU/BIOS trace and compare
the last EIP with the loader's `__TEXT` range before changing storage tables.

The standalone-driver boundary has been crossed. BootE maps the native
`sarld`, preserves the thin kernel and its `__LINKEDIT` data as the base file,
links the selected `_reloc` images, records them in the legacy driver array,
and appends each selected DriverKit table. The Socket 370 profile preloads the
EISA and PCI buses, Intel chipset, PS/2 keyboard, dual-channel EIDE/ATAPI, BusLogic BT-958D,
Adaptec 2940, Patch 4 VBE, and Matrox Millennium II drivers. Its explicit
hardware-table choices avoid the generic EIDE and original-Millennium defaults.
QEMU detects the ATA disk, reads its `OPENSTEP_4.2` label, and selects `hd0a`
(`rootdev 0x300`); keyboard attachment and reliable root I/O remain active test
boundaries.

`make boote-vesa-iso` builds `out/boote/boote-vesa.iso`, the opt-in Patch 4
multi-driver image. The VBE driver is preloaded, while the BootE graphics-mode
handoff remains disabled to retain the diagnostic console. Pair it with
`out/boote/openstep-user-patch4-vesa.raw`, produced by
`make patch4-vesa-fixture`, then
assert the crossed boundary with `python3 tools/boote/test-qemu.py --iso
out/boote/boote-vesa.iso --disk out/boote/openstep-user-patch4.raw --expect
eide`.

The current profile establishes the shared BootE core. Subsequent handoff
profiles will preserve the same disk and filesystem layer:

- `openstep`: legacy kernel parameters and DriverKit configuration tables
  (selected automatically for `NeXT UFS`; standalone drivers remain next).
- `rhapsody`: transitional Mach/BSD bootstrap structures.
- `marklar`: Darwin i386 `boot_args`, device tree, and optional fake EFI.

Proprietary DTK/Marklar media remains an optional hash-pinned vault input; it
is not fetched by this build.
