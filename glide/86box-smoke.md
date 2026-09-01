# Rhapsody DR2 86Box smoke boundary

The checked-in `rhapsody-dr2-voodoo2.template.cfg` was verified with 86Box 5.0
build 7600 on 2026-08-31.  A fresh sparse VHD booted the stock Rhapsody DR2
installation floppy and reached the language-selection prompt.

The Rhapsody PCI probe reported:

```text
Found PCI 2.0 device: ID=0x0002121a at Dev=12 Func=0 Bus=0
```

That independently confirms the driver table's i386 `Auto Detect IDs` value
and that 86Box exposes the Voodoo2 early enough for DriverKit probing.  An
explicit add-in `fdc_at` initially caused BIOS floppy error 40; the verified
profile correctly relies on the AM-BX133 motherboard's onboard controller.

Current reproducible boundary:

1. `scripts/run-rhapsody-dr2-86box.sh install`
2. Select language 1 and complete the stock installation.
3. Relaunch with `drivers` when the installer requests its driver floppy.
4. Build `make glide-rhapsody-glide-source` followed by
   `make glide-rhapsody-source-iso`, then relaunch with `source`.
5. Copy the source tree to a writable guest directory and run
   `glide/rhapsody/build-on-dr2.sh`.

The native `kl_ld` result remains the next required proof.  Host-side MIG and
Objective-C validation cannot establish that the DR2 linker accepts the final
load-command section or that DriverKit maps the Voodoo2 BAR correctly.
