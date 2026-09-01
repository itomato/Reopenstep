#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
media_dir="$project_dir/vault/Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)"
mode=${1:-install}
shift 2>/dev/null || true

source_iso=${RHAPSODY_DR2_ISO:-$media_dir/rhapsody_dr2_x86.iso}
install_floppy=${RHAPSODY_DR2_INSTALL_FLOPPY:-$media_dir/Boot floppy/rhapsody_dr2_x86_InstallationFloppy.img}
driver_floppy=${RHAPSODY_DR2_DRIVER_FLOPPY:-$media_dir/Boot floppy/rhapsody_dr2_x86_DriverDisk.img}
source_tree_iso=${RHAPSODY_GLIDE_SOURCE_ISO:-$project_dir/out/glide/rhapsody-glide-source.iso}
disk=${RHAPSODY_86BOX_DISK:-$project_dir/out/86box-rhapsody-dr2.vhd}
config=${RHAPSODY_86BOX_CONFIG:-$project_dir/out/86box-rhapsody-dr2.cfg}
template=${RHAPSODY_86BOX_TEMPLATE:-$project_dir/emulation/86box/rhapsody-dr2-voodoo2.template.cfg}
memory_kb=${RHAPSODY_86BOX_MEMORY_KB:-131072}

case "$mode" in
    install) iso=$source_iso; floppy=$install_floppy ;;
    drivers) iso=$source_iso; floppy=$driver_floppy ;;
    source) iso=$source_tree_iso; floppy= ;;
    disk) iso=; floppy= ;;
    *)
        echo "usage: $0 [install|drivers|source|disk] [86Box arguments...]" >&2
        exit 2
        ;;
esac

if test -n "${RHAPSODY_86BOX_BINARY:-}"; then
    emulator=$RHAPSODY_86BOX_BINARY
elif command -v 86Box >/dev/null 2>&1; then
    emulator=86Box
elif test -x /Applications/86Box.app/Contents/MacOS/86Box; then
    emulator=/Applications/86Box.app/Contents/MacOS/86Box
else
    echo "86Box is required (or set RHAPSODY_86BOX_BINARY)" >&2
    exit 1
fi

for path in "$template" ${iso:+"$iso"} ${floppy:+"$floppy"}; do
    if ! test -f "$path"; then
        echo "required Rhapsody/86Box input not found: $path" >&2
        exit 1
    fi
done

if ! test -e "$disk"; then
    qemu-img create -f vpc "$disk" 2113413120
fi

mkdir -p "$(dirname -- "$config")"
awk -v disk="$disk" -v iso="$iso" -v floppy="$floppy" -v memory="$memory_kb" '
    function replace(value, token, replacement, position) {
        while ((position = index(value, token)) != 0)
            value = substr(value, 1, position - 1) replacement substr(value, position + length(token))
        return value
    }
    {
        line = replace($0, "@DISK_PATH@", disk)
        line = replace(line, "@ISO_PATH@", iso)
        line = replace(line, "@FLOPPY_PATH@", floppy)
        print replace(line, "@MEMORY_KB@", memory)
    }
' "$template" > "$config"

echo "Mode:    $mode"
echo "Disk:    $disk"
echo "CD-ROM:  ${iso:-<ejected>}"
echo "Floppy:  ${floppy:-<ejected>}"
echo "Config:  $config"
echo "Voodoo2: enabled (86Box type 2)"
if test "${RHAPSODY_86BOX_DRY_RUN:-0}" = 1; then
    exit 0
fi
exec "$emulator" -C "$config" "$@"
