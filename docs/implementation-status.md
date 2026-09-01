# Implementation status

This document is the handoff map for the Reopenstep milestones. Generated
images live under `out/` and proprietary inputs live under `vault/`; neither is
committed. Source changes, profiles, reverse-engineering notes, and reproducible
build wrappers are committed.

## Milestones

| milestone | status | implemented boundary | next boundary |
|---|---|---|---|
| MS0: Darwin installer root | working | immutable Darwin 0.3 i386 source, writable overlay, reproducible QEMU single-user boot assertion through the named mountroot panic | resolve root driver/filesystem binding and mount the single-user root |
| MS1: rebuild El Torito media | working | User and Developer UFS partitions, corrected NeXT `dlV3` fields, bootable hybrid wrapper | final installation regression matrix |
| MS2: startup/install drivers | working | EIDE/PIIX, AMD PCscsi, and BusLogic lanes with separate install, rescue, and installed-disk tables | validate every controller lane after first reboot |
| MS3: installation overlays | working | Developer partition installation, Patch 4 inputs, transactional UFS tree insertion, BOM-oriented guest scripts, host package composer | package catalog and OPENSTEP Installer acceptance test |
| MS4: quad-fat builder | scaffolded | four-architecture profiles and fat-binary validator | boot and validate the native build image |
| MS5: build farm | scaffolded | build-plan schema and native Distributed Objects reference implementation | deploy controller/workers on the trusted build LAN |

## BootE

BootE is the current alternative boot lane. It builds pinned Chameleon/boot132
sources without the historical 32-bit curses configurator, discovers whole-disk
NeXT labels and MBR type `0xa7`, reads big-endian UFS, and loads the installed
OPENSTEP kernel.

For `NeXT UFS` volumes it selects a dedicated OPENSTEP handoff. The adapter
materializes `KERNBOOTSTRUCT` at physical `0x11000`, imports the installed
`System.config/Default.table`, and sets the conventional-memory floor to
`0x20000`. QEMU confirms that the kernel enables paging with `CR3=0x20000`,
initializes its GDT/IDT, and services interrupts. Other volume types retain the
Darwin/Marklar handoff.

BootE now reproduces native `sarld`: it preserves the thin i386 kernel as the
linker base file, maps `/usr/standalone/i386/sarld`, links selected `*_reloc`
images, appends their DriverKit tables, and writes the address/size array in
`KERNBOOTSTRUCT`. The default Socket 370 EIDE/ATAPI profile reaches real
hardware attachment in QEMU: ATA drive 0 and the ATAPI CD-ROM on drive 1 are
identified, both `OPENSTEP_4.2` labels are read, and the kernel selects CD root
(`rootdev 0x680`). A secondary-channel probe may warn when that channel is
empty; single-channel and SCSI profiles are provided for those machines.

QEMU physical-memory inspection of `KERNBOOTSTRUCT + 0x154` reports nine
standalone drivers, with nine nonzero address/size pairs beginning at `+0x168`.
This verifies that every driver in the expanded profile linked successfully;
it does not imply that every driver found matching hardware or attached.
The BootE link map now ends at `0x9a784`. Freestanding unwind metadata is
disabled, saving roughly 20 KiB and leaving both the CUBX BIOS workspace and
the nominal `0x9fc00` EBDA boundary intact across the El Torito handoff.

`make boote-openstep-disc` now masters BootE and a Patch 4 User UFS on the
same 488 MB optical image. QEMU validates the no-emulation El Torito catalog,
finds the embedded `NeXT UFS`, reads `/mach_kernel` and `sarld`, and reaches
native CD root-device selection when a target disk is attached. The disc
wrapper can place a
second Developer/Rhapsody/Darwin UFS in partition `b`. BootE currently mounts
only the label's selected root partition, so menu enumeration of partition `b`
is still required; `vault` also contains no version-matched XNU kernel,
extensions/boot archive, or Darwin root filesystem.

The supplied `itomato/RhapsodiOS` repository is confirmed to be a large
Darwin/Rhapsody source tree, not a binary release; it publishes no ISO or UFS
asset. `tools/boote/make-boote-xnu-ufs-vesa.sh` therefore requires an
externally built `XNU_UFS` root and uses the actual generated Patch 4 installer
UFS as partition `b`. `make rhapsody-gap` now reports this boundary
explicitly: it verifies the available OPENSTEP/BootE artifacts, checks the
pinned `nextufs` mutator, records that host-side UFS creation/resizing/fsck is
not available in the current macOS build, and inspects a supplied XNU/Rhapsody
UFS root for minimum boot paths.

Titan1U Rhapsody DR2 media are now inspectable without committing the media:
`./reopenstep rhapsody inspect-native-boot` recovers the native boot1 contract
from a boot floppy or raw CD. The recovered v5.0.40 path reads label sector 15,
derives boot2 from label offsets `0x5c` and `0x7c`, loads `0x58` BIOS sectors
to physical `0x3000`, and jumps there. This gives BootE a concrete Rhapsody
compatibility target independent of the still-open UFS filesystem mastering
gap.

