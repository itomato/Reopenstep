# Native mastering stage

The host creates `mastering-recipe.json` with `./reopenstep image recipe`. The
recipe and vault media are exposed read-only to a disposable OPENSTEP 4.2 QEMU
guest; only the `mastered/` output share is writable.

The native stage must perform these operations in order:

1. Verify input sizes and SHA-256 values before mounting media.
2. Clone the User CD UFS payload to a writable mastering disk.
3. Add Developer packages without discarding their `.info`, BOM, sizes, or
   lifecycle scripts.
4. Apply Patch 4 once. Abort if its BOM is already present.
5. Copy the declared boot drivers into the 2.88 MB startup filesystem and the
   declared installed drivers into `/private/Drivers/i386` in the target root.
6. Rebuild package BOMs and run native filesystem checking.
7. Export `OPENSTEP42CD.UFS`, `OPENSTEP_BOOT_288.img`, the original 7680-byte
   label template, and `native-report.plist` to the paths in the recipe.

## User + Developer BOM mastering

The Developer CD is an installed filesystem overlay. Its package receipts have
`.info`, `.bom`, and `.sizes` files, but no `.tar.Z` payload: the files named by
each BOM already live at their final paths in the Developer UFS. Do not treat
those receipts as archive packages.

With writable User media mounted at `/master/user`, the Developer UFS mounted
read-only at `/master/developer`, and an empty staging filesystem at
`/master/staging`, run inside OPENSTEP as root:

```sh
guest/master/master-developer-overlay.sh \
  /master/developer /master/user /master/staging /master/state
```

The default package order is `DeveloperTools`, `DeveloperLibs`,
`DeveloperDoc`, `GNUSource`, then `ProfileLibs`; the recipe records the same
order as `layers.packages_native_overlay`. Pass explicit package names after
the four roots to select a subset.

`install-overlay-packages.sh` uses each receipt BOM to copy only that package
from the Developer root, copies the complete receipt (including lifecycle
scripts), and records paths that already existed in the User root. It does not
execute the receipt scripts: this source is the already-installed Developer
filesystem and the script effects are represented by its BOM-selected state.

`rebuild-base-bom.sh` first reconstructs the installable User tree through the
old `BaseSystem.bom`, adds the selected package BOMs and receipts, and adds the
complete installed-driver directory. It then uses native `mkbom` to replace
`/usr/lib/NextStep/BaseSystem.bom`. This staging step is mandatory: running
`mkbom` directly over the installation-media root would add `/NextCD` and
other CD-only files to every installed system.

The original aggregate BOM is retained as `BaseSystem.bom.pre-reopenstep`.
The state directory contains package order, a pre-existing-path/collision
report, and `native-report.plist` with old/new BOM checksums and included
trees. Run `fsck` on the unmounted mastered UFS before export.

No host-side ISO file overlay counts as a native installation layer. The final
host step is `./reopenstep image wrap`, which embeds these native outputs in an
El Torito ISO and patches the declared front-porch field.
