#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
output=${XNU_KERNEL_OUTPUT:-$project/out/xnu/mach_kernel}
source_kernel=${XNU_KERNEL:-}
build_command=${XNU_BUILD_COMMAND:-}

mkdir -p "$(dirname -- "$output")"

if test -n "$source_kernel"; then
    if ! test -f "$source_kernel"; then
        echo "XNU_KERNEL does not exist: $source_kernel" >&2
        exit 2
    fi
    cp "$source_kernel" "$output"
elif test -n "$build_command"; then
    if test -z "${XNU_SOURCE:-}"; then
        echo "XNU_SOURCE is required when XNU_BUILD_COMMAND is used" >&2
        exit 2
    fi
    if ! test -d "$XNU_SOURCE"; then
        echo "XNU_SOURCE does not exist: $XNU_SOURCE" >&2
        exit 2
    fi
    (cd "$XNU_SOURCE" && sh -c "$build_command")
    built=${XNU_BUILT_KERNEL:-}
    if test -z "$built"; then
        echo "XNU_BUILT_KERNEL is required after XNU_BUILD_COMMAND completes" >&2
        exit 2
    fi
    if ! test -f "$built"; then
        echo "XNU_BUILT_KERNEL does not exist: $built" >&2
        exit 2
    fi
    cp "$built" "$output"
else
    echo "Set XNU_KERNEL to adopt an existing kernel, or XNU_SOURCE/XNU_BUILD_COMMAND/XNU_BUILT_KERNEL to build one." >&2
    echo "Example: XNU_KERNEL=/path/to/mach_kernel $0" >&2
    exit 2
fi

"$project/reopenstep" xnu inspect-kernel "$output" --require-boote
echo "XNU kernel artifact: $output"
