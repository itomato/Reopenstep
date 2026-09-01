# Glide on Rhapsody x86

This directory contains a source reconstruction of Omni Group's Voodoo2
DriverKit shim.  The immediate target is Rhapsody DR2/i386 under 86Box;
OPENSTEP 4.2/i386 is the follow-on target.

The original PPC package is not copied into this tree.  Prepare an indexed
reference copy with:

```sh
make glide-reference
make glide-dr2-reference
make glide-validate
make glide-rhapsody-glide-source
make glide-rhapsody-source-iso
```

`rhapsody/Voodoo2.lksproj` reconstructs the small kernel-loadable component.
It intentionally uses the DR2 `IODirectDevice (IOPCIDirectDevice)` API instead
of the PPC driver's configuration delegate.  The following behavior has been
confirmed from symbols and PPC instruction-level analysis:

- match PCI vendor/device `121a:0002` (3Dfx Voodoo2) through DR2's
  `Auto Detect IDs` format (`0x0002121a`);
- support at most two boards;
- enable PCI memory-space decoding in command register 0x04;
- export five kernel MIG calls beginning at message ID 67000;
- expose the device-description port to the post-load server.

The RPC argument layouts in `V2Driver.defs` are reconstructed from the PPC
server stubs, including request/reply sizes and each generated call site.  The
64-word config snapshot and the two diagnostic routines still need behavioral
validation in a running guest.
The user-space `V2Server` protocol (message IDs 67100-67103), exclusive mapping,
and owner-death cleanup are reconstructed in `V2Server.tproj`. Automatic
hardware reset on client death remains deferred until the first native run.

`rhapsody/Glide2.framework` supplies the reconstructed i386 PCI/MIG and
NSUserDefaults platform layer. Its Makefile consumes the separately licensed,
pinned 1999 3dfx CVG source exported by `glide-rhapsody-glide-source`; that
source and its license are placed in `out/`, not vendored into this repository.

Build this project inside a DR2 development installation, where
`/System/Developer/Makefiles/pb_makefiles` and `/usr/bin/kl_ld` exist:

```sh
cd glide/rhapsody/Voodoo2.lksproj
make clean all
```

The expected kernel product is `Voodoo2_reloc`. Copy it alongside
`Default.table` and `V2Server` into
`/private/Drivers/i386/Voodoo2.config`, then load it with `driverLoader`.

Do not test with a guest disk that matters yet.  PCI BAR mapping and the
reset-on-client-death path must be proven before running Glide rendering.

The 86Box lane uses the original installation/driver floppies and CD while
presenting a Voodoo2 from first boot:

```sh
scripts/run-rhapsody-dr2-86box.sh install
scripts/run-rhapsody-dr2-86box.sh drivers  # when the installer requests it
make glide-rhapsody-glide-source
make glide-rhapsody-source-iso
scripts/run-rhapsody-dr2-86box.sh source
```

The observed boot boundary and PCI probe are recorded in `86box-smoke.md`.
