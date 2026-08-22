#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

iso=${REOPENSTEP_QEMU_ISO:-$project_dir/out/reopenstep-4.2-eide-autoboot.iso}
disk=${REOPENSTEP_QEMU_DISK:-$project_dir/out/openstep-autoboot-hdd.raw}
disk_size=${REOPENSTEP_QEMU_DISK_SIZE:-2G}
qemu=${REOPENSTEP_QEMU_BINARY:-qemu-system-i386}
qemu_img=${REOPENSTEP_QEMU_IMG_BINARY:-qemu-img}

if ! command -v "$qemu" >/dev/null 2>&1; then
    echo "qemu-system-i386 is required (or set REOPENSTEP_QEMU_BINARY)" >&2
    exit 1
fi
if ! test -f "$iso"; then
    echo "boot ISO not found: $iso" >&2
    exit 1
fi

if ! test -e "$disk"; then
    if ! command -v "$qemu_img" >/dev/null 2>&1; then
        echo "qemu-img is required to create $disk" >&2
        exit 1
    fi
    mkdir -p "$(dirname -- "$disk")"
    "$qemu_img" create -f raw "$disk" "$disk_size"
fi
if ! test -f "$disk"; then
    echo "disk path is not a regular file: $disk" >&2
    exit 1
fi

echo "ISO:  $iso"
echo "HDD:  $disk"
echo "QEMU: $qemu"

# Keep the emulated machine deliberately boring. i440FX/PIIX supplies the PCI
# and dual-channel IDE controller expected by the stock bus drivers; Pentium
# avoids exposing newer CPU features; EIDE sees the HDD as primary master and
# the ATAPI CD-ROM as secondary master. Do not add ide-hd.disable-dma: modern
# QEMU has no such property.
exec "$qemu" \
    -machine pc-i440fx-7.2,accel=tcg,acpi=off,hpet=off \
    -cpu pentium \
    -smp 1 \
    -m 128 \
    -boot order=d,menu=on \
    -drive "if=none,id=osdisk,file=$disk,format=raw,cache=writeback" \
    -device ide-hd,drive=osdisk,bus=ide.0,unit=0 \
    -drive "if=none,id=oscd,file=$iso,format=raw,media=cdrom,readonly=on" \
    -device ide-cd,drive=oscd,bus=ide.1,unit=0 \
    -vga cirrus \
    -nic none \
    -rtc base=localtime,clock=vm \
    "$@"
