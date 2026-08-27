# Patch 4 VESA boot path

OPENSTEP 4.2 Patch 4 must be treated as a coherent system update. Replacing
only `/mach_kernel` leaves the old frameworks, shared library, native booter,
and display-driver bundle behind. `reopenstep patch4` reads the NeXT Installer
`bigtar` payload on the host and applies it transactionally to a copy of a UFS
image; an OPENSTEP machine is not required.

## Verified Patch 4 set

The User Patch contains 130 payload entries. The host-side inspector verifies
the archive checksum and reports hashes for the VESA boot dependency set:

- `/mach_kernel`
- `/usr/standalone/i386/boot`
- `/private/Drivers/i386/VBE20DisplayDriver.config`, including the runtime and
  standalone `_reloc` image
- `AppKit.framework` and `Foundation.framework`
- `/usr/shlib/libFoundation_s.E.shlib`

The Developer Patch contains compiler/editor fixes but no additional VESA boot
component. It can be installed later as a separate package overlay.

Inspect or extract either archive without native `tar`:

```sh
./reopenstep patch4 inspect vault/OS42MachUserPatch4.tar
./reopenstep patch4 extract vault/OS42MachUserPatch4.tar --output out/patch4-user-root
```

The decoder supports NeXT's 225-byte pathname header and its non-POSIX
hard-link rule: a hard-link header records the target size but consumes no
payload blocks. It rejects bad checksums and path traversal.

## Reproducible test fixture

Build a Patch 4 UFS copy and select QEMU's conventional 1024x768, 32-bit VBE
mode (`0x118`):

```sh
make patch4-vesa-fixture
make boote-vesa-iso
```

Outputs are intentionally untracked large binaries:

- `out/boote/openstep-user-patch4.raw`: complete User Patch overlay
- `out/boote/openstep-user-patch4-vesa.raw`: the same image with the VBE table
  changed from Patch 4's conservative mode 257 (`0x101`, 640x480x8) to mode
  280 (`0x118`, exposed by QEMU as 1024x768x32)
- `out/boote/boote-vesa.iso`: BootE with the opt-in VESA handoff configuration

The mode may also be selected independently:

```sh
./reopenstep patch4 set-vesa-mode \
  --image out/boote/openstep-user-patch4.raw \
  --output out/boote/openstep-user-patch4-vesa.raw \
  --mode 0x118
```

Do not assume that a mode number exists on every physical or emulated video
BIOS. For 86Box, first use BootE's VESA mode listing and select a mode actually
advertised by the configured Matrox/Voodoo VGA BIOS. The Voodoo Graphics card
is a separate 3D accelerator and does not provide the primary VBE framebuffer;
the Matrox BIOS does.

## BootE handoff

`tools/boote/root-vesa/Extra/com.apple.Boot.plist` asks Chameleon for
`1024x768x32`. The Socket 370 profile preloads the Patch 4 VBE driver but keeps
the dedicated `OPENSTEP VBE` switch disabled while the black-screen handoff is
investigated. When enabled, BootE:

1. selects a linear VBE framebuffer through BIOS interrupt `0x10`;
2. leaves `"Boot Graphics" = "Yes"` in the OPENSTEP System configuration;
3. marks the legacy KERNBOOTSTRUCT display mode as graphical; and
4. hands off to the Patch 4 kernel.

QEMU confirms that the enabled handoff changes the emulated display to
1024x768, but the framebuffer remains black after kernel entry. The default
test profile therefore links `VBE20DisplayDriver_reloc` and passes its mode-280
table without enabling the BootE graphics switch.

The ordinary `boote-smoke.iso` remains text-only, so its existing OCR regression
boundary stays deterministic.

## Current measured boundary

The following test passes with the Patch 4 kernel and sarld/EIDE BootE ISO:

```sh
python3 tools/boote/test-qemu.py \
  --iso out/boote/boote-vesa.iso \
  --disk out/boote/openstep-user-patch4.raw \
  --expect eide \
  --output-root out/boote/vesa-1024-test-runs
```

It crosses the former `Missing EISA kernel bus class` boundary, registers EISA,
links EIDE, detects the QEMU disk, reads its NeXT label, and selects `hd0a`.
The remaining QEMU storage boundary is an ATA interrupt timeout during sector
reads. The screen remains 640x480 because VBE retention is intentionally off
until root I/O is reliable; `VBE20DisplayDriver_reloc` is not yet part of this
minimal profile.

## Remaining path to a color installer

The next implementation order is constrained by dependencies:

1. **Done:** load `/usr/standalone/i386/sarld`, link `EISABus_reloc`, append its
   table, and populate the recovered legacy driver records.
2. Complete one storage path at a time (`EIDE`, BusLogic, then Adaptec). EIDE
   now discovers the disk and root label; reliable sector interrupts remain.
3. Link `VBE20DisplayDriver_reloc`, preserve the selected BIOS mode, and add
   `VBE20DisplayDriver` to the installation System configuration while removing
   the VGA fallback from the same instance.
4. Start the Patch 4 AppKit/Foundation installation environment and capture a
   screenshot proving framebuffer dimensions and color depth.
5. Repeat the mode probe on 86Box with Matrox Millennium II and record the
   supported-mode matrix. Only then raise the default beyond 1024x768.

This separates three facts that otherwise look deceptively similar: BootE can
set a VBE mode; the Patch 4 kernel and standalone drivers can load; a full-color
installer still requires reliable root I/O and the VBE driver profile.
