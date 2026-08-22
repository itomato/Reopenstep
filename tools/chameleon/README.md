# Chameleon UFS bridge

The pinned `itomato/Chameleon` fork contains the historical Apple UFS reader
interfaces, but the reader was removed/disabled from the normal build. The
bootstrap script restores the UFS implementation from its immediate pre-removal
commit, enables `UFS_SUPPORT`, and builds the i386 loader.

This is an experimental Darwin-family bridge, not an OpenStep kernel driver.
Chameleon can load a Darwin/Rhapsody kernel and UFS files once this reader is
compiled into `libsaio`; it does not make the OpenStep installer’s own driver
floppies unnecessary unless the Darwin kernel has the required hardware
drivers.

```sh
tools/chameleon/bootstrap.sh
```

On current macOS the historical build may stop while linking its 32-bit
configuration helper because Apple no longer ships i386 `libSystem`/ncurses.
That is a host-toolchain limitation, not a UFS-source failure; run the build
on a 32-bit Darwin SDK (or cross-build in the legacy builder) to obtain the
`boot`/`cdboot` binaries. The bootstrap still leaves a reproducibly patched
source tree and records the pinned commit.

The source and build products are ignored. The recorded source commit is kept
in `SOURCE_COMMIT` for reproducibility.
