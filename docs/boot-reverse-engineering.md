# OpenStep Intel boot reverse-engineering baseline

The vault now contains the original 1.44 MB install and beta-driver boot
floppies. These are golden inputs for Ghidra analysis; do not modify them.

| image | SHA-256 | notable strings |
|---|---|---|
| `vault/4.2_Install_Disk.floppyimage` | `58e391565c3dab98e01a8e5ff0c2a67ecbc67e0e5376a211a4a40761f20a238a` | `OPENSTEP boot1 v40.13.1`, `4.2mach_Install`, `sarld`, `mach_kernel`, `/private/Drivers/i386` |
| `4.2_Beta_Drivers_1.floppyimage` | `54fb79078c770c78d15b29663f6f87980e3a1a1e479578765afca75337113624` | `OPENSTEP boot1 v40.13.1`, `42_Beta_Drivers_1`, `sarld` |
| `4.2_Beta_Drivers_2.floppyimage` | `3aa16cfefd65671aaaff0c852d86f551a0d1bf4882d06523a186865bb7443037` | `OPENSTEP boot1 v40.13.1`, `42_Beta_Drivers_2`, `sarld` |

## Ghidra targets

Import each image as a raw 1.44 MB disk image. Analyze the first sector as
16-bit x86 real-mode code, then locate the `OPENSTEP boot1` string and the
filesystem loader around it. The key recovery targets are:

1. BIOS geometry and sector-loading routines in the first-stage code.
2. The `boot1` handoff and its disk/partition arguments.
3. `sarld` path resolution and standalone-driver loading.
4. The configuration-file parser (`mach_kernel.rcz` and startup settings).
5. Driver-family enumeration and `/private/Drivers/i386` lookup.
6. Install-mode branching and the transition into `mach_kernel`.

Record function signatures, sector offsets, load addresses, and file paths in
the Ghidra project. The resulting notes should be sufficient to make a native
boot-block writer and to explain exactly which startup files are mandatory.

Generate reproducible marker offsets before importing an image into Ghidra:

```sh
python3 tools/analyze_bootfloppy.py vault/4.2_Install_Disk.floppyimage \
  --output out/install-bootfloppy-map.json
```

The report records the image hash, 512-byte sector number, byte offset, and
boot signature for every relevant loader/configuration string.

The strings already establish that the installer boot path is not merely an
El Torito wrapper: it loads `sarld`, reads a compressed kernel/configuration,
can prompt for driver media, and searches the i386 driver directory.

## Initial Ghidra loader setup

For the floppy images, import as a raw binary with these settings:

```text
Language: x86:LE:16:Real Mode
Base address: 0x7c00
Entry point: 0x7c00
Block size: 512 bytes
```

The BIOS loads sector zero at physical `0000:7c00`; the final two bytes are
the `55 aa` boot signature. The install image's first visible version string
starts at file offset `0x13b` (`OPENSTEP boot1 v40.13.1`). Treat that string as
an anchor after auto-analysis, not as the entry point. The loader uses BIOS
interrupt `int 13h`, so label disk-read calls and record their CHS/LBA
translation before following the far transfers into later sectors.

The first analysis milestone is a table of every disk read made before the
`sarld` reference at file offset `0x10510`; those reads define the exact
standalone-loader payload and are more useful than string extraction alone.

## Rhapsody DR2 native boot1 baseline

The Titan1U Rhapsody DR2 i386 installation floppy uses `Rhapsody boot1
v5.0.40` and follows the same broad BIOS pattern as the OPENSTEP floppy, but
the boot2 handoff is now recorded as an executable compatibility target:

1. BIOS loads sector zero at `0000:7c00`.
2. boot1 relocates itself to `0000:e000` and continues at `e021`.
3. boot1 reads the NeXT `dlV3` label sector 15 into physical `0x1000`.
4. boot1 reads the media sector size from label-relative offset `0x5c`.
5. boot1 reads the boot2 block from label-relative offset `0x7c`.
6. boot1 converts that NeXT media block to a BIOS 512-byte LBA with
   `boot2_lba = boot2_block * (media_sector_size / 512)`.
