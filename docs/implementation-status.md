# Implementation status

This document is the handoff map for the Reopenstep milestones. Generated
images live under `out/` and proprietary inputs live under `vault/`; neither is
committed. Source changes, profiles, reverse-engineering notes, and reproducible
build wrappers are committed.

## Milestones

| milestone | status | implemented boundary | next boundary |
|---|---|---|---|
| MS1: rebuild El Torito media | working | User and Developer UFS partitions, corrected NeXT `dlV3` fields, bootable hybrid wrapper | final installation regression matrix |
| MS2: startup/install drivers | working | EIDE/PIIX, AMD PCscsi, and BusLogic lanes with separate install, rescue, and installed-disk tables | validate every controller lane after first reboot |
| MS3: installation overlays | working | Developer partition installation, Patch 4 inputs, transactional UFS tree insertion, BOM-oriented guest scripts | package catalog and host composer |
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

The next BootE boundary is `sarld`. OPENSTEP names `EISABus` in the imported
configuration, but boot drivers are Mach-O preload files with unresolved
relocations. Native boot v40.13.1 links each selected `*_reloc` against the
kernel, places the result after the kernel, and records address/size pairs in
`KERNBOOTSTRUCT`. Until BootE reproduces that operation, the complete UFS stops
cleanly at `Missing EISA kernel bus class` instead of triple-faulting.

Detailed evidence is in `docs/boot-reverse-engineering.md`; the loader-specific
test progression is in `docs/chameleon-ufs-boot.md`.

## Installation composer

`apps/ReopenStepWorkbench` is the cross-platform GNUstep/AppKit shell around
the repository CLI. Its next surface is an Installation Composer backed by a
serializable recipe rather than direct filesystem mutation from Objective-C.
The surface will provide:

1. a staged payload tree populated through file/folder selection;
2. package collections for Patch 4, KB7SQI, Big Green Disc, Lighthouse, and
   locally adopted packages;
3. explicit startup, installed-system, and post-install destinations;
4. `mkbom` creation and `lsbom` inspection through argument-array subprocesses;
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

The locally unpacked `BootX-BootX-34/` tree is an ignored research reference,
not a build input. If a BootX-derived lane becomes necessary, add a pinned
bootstrap and a source revision file rather than committing an anonymous source
snapshot. BootE deliberately remains an i386 BIOS loader and does not introduce
the PowerPC BootX execution model.
