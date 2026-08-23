#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
binary="${TMPDIR:-/tmp}/reopenstep-nextlabel-test"
${CC:-cc} -std=c99 -Wall -Wextra -Werror \
    -I"$here/host-test" -I"$here/overlay/i386/libsaio" \
    "$here/overlay/i386/libsaio/nextlabel.c" \
    "$here/host-test/nextlabel_test.c" -o "$binary"
"$binary" "$@"
