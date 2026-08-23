# Chameleon UFS bridge

The pinned `itomato/Chameleon` fork contains the historical Apple UFS reader
interfaces, but the reader was removed/disabled from the normal build. The
bootstrap script restores the UFS implementation from its immediate pre-removal
commit, enables `UFS_SUPPORT`, applies the ReopenStep NeXT-label scanner, and
builds the i386 loader.

The scanner accepts both native whole-disk `dlV3` layouts and MBR type `0xA7`
containers. It validates the label copy/checksum, resolves the selected root
partition's 24-bit base, and gives Chameleon's endian-aware UFS reader the
resulting 512-byte sector offset. Validate that parser on the host with:

```sh
tools/chameleon/test-nextlabel.sh
```

This is an experimental Darwin-family bridge, not an OpenStep kernel driver.
Chameleon can load a Darwin/Rhapsody kernel and UFS files once this reader is
compiled into `libsaio`; it does not make the OpenStep installer’s own driver
floppies unnecessary unless the Darwin kernel has the required hardware
drivers.

```sh
tools/chameleon/bootstrap.sh
```

To reproduce only the patched source tree:

```sh
REOPENSTEP_CHAMELEON_PREPARE_ONLY=1 tools/chameleon/bootstrap.sh
```

For a current macOS build, use BootE's static configuration wrapper. It skips
the obsolete 32-bit curses helper, builds host utilities natively, and retains
freestanding i386 output:

```sh
tools/boote/build-boote.sh build
```

The resulting `out/boote/boote-boot` and `out/boote/boote-cdboot` contain the
NeXT-label scanner and restored UFS reader. They still use Chameleon's Darwin
kernel handoff; OPENSTEP boot-argument and DriverKit-table handoff is the next
implementation boundary.

The source and build products are ignored. The recorded source commit is kept
in `SOURCE_COMMIT` for reproducibility.
