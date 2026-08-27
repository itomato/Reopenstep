#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
output=${1:-$project/out/boote/boote-xnu-ufs-vesa.iso}
xnu_ufs=${XNU_UFS:-}
installer_ufs=${INSTALLER_UFS:-$project/out/boote/openstep-user-patch4-beta-eide-cd.ufs}
label="$project/out/mastered/user-base/NEXT_LABEL.bin"
boot_mode=${BOOTE_BOOT_MODE:-no-emulation}
root_kind=${BOOTE_ROOT_KIND:-rhapsodios}

if test -z "$xnu_ufs"; then
    echo "XNU_UFS is required: no XNU/Rhapsody UFS root is present in vault or out/" >&2
    echo "Example: XNU_UFS=path/to/xnu-root.ufs $0" >&2
    exit 2
fi
if ! test -f "$xnu_ufs"; then
    echo "XNU UFS root not found: $xnu_ufs" >&2
    exit 2
fi
if ! test -f "$installer_ufs"; then
    echo "Installer UFS not found: $installer_ufs" >&2
    echo "Build it with: tools/boote/make-boote-openstep-disc.sh" >&2
    exit 2
fi
if ! test -f "$label"; then
    echo "NeXT label template not found: $label" >&2
    exit 2
fi

BOOTE_CONFIG="$here/config/xnu-ufs-vesa.toml" "$here/build-boote.sh" build
boot_image="$project/out/boote/boote-cdboot"
if test "$boot_mode" = "floppy"; then
    boot_image="$project/out/boote/boote-cdboot-2880.img"
    cp "$project/out/boote/boote-cdboot" "$boot_image"
    truncate -s 2949120 "$boot_image"
elif test "$boot_mode" != "no-emulation"; then
    echo "unsupported BOOTE_BOOT_MODE: $boot_mode (use floppy or no-emulation)" >&2
    exit 2
fi

"$project/reopenstep" image wrap --boot-mode "$boot_mode" \
    --ufs "$xnu_ufs" --secondary-ufs "$installer_ufs" \
    --root-kind "$root_kind" \
    --boot-image "$boot_image" --label-template "$label" \
    --label-offset 112 --label-format u16be \
    --volume BOOTE_XNU_UFS --output "$output"

echo "BootE XNU/UFS/VESA image: $output"
echo "root kind:     $root_kind"
echo "root UFS:      $xnu_ufs"
echo "installer UFS: $installer_ufs (NeXT partition b)"