7. boot1 reads `0x58` 512-byte sectors to physical `0x3000` and jumps there.

For the Titan1U install floppy, `media_sector_size=1024` and `boot2_block=0x20`,
so boot2 starts at BIOS LBA `0x40`, byte offset `0x8000`. For the Titan1U CD
label, `media_sector_size=2048` and the same boot2 block maps to BIOS LBA
`0x80`, byte offset `0x10000`.

The RhapsodyAnswers beta2 notes confirm that RDR/Intel media are not
OPENSTEP-compatible UFS images. `00004-RDR_Filesystem.rtfd` and
`00021-RDR_UFS_Incompatibilities.rtfd` describe two separate differences:
RDR/Intel removed the OPENSTEP byte-swapping path, and RDR's native filesystem
is based on BSD 4.4 rather than the BSD 4.3 format used by earlier Mach
releases. This explains why extracting at the labelled root offset can still
fail under the repository's OPENSTEP-oriented `nextufs` tool.

Use the checked inspector rather than hand arithmetic when comparing BootE with
native Rhapsody media:

```sh
./reopenstep rhapsody inspect-native-boot path/to/rhapsody_dr2_x86_InstallationFloppy.img
./reopenstep rhapsody inspect-native-boot path/to/rhapsody_dr2_x86.iso
./reopenstep rhapsody analyze-boot path/to/rhapsody_dr2_x86_InstallationFloppy.img
```

This does not make BootE boot Rhapsody yet. It gives BootE a precise target:
the loader must either emulate this boot1/boot2 discovery path or mount the
same Rhapsody 4.4BSD root well enough to load the equivalent kernel and boot
arguments directly.

## Rhapsody DR2 native UFS findings

The RDR/i386 boot2 image contains the native little-endian UFS1 magic constant,
not the swapped OPENSTEP/NeXTStep encoding. Static disassembly around the
superblock validation path shows this check:

```text
cmp dword [superblock + 0x55c], 0x00011954
jz  valid_superblock
...
cmp dword [superblock + 0x34], 0
```

The immediately preceding loader path allocates and reads `0x2000` bytes for
the superblock sample. The practical reader/mastering consequence is:

| field | offset | RDR/i386 interpretation |
|---:|---:|---|
| `fs_bsize` | `0x30` | native little-endian block size |
| `fs_fsize` | `0x34` | native little-endian fragment size; boot2 checks this is nonzero |
| `fs_frag` | `0x38` | native little-endian fragments per block |
| `fs_magic` | `0x55c` | native little-endian `0x00011954` |

For the Titan1U install floppy, the NeXT label reports the root UFS byte offset
as `0x18000`. The primary superblock is at `0x1a000`
(`root + 0x2000`) and `fs_magic` is at `0x1a55c`
(`root + 0x255c`). That is the concrete baseline for a host-side
RDR/i386 reader.

The Titan1U CD contains multiple early native UFS regions before the labelled
payload partition:

| candidate | superblock offsets | format fields |
|---|---:|---|
| boot-support UFS-like region | `0x2a000`, `0x2c000` | `8192/1024/8` |
| CD payload/front region | `0xa2000`, `0xa4000` | `8192/2048/4` |

The second pair matches the CD label's fragment size. Do not treat every magic
hit inside the CD payload as a real superblock; the checked analyzer reports
both the absolute hit and whether nearby `fs_bsize`/`fs_fsize`/`fs_frag` fields
are plausible.

The current implementation gap is therefore narrower than “unknown
filesystem”: we need a BSD 4.4 UFS1 reader/writer path that accepts native
little-endian i386 superblocks, inodes, cylinder groups, directory entries, and
block mapping. The existing OPENSTEP-oriented `nextufs` path should remain
separate because it targets the older swapped Mach UFS variant.

## Darwin 0.3 and 6.0.2 boot baselines

The vault also contains two Darwin images that should be treated as separate
XNU lanes rather than Rhapsody DR2 replacements:

