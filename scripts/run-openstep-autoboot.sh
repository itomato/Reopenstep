#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

storage=${REOPENSTEP_QEMU_STORAGE:-eide}
case "$storage" in
    eide|amd-scsi) ;;
    *)
        echo "REOPENSTEP_QEMU_STORAGE must be eide or amd-scsi" >&2
        exit 2
        ;;
esac

mode=${1:-install}
case "$mode" in
    install)
        if test "$storage" = amd-scsi; then
            default_iso=$project_dir/out/reopenstep-4.2-amd-scsi.iso
        else
            default_iso=$project_dir/out/reopenstep-4.2-eide-developer-v6.iso
        fi
        boot_order=d
        ;;
    rescue)
        if test "$storage" = amd-scsi; then
            default_iso=$project_dir/out/reopenstep-4.2-amd-scsi-rescue.iso
        else
            default_iso=$project_dir/out/reopenstep-4.2-eide-rescue-piix.iso
        fi
        boot_order=d
        ;;
    disk)
        default_iso=
        boot_order=c
        ;;
    *)
        echo "usage: $0 [install|rescue|disk] [QEMU arguments...]" >&2
        exit 2
        ;;
esac
shift 2>/dev/null || true

iso=${REOPENSTEP_QEMU_ISO:-$default_iso}
disk=${REOPENSTEP_QEMU_DISK:-$project_dir/out/openstep-autoboot-hdd.raw}
disk_size=${REOPENSTEP_QEMU_DISK_SIZE:-2G}
qemu=${REOPENSTEP_QEMU_BINARY:-qemu-system-i386}
qemu_img=${REOPENSTEP_QEMU_IMG_BINARY:-qemu-img}
gdb_port=${REOPENSTEP_QEMU_GDB_PORT:-}
gdb_wait=${REOPENSTEP_QEMU_GDB_WAIT:-no}
debug_log=${REOPENSTEP_QEMU_DEBUG_LOG:-}

if ! command -v "$qemu" >/dev/null 2>&1; then
    echo "qemu-system-i386 is required (or set REOPENSTEP_QEMU_BINARY)" >&2
    exit 1
fi
if test -n "$iso" && ! test -f "$iso"; then
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

case "$gdb_wait" in yes|no) ;; *) echo "REOPENSTEP_QEMU_GDB_WAIT must be yes or no" >&2; exit 2 ;; esac
if test -n "$gdb_port"; then
    case "$gdb_port" in *[!0-9]*) echo "REOPENSTEP_QEMU_GDB_PORT must be numeric" >&2; exit 2 ;; esac
    set -- "$@" -gdb "tcp::$gdb_port"
    test "$gdb_wait" = yes && set -- "$@" -S
    echo "GDB:  tcp://127.0.0.1:$gdb_port${gdb_wait:+ (wait=$gdb_wait)}"
fi
if test -n "$debug_log"; then
    mkdir -p "$(dirname -- "$debug_log")"
    set -- "$@" -d int,cpu_reset -D "$debug_log"
    echo "QEMU log: $debug_log"
fi

echo "Mode: $mode"
echo "Bus:  $storage"
echo "ISO:  ${iso:-<ejected>}"
echo "HDD:  $disk"
echo "QEMU: $qemu"

# Keep the emulated machine deliberately boring. i440FX/PIIX supplies the PCI
# and dual-channel IDE controller expected by the stock bus drivers; Pentium
# avoids exposing newer CPU features; EIDE sees the HDD as primary master and
# the ATAPI CD-ROM as secondary master. Do not add ide-hd.disable-dma: modern
# QEMU has no such property.
if test "$storage" = amd-scsi && test -n "$iso"; then
    exec "$qemu" \
        -machine pc-i440fx-7.2,accel=tcg,acpi=off,hpet=off \
        -cpu pentium -smp 1 -m 128 -boot "order=$boot_order,menu=on" \
        -device am53c974,id=scsi0 \
        -drive "if=none,id=osdisk,file=$disk,format=raw,cache=writeback" \
        -device scsi-hd,drive=osdisk,bus=scsi0.0,channel=0,scsi-id=0,lun=0 \
        -drive "if=none,id=oscd,file=$iso,format=raw,media=cdrom,readonly=on" \
        -device scsi-cd,drive=oscd,bus=scsi0.0,channel=0,scsi-id=6,lun=0 \
        -vga cirrus -nic none -rtc base=localtime,clock=vm "$@"
elif test "$storage" = amd-scsi; then
    exec "$qemu" \
        -machine pc-i440fx-7.2,accel=tcg,acpi=off,hpet=off \
        -cpu pentium -smp 1 -m 128 -boot "order=$boot_order,menu=on" \
        -device am53c974,id=scsi0 \
        -drive "if=none,id=osdisk,file=$disk,format=raw,cache=writeback" \
        -device scsi-hd,drive=osdisk,bus=scsi0.0,channel=0,scsi-id=0,lun=0 \
        -vga cirrus -nic none -rtc base=localtime,clock=vm "$@"
elif test -n "$iso"; then
    exec "$qemu" \
        -machine pc-i440fx-7.2,accel=tcg,acpi=off,hpet=off \
        -cpu pentium -smp 1 -m 128 -boot "order=$boot_order,menu=on" \
        -drive "if=none,id=osdisk,file=$disk,format=raw,cache=writeback" \
        -device ide-hd,drive=osdisk,bus=ide.0,unit=0 \
        -drive "if=none,id=oscd,file=$iso,format=raw,media=cdrom,readonly=on" \
        -device ide-cd,drive=oscd,bus=ide.1,unit=0 \
        -vga cirrus -nic none -rtc base=localtime,clock=vm "$@"
else
    exec "$qemu" \
        -machine pc-i440fx-7.2,accel=tcg,acpi=off,hpet=off \
        -cpu pentium -smp 1 -m 128 -boot "order=$boot_order,menu=on" \
        -drive "if=none,id=osdisk,file=$disk,format=raw,cache=writeback" \
        -device ide-hd,drive=osdisk,bus=ide.0,unit=0 \
        -vga cirrus -nic none -rtc base=localtime,clock=vm "$@"
fi
