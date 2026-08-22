#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

iso=${REOPENSTEP_86BOX_ISO:-$project_dir/out/reopenstep-4.2-eide-persistent.iso}
disk=${REOPENSTEP_86BOX_DISK:-$project_dir/out/86box-openstep.vhd}
config=${REOPENSTEP_86BOX_CONFIG:-$project_dir/out/86box-autoboot.cfg}
template=${REOPENSTEP_86BOX_TEMPLATE:-$project_dir/emulation/86box/openstep-autoboot.template.cfg}
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

if ! test -f "$iso"; then
    echo "installer ISO not found: $iso" >&2
    exit 1
fi
if ! test -f "$template"; then
    echo "86Box configuration template not found: $template" >&2
    exit 1
fi

# 63 * 16 * 1024 sectors is 504 MiB, exactly matching the geometry in the
# template. A dynamic VHD keeps the initial host allocation small.
if ! test -e "$disk"; then
    if ! command -v "$qemu_img" >/dev/null 2>&1; then
        echo "qemu-img is required to create $disk" >&2
        exit 1
    fi
    mkdir -p "$(dirname -- "$disk")"
    "$qemu_img" create -f vpc "$disk" 504M
fi
if ! test -f "$disk"; then
    echo "disk path is not a regular file: $disk" >&2
    exit 1
fi

mkdir -p "$(dirname -- "$config")"
awk -v disk="$disk" -v iso="$iso" -v memory="$memory_kb" '
    { gsub(/@DISK_PATH@/, disk); gsub(/@ISO_PATH@/, iso); gsub(/@MEMORY_KB@/, memory); print }
' "$template" > "$config"

echo "ISO:    $iso"
echo "HDD:    $disk"
echo "Config: $config"
echo "86Box:  $emulator"

exec "$emulator" -C "$config" "$@"
