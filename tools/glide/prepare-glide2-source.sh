#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
output=${1:-$project_dir/out/glide/3dfx-glide-1999}
repository=${GLIDE_REPOSITORY:-https://github.com/sezero/glide.git}
commit=0de38e8b22542d636b2796be0411b21c0d038500
license_commit=ee38094805f778566cc752c6d854f058253234de

if test -e "$output"; then
    echo "Refusing to replace existing Glide source: $output" >&2
    exit 1
fi

temporary=$(mktemp -d "${TMPDIR:-/tmp}/reopenstep-glide-source.XXXXXX")
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
git clone --quiet "$repository" "$temporary/repository"
git -C "$temporary/repository" checkout --quiet --detach "$commit"
mkdir -p "$(dirname -- "$output")"
git -C "$temporary/repository" archive --format=tar "$commit" | \
    (mkdir "$output" && tar -xf - -C "$output")
git -C "$temporary/repository" show "$license_commit:LICENSE" > \
    "$output/3DFX_GLIDE_LICENSE.txt"
printf '%s\n' "$commit" > "$output/REOPENSTEP_BASELINE_COMMIT"

echo "Pinned 3dfx Glide source exported to $output"
