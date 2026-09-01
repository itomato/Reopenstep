# Glide reverse-engineering tools

`disassemble_ppc.py` reads the 32-bit big-endian Mach-O text section, obtains
function boundaries from `nm`, and disassembles selected functions with
Capstone.  It is useful on the original Rhapsody PPC binaries even when the
host Ghidra installation has no native decompiler for its architecture.

Example:

```sh
python3 tools/glide/disassemble_ppc.py \
  --match 'V2Driver_server|__XReadConfigLong' \
  out/glide/omni-reference/root/private/Drivers/ppc/Voodoo2.config/Voodoo2_reloc
```

Capstone is optional and is not vendored.  Install its Python package into a
virtual environment before running the script.