RhapsodyAnswers beta2 documents the key filesystem blocker: RDR/Intel does not
use the OPENSTEP/NeXTStep big-endian m68k UFS-on-all-architectures convention.
It uses a native-endian BSD 4.4-derived UFS variant, while earlier Mach systems
used BSD 4.3-era UFS with byte-swapping on Intel. The tooling now reports
`rhapsody-dr2` roots as incompatible with `nextufs` path probing instead of
misclassifying an unreadable candidate as simply missing `/mach_kernel`.

The XNU boot lane is now split from the RDR filesystem lane. `make xnu-kernel`
adopts an existing x86 Mach-O kernel or runs an explicitly supplied source
build command, then `./reopenstep xnu inspect-kernel --require-boote` validates
that the artifact has an i386/x86_64 slice. `make boote-xnu-kernel-iso`
masters that kernel onto a BootE HFS/ISO hybrid test disc. This provides a
kernel-entry harness for Darwin/XNU work while the RDR/i386 BSD 4.4 UFS reader
remains unresolved.

Patch 4 host-side overlay and the opt-in VESA handoff are now reproducible; see
`docs/patch4-vesa-boot.md`. The complete User Patch payload, including its
kernel, native VBE booter, VBE driver bundle, AppKit, Foundation, and shared
library, boots to this same boundary. Retaining the framebuffer in the
installer still depends on the same `sarld` driver-preload milestone.

Detailed evidence is in `docs/boot-reverse-engineering.md`; the loader-specific
test progression is in `docs/chameleon-ufs-boot.md`.

## Darwin installer root

`make darwin-installer-image` creates a local QCOW2 overlay backed by the
immutable `vault/Darwin03.qcow` i386 image. The source format, virtual and
actual sizes, and SHA-256 identity are available through
`./reopenstep darwin inspect-installer`; vault contents are never modified.

`make darwin-installer-test` boots that overlay read-only through a QEMU
snapshot, interrupts boot2's countdown, and enters `-s`. On the pinned
`pc-i440fx-7.2`/Pentium contract, Rhapsody boot1 and boot2 v5.0.41.1 load
Kernel Release 5.3, DriverKit detects the primary IDE disk, and the kernel
selects `rootdev 300, howto 40002`. The test then separately probes for init's
single-user/read-only-root messages and preserves screenshots, OCR transcripts,
the exact command, and stage timings in `out/darwin03/test-runs/`.

The current blocker is narrower than image or boot-loader compatibility. The
legacy EIDE driver times out during commands `0xec`, `0x10`, and `0x20`, but
boot continues to `rootdev 300`; `ufs_mountroot` and `od986a_mountroot` then
fail with errno 19 before a no-suitable-interface panic. The root driver or
filesystem binding must be corrected before the installer can mutate the
overlay. QEMU machine contracts are selectable for comparisons;
`pc-i440fx-2.4` was slower and did not reach the verified `rootdev` boundary in
the same 60-second window.

## Installation composer

`apps/ReopenStepWorkbench` is the cross-platform GNUstep/AppKit shell around
the repository CLI. Its Installation Composer is backed by a serializable
recipe rather than direct filesystem mutation from Objective-C. The first
working surface provides staged payload selection, payload fingerprinting,
classic `.tar.Z`/`.bom`/`.info`/`.sizes` package creation, and structural
inspection. The remaining surface will provide:

1. a staged payload tree populated through file/folder selection;
2. package collections for Patch 4, KB7SQI, Big Green Disc, Lighthouse, and
   locally adopted packages;
3. explicit startup, installed-system, and post-install destinations;
4. installed binary BOM conversion/inspection after OPENSTEP acceptance tests;
5. collision, ownership, mode, architecture, and missing-input diagnostics;
6. a reviewable recipe that invokes the same UFS insertion and ISO mastering
   operations used by unattended builds.

Package payloads remain external inputs. The repository stores identifiers,
hashes, destinations, and ordering rules—not proprietary package contents.

## Verification

Run the complete host checks before committing:

```sh
make check
make boote-test
make workbench-test
git diff --check
```

Build products can be regenerated with `make boote-build` and `make boote-iso`.
QEMU/86Box wrappers use snapshot or explicit lifecycle modes so installation,
rescue, and installed-disk tests remain distinct.

`make boote-qemu-matrix` is the executable BootE regression boundary. It
separates El Torito prompt, NeXT UFS discovery, and OPENSTEP kernel handoff
failures and preserves screenshots, OCR, label evidence, and JSON reports for
each run. The disk-backed lane asserts ATA/ATAPI discovery, disk-label reads,
and CD-root selection. SCSI profiles remain separate lanes because controller
hardware and OpenStep table semantics differ.

The locally unpacked `BootX-BootX-34/` tree is an ignored research reference,
not a build input. If a BootX-derived lane becomes necessary, add a pinned
bootstrap and a source revision file rather than committing an anonymous source
snapshot. BootE deliberately remains an i386 BIOS loader and does not introduce
the PowerPC BootX execution model.
