#!/bin/sh
set -eu

commit=2c0e668102c24b299791c192baf6d5fd0646f439
ufs_commit=411f916
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$here/src"

if [ ! -d "$source_dir/.git" ]; then
    git clone https://github.com/itomato/Chameleon.git "$source_dir"
fi
git -C "$source_dir" fetch origin "$commit"
git -C "$source_dir" reset --hard "$commit"
git -C "$source_dir" checkout "$ufs_commit^" -- i386/libsaio/ufs.c i386/libsaio/ufs_byteorder.c i386/libsaio/Makefile

# The fork retains Apple's UFS reader as disabled compatibility code. Enable
# it and link it into libsaio for the OpenStep UFS experiment.
sed -i.bak 's/^#if 0$/#if 1/' "$source_dir/i386/libsaio/ufs.c" "$source_dir/i386/libsaio/ufs_byteorder.c"
sed -i.bak 's/^#define UFS_SUPPORT 0$/#define UFS_SUPPORT 1/' "$source_dir/i386/libsaio/disk.c"
rm -f "$source_dir/i386/libsaio/ufs.c.bak" "$source_dir/i386/libsaio/ufs_byteorder.c.bak" "$source_dir/i386/libsaio/disk.c.bak"

# Chameleon's 2009 warning policy treats every warning as fatal. Modern
# Clang diagnoses several harmless legacy constructs, so keep the warnings
# but make them non-fatal for this reproducibility build.
sed -i.bak 's/ -Werror//g' "$source_dir/Make.rules"
rm -f "$source_dir/Make.rules.bak"

make -C "$source_dir" -f Makefile
printf '%s\n' "$commit" > "$here/SOURCE_COMMIT"
