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