| image | role | verified boot/filesystem facts |
|---|---|---|
| `vault/Darwin03.qcow` | Darwin 0.3 i386 build/root image | Primary single-user build-farm and Rhapsody-kernel userland compatibility lane. |
| `vault/Darwin-0.3.toast` | PowerPC/APM-era Darwin bridge reference | APM image with `Apple_HFS`, `Darwin_OF3_Booter`, `SecondaryLoader`, and `Apple_Rhapsody_UFS`; the UFS root starts at `0x10908800` and is big-endian UFS1; excluded from the i386 target matrix. |
| `vault/Darwin_6_0_2_x86.iso` | Darwin 6.0.2 x86 installer ISO | Hard-disk El Torito image with `usr/standalone/i386/cdboot.dmg`, fat `mach_kernel`, `Extensions.mkext`, and kext bundles. |

The Darwin 0.3 toast root contains `/mach_kernel`, `/System/Library`, and
`/usr`, so it is a valid Darwin root-contract specimen for host-side probing.
The separate `Darwin03.qcow` is the i386 build/root artifact and should be
booted and inspected independently.

```sh
./reopenstep rdrufs inspect vault/Darwin-0.3.toast --root-offset 0x10908800
./reopenstep rhapsody inspect-root vault/Darwin-0.3.toast --root-kind darwin --root-offset 0x10908800
```

Darwin 6.0.2's `cdboot.dmg` contains a nested big-endian UFS1 helper partition
with `mach_kernel.rcz`, `private`, and `System`. It is a boot-helper image, not
a complete installer root:

```sh
./reopenstep rdrufs inspect out/re/darwin-6.0.2/cdboot-partition.img --root-offset 0x3c000
./reopenstep rdrufs list out/re/darwin-6.0.2/cdboot-partition.img / --root-offset 0x3c000
```

The Darwin 6.0.2 ISO root carries the latest verified local x86 XNU kernel:
`Darwin Kernel Version 6.0`, built from `xnu-10-1-root.obj/RELEASE_I386`.
Its boot and kernel strings name `Extensions.mkext`, `System/Library/Extensions`,
IOKit, kext, `Apple_UFS`, and HFS paths. That is the evidence boundary: Darwin
6.0.2 is a good XNU/IOKit customization target, but it does not replace the
OPENSTEP KERNBOOTSTRUCT or Rhapsody DR2 `sarld`/DriverKit handoff.

A read-only native path now exists for the Rhapsody/RDR validation lane:

```sh
./reopenstep rdrufs inspect path/to/rhapsody_dr2_x86_InstallationFloppy.img
./reopenstep rdrufs list path/to/rhapsody_dr2_x86_InstallationFloppy.img /
./reopenstep rdrufs extract path/to/rhapsody_dr2_x86_InstallationFloppy.img /mach_kernel.rcz out/rdr/mach_kernel.rcz
```

For embedded CD regions discovered by `rhapsody analyze-boot`, pass an explicit
filesystem start offset:

```sh
./reopenstep rdrufs list path/to/rhapsody_dr2_x86.iso / --root-offset 0xa0000
```

The reader also auto-detects this case: it tries the label-reported UFS offset
first, then scans early media for plausible native superblocks, preferring a
candidate whose fragment size matches the label. This is necessary for the
Titan1U CD because the label reports a later payload offset while the bootable
RDR filesystem used for `/mach_kernel` is the front UFS beginning at `0xa0000`.

This reader deliberately supports direct and single-indirect UFS1 block reads
first. It is sufficient for bootloader filesystem mapping and file extraction;
writer support should only be added after cylinder-group summaries and free
maps are decoded against known-good media.

The inode path uses standard UFS cylinder-group addressing:

```text
cgbase = fs_fpg * cg + fs_cgoffset * (cg & ~fs_cgmask)
inode_fragment = cgbase + fs_iblkno
```

This matters for the CD: `/mach_kernel` is inode `68983`, so a naïve
`cg * fs_fpg` lookup lands in the wrong inode table. With the offset term, the
reader extracts `/mach_kernel` as a valid i386 Mach-O image.

