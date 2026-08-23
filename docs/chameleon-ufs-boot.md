# Chameleon UFS boot lane

The minimal product is now named **BootE**: an i386 BIOS/El Torito loader with
a deterministic static configuration. `tools/boote/build-boote.sh` bypasses
Chameleon's 32-bit curses configuration utility completely and builds the
conversion utilities for the native host while retaining i386 loader output.

The next boot milestone is intentionally separate from CDIS mastering. The v5
installer proves the User and Developer UFS layout while retaining the native
OPENSTEP startup image. The next lane replaces only the boot path.

The vendored Chameleon source provides several useful foundations:

- `i386/libsaio/ufs.c` reads big-endian UFS superblocks and files.
- the reproducible bootstrap enables `UFS_SUPPORT` in `i386/libsaio/disk.c`.
- FDisk type `0xa8` is registered as Apple UFS.
- `chain0` recognizes type `0xa8`.
- The source retains substantial NeXT-derived boot and Mach-O loader code.

The first filesystem milestone is implemented. `nextlabel.c` validates `dlV3`
copies at sectors 0, 15, 30, and 45, decodes the 24-bit partition fields, and
computes `(front + root.base) * label_sector_size`. Chameleon now tries that
scanner for both MBR type `0xa7` partitions and native whole-disk NeXT labels.
The installed 86Box disk resolves to byte offset 163840 (sector 320), matching
`nextufs` independently. `tools/chameleon/test-nextlabel.sh` compiles and runs
the same C parser on the host.

BootE now has a selectable OPENSTEP handoff in addition to the unmodified
Darwin lane. Selection is scoped to volumes identified as `NeXT UFS`. The
OPENSTEP 4.2 kernel ignores Chameleon's pointer in EAX and instead reads a
legacy `KERNBOOTSTRUCT` at physical `0x11000`; the adapter materializes that
fixed structure and jumps directly after Mach-O decoding, before fake EFI and
Darwin driver loading.

The generated `boote-smoke.iso` has also passed a QEMU BIOS smoke test through
the visible Chameleon text prompt. Use at least 512 MB of guest RAM: this source
line reserves its heap at `0x08100000`, just beyond a 128 MB machine. UFS disk
enumeration is now proven against `test.VHD`: BootE offers startup from
`NeXT UFS`, loads the installed kernel, and crosses into the handoff path. The
old Darwin contract triple-faulted during OPENSTEP's paging transition with
`CR0=0x80010033` and `CR3=0`. Kernel disassembly and native boot v40.13.1 show
that KERNBOOTSTRUCT offset `0x138` is the conventional-memory allocation floor.
BootE sets it to `0x20000`, the first page above its legacy stack/boot arena.
QEMU now shows `CR0=0x8001003b`, `CR3=0x20000`, a live kernel GDT/IDT, and
serviced interrupts. This completes the basic kernel-entry and paging contract.

The adapter also loads `/private/Drivers/i386/System.config/Default.table` into
the native configuration address `0x134fc` and forces text boot for diagnostic
visibility. On `out/openstep-user-ufs.raw`, the kernel consumes that table and
advances to `Missing EISA kernel bus class`. This is expected until BootE can
invoke or reproduce `sarld`: `_reloc` files are Mach-O preload images with
unresolved relocation records, not binaries that can merely be copied into
memory. Each linked result must be placed after the kernel and represented by
an address/size pair beginning at KERNBOOTSTRUCT offset `0x168`, with the count
at offset `0x154`.

The test progression is therefore:

1. **Done:** build a minimal Chameleon `cdboot`/boot132 image without optional
   modules or the curses configurator.
2. **Done:** add `0xa7`/whole-disk recognition and resolve the `dlV3` root UFS
   byte offset before calling `UFSInitPartition`.
3. **Done:** discover the installed NeXT UFS and load/handoff `/mach_kernel`.
4. **Done:** add an OPENSTEP handoff mode supplying the fixed legacy boot
   arguments, memory floor, and System configuration table while leaving the
   Darwin path unchanged.
5. Reproduce native `sarld` invocation and populate the legacy standalone
   driver records, beginning with `EISABus`, `PCIBus`, and the selected storage
   driver.
6. Test the same boot image against OPENSTEP 4.2, Rhapsody, and a Darwin UFS
   fixture. Only after the handoff works should it replace the native startup
   image in the combined installer.

Clover adds UEFI complexity without helping the legacy OPENSTEP handoff, so
Chameleon/boot132 is the preferred first implementation. A small chainloader
using Chameleon's UFS reader remains the fallback if adapting its full boot2 is
more invasive than retaining OPENSTEP's native second-stage entry contract.
