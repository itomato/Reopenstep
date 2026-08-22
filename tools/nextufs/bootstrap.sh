#!/bin/sh
set -eu

commit=6ef2908f3d7ef85f593ecb6501e8589ba55c8810
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$here/src"
bin_dir="$here/bin"

if [ ! -d "$source_dir/.git" ]; then
    git clone https://github.com/ostrich/nextufs.git "$source_dir"
fi
git -C "$source_dir" fetch origin "$commit"
git -C "$source_dir" reset --hard "$commit"
git -C "$source_dir" checkout --detach "$commit"
git -C "$source_dir" apply "$here/offline.patch"
mkdir -p "$source_dir/.scratch" "$bin_dir"
make -C "$source_dir" nextufs CFLAGS='-Iinclude -Isrc -O2 -g -std=gnu99 -Wall -Wextra'
cp "$source_dir/nextufs" "$bin_dir/nextufs"
printf '%s\n' "$commit" > "$bin_dir/SOURCE_COMMIT"