Additional static anchors recovered from the install image are:

```text
0x1061b  /usr/standalone/i386/sarld
0x106b0  fd()/mach_kernel.rcz
0x10c86  /private/Drivers/i386
0x10dfd  /private/Drivers/i386/System.config/Default.table
0x1130e  /private/Drivers/i386/%s.config/%s_reloc
0x113b6  Can't link driver %s without sarld
```

`System.config/Default.table` is therefore a primary target: it is likely the
default startup-driver table we need to reproduce for the minimal system.
The `%s.config/%s_reloc` format also shows that the loader expects relocated
driver objects, not just arbitrary files copied into the directory.

The surrounding loader strings establish the complete lookup order:

```text
/usr/Devices/System.config/Default.table
/private/Drivers/i386/System.config/Default.table
%s/%s.config/%s.table
/private/Drivers/i386/%s.config/%s_reloc
/usr/Devices/%s.config/%s_reloc
```

They also expose the native states we must reproduce: “Boot Drivers”, active
driver selection, binary loading, standalone linking through `sarld`, and the
failure modes for missing tables, oversized drivers, and link errors. The
minimal image must therefore ship a selected `System.config` instance and
relocated objects for its boot set; a directory containing only `.config`
metadata is insufficient.

## Recovered OPENSTEP kernel handoff ABI

The installed OPENSTEP 4.2 i386 `mach_kernel` has `_start` at `0x185f58`. It
does not consume Chameleon's Darwin boot-argument pointer. `_i386_init` reads
the NeXT `KERNBOOTSTRUCT` at physical `0x11000` directly. The currently
recovered fields are:

| absolute | offset | meaning |
|---:|---:|---|
| `0x11002` | `0x002` | kernel command line parsed by `_getargs` |
| `0x110a4` | `0x0a4` | native `0xa7a7a7a7` structure marker |
| `0x110ac` | `0x0ac` | encoded boot device |
| `0x110b0` | `0x0b0` | conventional memory, KiB |
| `0x110b4` | `0x0b4` | extended memory, KiB |
| `0x110b8` | `0x0b8` | boot kernel filename (64-byte field) |
| `0x11138` | `0x138` | first safe conventional-memory allocation address |
| `0x1114c` | `0x14c` | display mode/state |
| `0x11150` | `0x150` | native boot/install mode |
| `0x11154` | `0x154` | standalone driver count |
| `0x11158` | `0x158` | end of configuration storage |
| `0x11168` | `0x168` | first standalone driver address |
| `0x1116c` | `0x16c` | first standalone driver size |
| `0x134fc` | `0x24fc` | first NUL-terminated configuration table |

Native boot v40.13.1 initializes the configuration pointer to
`KERNBOOTSTRUCT + 0x24fc`. After loading, it derives the low-memory floor from
that end pointer plus `0x400`. BootE cannot clear the complete historical
60 KiB structure immediately before handoff because Chameleon's live stack is
inside the same arena; it snapshots its values and writes only the legacy
fields. A zero `0x138` causes `_alloc_cnvmem` to place the initial page directory
at address zero, after which `_pmap_bootstrap` loads `CR3=0` and triple-faults
as soon as it enables paging. Setting a safe `0x20000` floor produces a live
kernel with `CR3=0x20000`.

`System.config/Default.table` is copied verbatim to `0x134fc` as the first
configuration string. This removes the kernel's `No config table` warning, but
does not instantiate its named bus classes. Boot v40.13.1 uses `sarld` to link
each selected `*_reloc` preload image against the kernel, then appends its
address/size record. For example, stock `EISABus_reloc` still contains Mach-O
relocation entries and cannot be registered by copying the file unchanged.

### Recovered `sa_rld` contract and memory map

