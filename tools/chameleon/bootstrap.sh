#!/bin/sh
set -eu

commit=2c0e668102c24b299791c192baf6d5fd0646f439
ufs_commit=411f916
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$here/src"

if [ ! -d "$source_dir/.git" ]; then
    git clone https://github.com/itomato/Chameleon.git "$source_dir"
fi
if ! git -C "$source_dir" cat-file -e "$commit^{commit}" 2>/dev/null; then
    git -C "$source_dir" fetch origin "$commit"
fi
git -C "$source_dir" reset --hard "$commit"
git -C "$source_dir" checkout "$ufs_commit^" -- i386/libsaio/ufs.c i386/libsaio/ufs_byteorder.c

# The fork retains Apple's UFS reader as disabled compatibility code. Enable
# it and link it into libsaio for the OpenStep UFS experiment.
sed -i.bak 's/^#if 0$/#if 1/' "$source_dir/i386/libsaio/ufs.c" "$source_dir/i386/libsaio/ufs_byteorder.c"
rm -f "$source_dir/i386/libsaio/ufs.c.bak" "$source_dir/i386/libsaio/ufs_byteorder.c.bak"

# Add NeXT dlV3 root-slice discovery (both whole-disk labels and MBR 0xA7)
# and relax the obsolete warning-as-error policy.
python3 "$here/patch_source.py" "$source_dir"

printf '%s\n' "$commit" > "$here/SOURCE_COMMIT"
if test "${REOPENSTEP_CHAMELEON_PREPARE_ONLY:-0}" = 1; then
    printf '%s\n' "prepared Chameleon source at $source_dir"
    exit 0
fi

make -C "$source_dir" -f Makefile
