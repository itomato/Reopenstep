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
    *)
        echo "usage: $0 [install|rescue|disk] [86Box arguments...]" >&2
        exit 2
        ;;
esac
shift 2>/dev/null || true

iso=${REOPENSTEP_86BOX_ISO:-$default_iso}
disk=${REOPENSTEP_86BOX_DISK:-$project_dir/out/86box-openstep-dev-v6.vhd}
config=${REOPENSTEP_86BOX_CONFIG:-$project_dir/out/86box-autoboot.cfg}
if test "$storage" = buslogic; then
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
if ! test -e "$disk"; then
    if ! command -v "$qemu_img" >/dev/null 2>&1; then
        echo "qemu-img is required to create $disk" >&2
        exit 1
    fi
    mkdir -p "$(dirname -- "$disk")"
    "$qemu_img" create -f vpc "$disk" 2113413120
fi
if ! test -f "$disk"; then
    echo "disk path is not a regular file: $disk" >&2
    exit 1
fi

mkdir -p "$(dirname -- "$config")"
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

exec "$emulator" -C "$config" "$@"
