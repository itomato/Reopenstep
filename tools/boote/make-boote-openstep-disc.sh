#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
output=${1:-$project/out/boote/boote-openstep-patch4.iso}
default_ufs="$project/out/boote/openstep-user-patch4-beta-eide-cd.ufs"
ufs=${2:-$default_ufs}
secondary=${3:-${BOOTE_SECONDARY_UFS:-}}
disc_config=${BOOTE_DISC_CONFIG:-$here/config/disc.toml}
boot_mode=${BOOTE_BOOT_MODE:-no-emulation}
base_ufs="$project/out/mastered/user-base/OPENSTEP42CD.UFS"
label="$project/out/mastered/user-base/NEXT_LABEL.bin"
patched_ufs="$project/out/boote/openstep-user-patch4-cd.ufs"

if ! test -f "$base_ufs" || ! test -f "$label"; then
    mkdir -p "$(dirname -- "$base_ufs")"
    "$project/reopenstep" image extract-ufs \
        --source "$project/vault/OpenStep-4.2-User.iso" \
        --ufs-output "$base_ufs" --label-output "$label"
fi

if ! test -f "$patched_ufs"; then
    "$project/reopenstep" patch4 overlay "$project/vault/OS42MachUserPatch4.tar" \
        --image "$base_ufs" --output "$patched_ufs"
fi

if test "$ufs" = "$default_ufs" && ! test -f "$ufs"; then
    "$project/reopenstep" slipstream drivers \
        --source "$project/4.2_Beta_Drivers_1.floppyimage" \
        --source-root /private/Drivers/i386/EIDE.config \
        --startup "$patched_ufs" \
        --startup-root /private/Drivers/i386/EIDE.config \
        --output "$ufs"
elif ! test -f "$ufs"; then
    echo "BootE UFS payload not found: $ufs" >&2
    exit 2
fi

BOOTE_CONFIG="$disc_config" "$here/build-boote.sh" build

boot_image="$project/out/boote/boote-cdboot"
if test "$boot_mode" = "floppy"; then
    # El Torito type-3 media must be a real 2.88 MB floppy image.  BootE only
    # occupies the beginning; its CD reader then locates the UFS payload on
    # the enclosing ISO.  Padding keeps BIOSes (especially 86Box) from
    # rejecting a short emulation image.
    boot_image="$project/out/boote/boote-cdboot-2880.img"
    cp "$project/out/boote/boote-cdboot" "$boot_image"
    truncate -s 2949120 "$boot_image"
elif test "$boot_mode" != "no-emulation"; then
    echo "unsupported BOOTE_BOOT_MODE: $boot_mode (use floppy or no-emulation)" >&2
    exit 2
fi

if test -n "$secondary"; then
    "$project/reopenstep" image wrap --boot-mode "$boot_mode" \
        --ufs "$ufs" --secondary-ufs "$secondary" \
        --boot-image "$boot_image" \
        --label-template "$label" --label-offset 112 --label-format u16be \
        --volume BOOTE_OPENSTEP --output "$output"
else
    "$project/reopenstep" image wrap --boot-mode "$boot_mode" \
        --ufs "$ufs" --boot-image "$boot_image" \
        --label-template "$label" --label-offset 112 --label-format u16be \
        --volume BOOTE_OPENSTEP --output "$output"
fi

echo "BootE OPENSTEP kernel/install disc: $output"
