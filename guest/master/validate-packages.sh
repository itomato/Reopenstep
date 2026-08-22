#!/bin/sh
set -eu

if test "$#" -eq 0; then
    echo "usage: $0 PACKAGE.pkg..." >&2
    exit 2
fi

status=0
for package in "$@"; do
    if test ! -d "$package"; then
        echo "not an Installer package directory: $package" >&2
        status=1
        continue
    fi
    base=`basename "$package" .pkg`
    for suffix in .info .bom .sizes .tar.Z; do
        if test ! -f "$package/$base$suffix"; then
            echo "$package: missing $base$suffix" >&2
            status=1
        fi
    done
done
exit "$status"
