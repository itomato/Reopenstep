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

Master a small El Torito test ISO from that loader:

```sh
tools/boote/make-boote-iso.sh
```

`out/boote/boote-smoke.iso` is intended to be booted with an installed NeXT
UFS disk attached. It contains no Apple system files or kernel of its own.

Boot the ISO alone, or attach an installed raw/VHD/QCOW2 disk:

```sh
tools/boote/run-boote-smoke.sh
tools/boote/run-boote-smoke.sh path/to/openstep.raw
```

The wrapper uses 512 MB because this Chameleon revision reserves its allocator
at physical address `0x08100000`; a 128 MB VM corrupts boot2 before its prompt.
The QEMU smoke test reaches the text-mode `Darwin/x86 boot v5.0.132` prompt.
Attached disks run under QEMU snapshot mode and are not modified.

## Automated QEMU assertions

Run the fast host/parser checks plus the full three-lane VM matrix:

```sh
make boote-qemu-matrix
```

The matrix launches separate snapshot-mode Pentium III/512 MB guests and
asserts visible VGA output with OCR:

1. **prompt:** the CD alone reaches `Darwin/x86 boot v5.0.132`;
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

The standalone-driver boundary has been crossed. BootE maps the native
`sarld`, preserves the thin kernel and its `__LINKEDIT` data as the base file,
links the selected `_reloc` images, records them in the legacy driver array,
and appends each selected DriverKit table. The `EISABus EIDE` diagnostic profile
registers EISA, detects QEMU's ATA disk, reads its `OPENSTEP_4.2` label, and
selects `hd0a` (`rootdev 0x300`). QEMU currently reaches an EIDE interrupt
timeout during sector reads; `OPENSTEP_EIDE_SAFE` disables multiple-sector
transfers but does not eliminate that PIIX/interrupt compatibility boundary.

`make boote-vesa-iso` builds `out/boote/boote-vesa.iso`, the opt-in Patch 4
sarld/EIDE diagnostic image. Its VBE handoff remains disabled while the storage
path is measured in text mode. Pair it with `make patch4-vesa-fixture`, then
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
