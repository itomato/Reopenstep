#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)
output=${1:-$project_dir/out/glide/rhapsody-glide-source.iso}

mkdir -p "$(dirname -- "$output")"
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/rhapsody-glide-iso.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM
temporary=$work_dir/rhapsody-glide-source.iso
staging=$work_dir/RHAPSODY_GLIDE
mkdir "$staging"
cp -R "$project_dir/glide" "$staging/glide"
if test -d "$project_dir/out/glide/3dfx-glide-1999"; then
    cp -R "$project_dir/out/glide/3dfx-glide-1999" \
        "$staging/3dfx-glide-1999"
fi
hdiutil makehybrid -iso -joliet -default-volume-name RHAPSODY_GLIDE \
    -o "$temporary" "$staging"
mv -f "$temporary" "$output"
echo "Rhapsody Glide source ISO: $output"
shasum -a 256 "$output"
