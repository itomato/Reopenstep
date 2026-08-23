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

`tools/boote/root-vesa/Extra/com.apple.Boot.plist` enables the dedicated
`OPENSTEP VBE` switch and asks Chameleon for `1024x768x32`. In this mode BootE:

1. selects a linear VBE framebuffer through BIOS interrupt `0x10`;
2. leaves `"Boot Graphics" = "Yes"` in the OPENSTEP System configuration;
3. marks the legacy KERNBOOTSTRUCT display mode as graphical; and
4. hands off to the Patch 4 kernel.

The ordinary `boote-smoke.iso` remains text-only, so its existing OCR regression
boundary stays deterministic.

## Current measured boundary

The following test passes with the Patch 4 kernel and VESA-specific BootE ISO:

```sh
python3 tools/boote/test-qemu.py \
  --iso out/boote/boote-vesa.iso \
  --disk out/boote/openstep-user-patch4-vesa.raw \
  --expect eisa \
  --output-root out/boote/vesa-1024-test-runs
```

It reaches the patched `NeXT Mach 4.2` kernel and the expected `Missing EISA
kernel bus class` boundary. The kernel panic screen is still 640x480. That is
not evidence that the Patch 4 VBE runtime failed: BootE has not yet invoked or
reproduced `sarld`, so none of the selected standalone drivers—including
`VBE20DisplayDriver_reloc`—has been linked into the kernel. OPENSTEP therefore
falls back to its early console before the display server can retain the VBE
framebuffer.

## Remaining path to a color installer

The next implementation order is constrained by dependencies:

1. Load `/usr/standalone/i386/sarld` and link `EISABus_reloc` and
   `PCIBus_reloc`; populate the recovered legacy driver records.
2. Add one storage path at a time (`EIDE`, BusLogic, then Adaptec) and prove
   that the installer UFS mounts as root.
3. Link `VBE20DisplayDriver_reloc`, preserve the selected BIOS mode, and add
   `VBE20DisplayDriver` to the installation System configuration while removing
   the VGA fallback from the same instance.
4. Start the Patch 4 AppKit/Foundation installation environment and capture a
   screenshot proving framebuffer dimensions and color depth.
5. Repeat the mode probe on 86Box with Matrox Millennium II and record the
   supported-mode matrix. Only then raise the default beyond 1024x768.

This separates three facts that otherwise look deceptively similar: BootE can
set a VBE mode now; the Patch 4 kernel can boot now; a full-color installer
requires the standalone driver-link and root-mount stages that remain.
