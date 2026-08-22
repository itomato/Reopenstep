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
