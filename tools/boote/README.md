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

The remaining boot boundary is standalone driver linkage. A complete installed
UFS reaches `Missing EISA kernel bus class`: the table names `EISABus`, but the
corresponding `EISABus_reloc` module has not been linked by `sarld`, loaded after
the kernel, and recorded in the legacy driver array. `test.VHD` is useful only
for the kernel handoff test; its visible UFS tree does not contain the installed
`System.config`, so it exercises the adapter's missing-config diagnostic.

The current profile establishes the shared BootE core. Subsequent handoff
profiles will preserve the same disk and filesystem layer:

- `openstep`: legacy kernel parameters and DriverKit configuration tables
  (selected automatically for `NeXT UFS`; standalone drivers remain next).
- `rhapsody`: transitional Mach/BSD bootstrap structures.
- `marklar`: Darwin i386 `boot_args`, device tree, and optional fake EFI.

Proprietary DTK/Marklar media remains an optional hash-pinned vault input; it
is not fetched by this build.
