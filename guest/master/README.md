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

No host-side ISO file overlay counts as a native installation layer. The final
host step is `./reopenstep image wrap`, which embeds these native outputs in an
El Torito ISO and patches the declared front-porch field.
