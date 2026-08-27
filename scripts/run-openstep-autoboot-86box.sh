#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

storage=${REOPENSTEP_86BOX_STORAGE:-eide}
case "$storage" in
    eide|buslogic) ;;
    *)
        echo "REOPENSTEP_86BOX_STORAGE must be eide or buslogic" >&2
        exit 2
        ;;
esac

mode=${1:-install}
create_disk=yes
case "$mode" in
    install)
        if test "$storage" = buslogic; then
            default_iso=$project_dir/out/reopenstep-4.2-buslogic.iso
        else
            default_iso=$project_dir/out/reopenstep-4.2-eide-developer-v6.iso
        fi
        ;;
    rescue)
        if test "$storage" = buslogic; then
            default_iso=$project_dir/out/reopenstep-4.2-buslogic-rescue.iso
        else
            default_iso=$project_dir/out/reopenstep-4.2-eide-rescue-piix.iso
        fi
        ;;
    disk) default_iso= ;;
    boote)
        default_iso=$project_dir/out/boote/boote-vesa.iso
        default_disk=$project_dir/out/boote/openstep-user-patch4-vesa.raw
        create_disk=no
        ;;
    *)
        echo "usage: $0 [install|rescue|disk|boote] [86Box arguments...]" >&2
        exit 2
        ;;
esac
shift 2>/dev/null || true

iso=${REOPENSTEP_86BOX_ISO:-$default_iso}
if test "$mode" != boote; then
    default_disk=$project_dir/out/86box-openstep-dev-v6.vhd
fi
disk=${REOPENSTEP_86BOX_DISK:-$default_disk}
if test "$mode" = boote; then
    default_config=$project_dir/out/86box-cubx-boote-vm/86box.cfg
else
    default_config=$project_dir/out/86box-autoboot.cfg
fi
config=${REOPENSTEP_86BOX_CONFIG:-$default_config}
if test "$mode" = boote; then
    default_template=$project_dir/emulation/86box/boote-keyboard-debug.template.cfg
elif test "$storage" = buslogic; then
    default_template=$project_dir/emulation/86box/openstep-buslogic.template.cfg
else
    default_template=$project_dir/emulation/86box/openstep-autoboot.template.cfg
fi
template=${REOPENSTEP_86BOX_TEMPLATE:-$default_template}
memory_kb=${REOPENSTEP_86BOX_MEMORY_KB:-32768}
qemu_img=${REOPENSTEP_86BOX_QEMU_IMG:-qemu-img}

if test -n "${REOPENSTEP_86BOX_BINARY:-}"; then
    emulator=$REOPENSTEP_86BOX_BINARY
elif command -v 86Box >/dev/null 2>&1; then
    emulator=86Box
elif command -v 86box >/dev/null 2>&1; then
    emulator=86box
elif test -x /Applications/86Box.app/Contents/MacOS/86Box; then
    emulator=/Applications/86Box.app/Contents/MacOS/86Box
else
    echo "86Box is required (or set REOPENSTEP_86BOX_BINARY)" >&2
    exit 1
fi

if test -n "$iso" && ! test -f "$iso"; then
    echo "$mode ISO not found: $iso" >&2
    exit 1
fi
if ! test -f "$template"; then
    echo "86Box configuration template not found: $template" >&2
    exit 1
fi

# 63 * 16 * 4095 sectors is just under 2 GiB, matching the geometry in the
# templates and leaving room for User plus all five Developer packages. A
# dynamic VHD keeps the initial host allocation small.
if ! test -e "$disk" && test "$create_disk" = yes; then
    if ! command -v "$qemu_img" >/dev/null 2>&1; then
        echo "qemu-img is required to create $disk" >&2
        exit 1
    fi
    mkdir -p "$(dirname -- "$disk")"
    "$qemu_img" create -f vpc "$disk" 2113413120
fi
if ! test -f "$disk"; then
    echo "$mode disk image not found: $disk" >&2
    exit 1
fi

mkdir -p "$(dirname -- "$config")"
config_dir=$(CDPATH= cd -- "$(dirname -- "$config")" && pwd)
config=$config_dir/$(basename -- "$config")
awk -v disk="$disk" -v iso="$iso" -v memory="$memory_kb" '
    function replace_literal(value, token, replacement, position) {
        while ((position = index(value, token)) != 0)
            value = substr(value, 1, position - 1) replacement substr(value, position + length(token))
        return value
    }
    {
        line = replace_literal($0, "@DISK_PATH@", disk)
        line = replace_literal(line, "@ISO_PATH@", iso)
        print replace_literal(line, "@MEMORY_KB@", memory)
    }
' "$template" > "$config"

echo "Mode:   $mode"
echo "Bus:    $storage"
echo "ISO:    ${iso:-<ejected>}"
echo "HDD:    $disk"
echo "Config: $config"
echo "86Box:  $emulator"
if test "$mode" = boote; then
    echo "Boot:   select CD-ROM first in CUBX BIOS (Delete; sequence CDROM, C, A)"
fi

if test -n "${REOPENSTEP_86BOX_LOG:-}"; then
    mkdir -p "$(dirname -- "$REOPENSTEP_86BOX_LOG")"
    log_dir=$(CDPATH= cd -- "$(dirname -- "$REOPENSTEP_86BOX_LOG")" && pwd)
    log_path=$log_dir/$(basename -- "$REOPENSTEP_86BOX_LOG")
    echo "Log:    $log_path"
    if test "$mode" = boote; then
        exec "$emulator" -L "$log_path" -P "$(dirname -- "$config")" "$@"
    fi
    exec "$emulator" -L "$log_path" -C "$config" "$@"
fi
if test "$mode" = boote; then
    exec "$emulator" -P "$(dirname -- "$config")" "$@"
fi
exec "$emulator" -C "$config" "$@"