Apple's published
[cctools `mach-o/sarld.h`](https://github.com/apple-oss-distributions/cctools/blob/main/include/mach-o/sarld.h)
confirms the native 11-argument contract: base-file name/address,
object name/address/size, work-memory
address/size pointer, error buffer/address size, and malloc address/length.
Boot v40.13.1 stores the mapped sarld entry at KERNBOOTSTRUCT `+0x164`, uses the
kernel's current end as the work address, and appends each successful
address/size pair at `+0x168` while incrementing `+0x154`.

Chameleon's original BootE occupied roughly `0x20200-0x6b000`, while native
sarld must map `0x30000-0x52000`; the first implementation therefore overwrote
its own executing loader. BootE is now linked at `0x52000`, represented in real
mode as the 64-KiB-aligned pair `0x5000:0x2000`. Reduced data padding and
disabled freestanding unwind metadata keep the last BSS byte at `0x9a784`,
well below both the conventional `0x9fc00` EBDA boundary and the larger CUBX
BIOS workspace. Driver input is
staged at `0x03000000`, the preserved thin kernel at `0x01000000`, and sarld is
called on a private stack below `0x00f00000` with its native 5-6 MiB heap.

The Patch 4 i386 kernel's loadable extent ends at `0x20a000`; its distant
`__LINKEDIT` segment is excluded from the runtime extent but repointed into the
preserved base-file bytes for symbol resolution. QEMU inspection confirms EISA
registration, ATA discovery, the `OPENSTEP_4.2` label, and `hd0a` root
selection. The expanded Socket 370 profile additionally links PCI, chipset,
keyboard, alternate SCSI, VBE, and Matrox records; each new attachment remains
independently testable rather than being inferred from successful linkage.

## Recovered native files

The install floppy contains `System.config/Instance0.table` rather than a
physical `Default.table`; the loader resolves the selected instance through
its fallback rules. Its stock boot set is:

```text
PS2Keyboard EISABus PCIBus PCMCIABus PCIC Intel824X0
```

The table sets `rootdev=cdrom`, enables install mode and driver prompts, and
asks for the Disk/SCSI families. Beta disk 1 supplies a complete EIDE 4.03
bundle with `EIDE_reloc`; beta disk 2 supplies a complete Matrox MGA2064W
bundle with `MatroxMGA2064WDisplayDriver_reloc`.

The extracted evidence under `out/extracted/` is derived output. Regenerate it
with `reopenstep slipstream extract` and `extract-tree`.

The installer and normal-boot tables are independent. Supplying EIDE only in
the El Torito startup image lets installation see the target but does not make
the installed system bootable. EIDE must also appear in the User UFS
`System.config/Default.table`, and the complete EIDE bundle (including
`EIDE_reloc`) must be present in that UFS before mastering. The rescue table
uses the native `rootdev=sd0a` kernel convention while preloading EIDE.

CDIS displays the end-of-stage floppy instruction through the
`REMOVE_FLOPPY` key in `/NextCD/CDIS/English.lproj/Localizable.strings`. Hybrid
El Torito media still take the floppy branch, so ReOpenStep replaces that text
with the ordinary restart instruction. More importantly, CDIS seeds the first
hard-disk startup environment from the boot filesystem: its `Default.table`
must contain EIDE in addition to the install-mode `Instance0.table`.

EIDE bundle selection is itself instance-driven. The beta bundle ships an old
generic `Instance0.table` identifying drvEIDE-16/4.01 even though its relocated
binary is drvEIDE-16.2. On a PIIX4 target the selected instance must be materialized
from `EIDE_PIIX.table`: it identifies PCI device `8086:7111`, enables both IDE
channels and uses the `DualEide` class. Merely listing `EIDE` under “Boot
Drivers" still selects the stale instance and does not detect the disks.

## Boot2 installer prompt bypass

The first language and destructive-install confirmation screens are emitted by
boot2 before the kernel starts; they are not CDIS prompts. Boot1 loads the boot2
region beginning at disk-image offset `0x5000` to physical address zero, so the
boot2 entry stored at image offset `0x8000` executes at runtime `0x3000`.

Runtime tracing and Ghidra analysis place the install-mode function at `0x3558`.
The `Install Mode` and `Really Install?` strings are referenced at runtime
`0x3707` and `0x375c`. After boot2 prepares install mode, this sequence guards
the confirmation block:

```text
0x3753  call 0x7570
0x3758  test ebx,ebx
0x375a  jz   0x37a0
0x375c  mov  [ebp-0xc],0xb939  ; "Really Install?"
...
0x37a0  push 0                 ; "Loading OPENSTEP"
```

On installation media `ebx` is one, so stock boot2 enters the confirmation.
`reopenstep slipstream boot2-autoinstall` changes only the short conditional
jump opcode at image offset `0x875a` from `0x74` (`JZ`) to `0xeb` (`JMP`). The
unchanged displacement still targets `0x37a0`. The command validates the full
surrounding instruction signature and refuses unknown boot2 builds.

Autoboot `System.config` tables independently set `Language` to `English`, so
CDIS and the installed system retain the selected language. Install-mode boot2
nevertheless calls its language menu unconditionally. A second checked patch at
image offset `0x8a93` replaces its six-byte `JZ 0x3b3a` with
`JMP 0x3b44; NOP`, entering the native English-selection path without printing
the language-table error. Driver loading, CDIS disk selection, partitioning and
the later destructive confirmation remain unchanged.

## BootE Rhapsody DR2 DVD mastering

The reproducible DVD mastering lane is:

```sh
make boote-rhapsody-dr2-dvd
```

This builds `out/boote/boote-rhapsody-dr2-dvd.iso` as a BootE no-emulation
HFS/ISO hybrid. The image contains:

- `cdboot`: BootE El Torito loader.
- `mach_kernel`: RDR/i386 `/mach_kernel` extracted from the Titan1U CD through
  `rdrufs`.
- `Payload/rhapsody_dr2_x86.iso`: the original Rhapsody DR2 source ISO payload.

The disc is intended as a kernel-loader and filesystem/installer test vehicle.
It is not yet a complete native RDR installer replacement; the next boundary is
teaching BootE to mount the RDR native UFS directly or to pass a complete root
device/install handoff to the Rhapsody kernel.

`hdiutil makehybrid` emits a no-emulation catalog load count of four 512-byte
virtual sectors. That is the canonical mode for Chameleon's `cdboot`: BIOS
loads the first 2 KiB, then `cdboot` reads the catalog and loads the rest of
its own ISO boot image before jumping to the embedded `boot` payload. For
emulator A/B testing, set `BOOTE_NOEMUL_LOAD_MODE=full` to patch the catalog to
the full `cdboot` virtual-sector count.

BootE/Chameleon also pauses if only the legacy
`/Extra/com.apple.Boot.plist` exists. The Rhapsody DVD script therefore writes
`/Extra/org.chameleon.Boot.plist` directly.

Until that Rhapsody-specific BootE ABI is recovered, the native boot fallback is:

```sh
make rhapsody-dr2-native-floppy-dvd
```

This image uses a real 2.88 MB El Torito floppy-emulation boot image. The first
1.44 MB is the stock Rhapsody DR2 installation floppy and the second 1.44 MB is
the stock Rhapsody DR2 driver disk. That matches the OPENSTEP 2.88 MB
BIOS-facing path and avoids presenting 86Box with a short floppy-emulation boot
image. The enclosing ISO front label points at the extracted native RDR UFS
payload. It reaches the stock Rhapsody `boot:` prompt in QEMU and is the better
86Box target for native loader testing.

The reusable primitive is:

```sh
./reopenstep floppy combine-2880 \
  --install path/to/install.img \
  --drivers path/to/driver.img \
  --output out/rhapsody-dr2/install-driver-2880.img
```

If the installer still asks for the driver diskette, the remaining boundary is
inside the Rhapsody boot2/installer driver-media path: the second 1.44 MB is
present in the emulated 2.88 MB image, but stock Rhapsody code may still reread
the floppy label at sector 15 and expect an actual disk swap. That case requires
patching the driver-media lookup rather than further ISO catalog changes.
