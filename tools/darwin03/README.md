# Darwin 0.3 i386 installer lane

This lane uses `vault/Darwin03.qcow` as the immutable Darwin 0.3/Rhapsody i386
build-root input. Create a writable QCOW2 overlay without changing the vault
image:

```sh
make darwin-installer-image
```

The overlay records an absolute backing-image path and is therefore a local
build artifact. Inspect either image with:

```sh
./reopenstep darwin inspect-installer vault/Darwin03.qcow
./reopenstep darwin inspect-installer out/darwin03/installer-base.qcow2
```

Run the snapshot-only boot assertion with:

```sh
make darwin-installer-test
```

The harness stops boot2's countdown, enters `-s`, and records screenshots,
OCR transcripts, the QEMU command, input identity, and a JSON report under
`out/darwin03/test-runs/`.

Select another QEMU i440FX compatibility contract for DriverKit comparisons:

```sh
python3 tools/darwin03/test-qemu.py --machine pc-i440fx-2.4
```

The verified baseline on QEMU 9.2 is not a root shell yet. Kernel Release 5.3
initializes PCI, ISA/EISA, DriverKit 500, and the emulated IDE disk. PIO reads
report ATA interrupt timeouts, but initialization continues through DriverKit
registration and selects `rootdev 300, howto 40002`. It then terminates with
`ufs_mountroot failed: 19`, `od986a_mountroot failed: 19`, and a no-suitable-
interface panic.

The harness records that root-device boundary as its baseline, then continues
probing for init's `Singleuser boot` and read-only root messages. A report result
of `passed-single-user-root` is the installer acceptance milestone;
`passed-root-device-mount-failure-boundary` means the known root driver or
filesystem binding gap remains.
