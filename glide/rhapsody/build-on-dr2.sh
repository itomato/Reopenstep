#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_dir=${1:-$project_dir/build}
kernel_project=$project_dir/Voodoo2.lksproj
server_project=$project_dir/V2Server.tproj
framework_project=$project_dir/Glide2.framework
glide_source=${GLIDE2_SOURCE_ROOT:-$project_dir/../../3dfx-glide-1999}

mkdir -p "$build_dir"
make -C "$kernel_project" clean all
make -C "$server_project" clean all
if test -f "$glide_source/REOPENSTEP_BASELINE_COMMIT"; then
    make -C "$framework_project" clean all SOURCE_ROOT="$glide_source"
fi

kernel=$(find "$kernel_project" "$build_dir" -name Voodoo2_reloc -type f -print | head -n 1)
server=$(find "$server_project" "$build_dir" -name V2Server -type f -print | head -n 1)
if test -z "$kernel" || test -z "$server"; then
    echo "Project Builder products were not found after the native build." >&2
    echo "Kernel candidate: ${kernel:-<missing>}" >&2
    echo "Server candidate: ${server:-<missing>}" >&2
    exit 1
fi

output=$build_dir/Voodoo2.config
if test -e "$output"; then
    echo "Refusing to replace existing staged driver: $output" >&2
    exit 1
fi
mkdir "$output"
cp "$kernel" "$output/Voodoo2_reloc"
cp "$server" "$output/V2Server"
cp "$project_dir/Default.table" "$output/Default.table"
cp "$project_dir/Localizable.strings" "$output/Localizable.strings"
chmod 755 "$output/Voodoo2_reloc" "$output/V2Server"

echo "Native Rhapsody driver staged at $output"
ls -l "$output"
if test -d "$framework_project/build/Glide2.framework"; then
    echo "Native Glide framework staged at $framework_project/build/Glide2.framework"
fi
