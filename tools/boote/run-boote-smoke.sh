#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
iso="$project/out/boote/boote-smoke.iso"
disk=${1:-}

if ! command -v qemu-system-i386 >/dev/null 2>&1; then
    echo "BootE smoke testing requires qemu-system-i386" >&2
    exit 3
fi
if ! test -f "$iso"; then
    "$here/make-boote-iso.sh"
fi

if test -n "$disk"; then
    if ! test -f "$disk"; then
        echo "BootE disk does not exist: $disk" >&2
        exit 2
    fi
    case "$disk" in
        *.vhd|*.VHD) format=vpc ;;
        *.qcow2|*.QCOW2) format=qcow2 ;;
        *) format=raw ;;
    esac
    exec qemu-system-i386 -machine pc -cpu pentium3 -m 512 -boot d -snapshot \
        -drive "file=$disk,if=ide,index=0,media=disk,format=$format" \
        -drive "file=$iso,if=ide,index=2,media=cdrom,readonly=on" \
        -no-reboot
fi

exec qemu-system-i386 -machine pc -cpu pentium3 -m 512 -boot d \
    -drive "file=$iso,if=ide,index=2,media=cdrom,readonly=on" \
    -no-reboot
