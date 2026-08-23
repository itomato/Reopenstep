#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
source_dir="$project/tools/chameleon/src"
profile=${BOOTE_CONFIG:-$here/config/minimal.toml}
mode=${1:-build}

case "$mode" in
    build|prepare) ;;
    *) echo "usage: $0 [build|prepare]" >&2; exit 2 ;;
esac

REOPENSTEP_CHAMELEON_PREPARE_ONLY=1 "$project/tools/chameleon/bootstrap.sh"
python3 "$here/generate_config.py" --profile "$profile" --output-dir "$source_dir"

if test "$mode" = prepare; then
    echo "BootE source and static configuration prepared at $source_dir"
    exit 0
fi

if ! command -v nasm >/dev/null 2>&1; then
    echo "BootE requires NASM for its BIOS and El Torito entry stages" >&2
    exit 3
fi

if test "${BOOTE_INCREMENTAL:-0}" != 1; then
    make -C "$source_dir" -f Makefile clean
fi
make -C "$source_dir" -f Makefile

output="$project/out/boote"
mkdir -p "$output"
for product in boot cdboot; do
    source_product="$source_dir/sym/i386/$product"
    if ! test -f "$source_product"; then
        echo "expected BootE product was not built: $source_product" >&2
        exit 1
    fi
    cp "$source_product" "$output/boote-$product"
done

echo "BootE products:"
ls -l "$output/boote-boot" "$output/boote-cdboot"
shasum -a 256 "$output/boote-boot" "$output/boote-cdboot"
