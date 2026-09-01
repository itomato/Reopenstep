# Glide2.framework reconstruction

This directory is the Rhapsody/i386 overlay for the separately licensed 3dfx
Glide 2 CVG (Voodoo2) source. It does not contain or redistribute that source.

The baseline is the first public 3dfx SourceForge import, mirrored by
`https://github.com/sezero/glide.git` at commit
`0de38e8b22542d636b2796be0411b21c0d038500` (1999-12-07). That snapshot is
contemporaneous with Omni's 2.54 framework. Run
`make glide-rhapsody-glide-source` to export the pinned tree and a copy of the
3DFX GLIDE Source Code General Public License into
`out/glide/3dfx-glide-1999`.

`macosxglide.m` replaces 3dfx's direct PCI library. It connects to the
reconstructed `Voodoo2Server`, forwards aligned PCI configuration transactions,
maps BAR 0 into the client task, and exposes Glide settings through
`NSUserDefaults`. The function boundary and error behavior are derived from
the exported PPC symbols and disassembly; no Omni source was available.

Build this component inside Rhapsody DR2 after the kernel driver and V2Server:

```
make -C Glide2.framework SOURCE_ROOT=/path/to/3dfx-glide-1999
```

The Makefile selects the C triangle setup used by Omni, generates 3dfx's
`fxinline.h`, builds an i386 dynamic framework with version 2.54, and stages it
under `build/Glide2.framework`. It still must be exercised in the guest compiler.
