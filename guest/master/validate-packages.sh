#!/bin/sh
set -eu

mode=archive
if test "${1-}" = "--overlay"; then
    mode=overlay
    shift
elif test "${1-}" = "--archive"; then
    shift
fi

if test "$#" -eq 0; then
    echo "usage: $0 [--archive|--overlay] PACKAGE.pkg..." >&2
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
    suffixes=".info .bom .sizes"
    if test "$mode" = archive; then
        suffixes="$suffixes .tar.Z"
    fi
    for suffix in $suffixes; do
        if test ! -f "$package/$base$suffix"; then
            echo "$package: missing $base$suffix" >&2
            status=1
        fi
    done
done
exit "$status"
