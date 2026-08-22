#!/bin/sh
set -eu

if test "$#" -lt 3; then
    echo "usage: $0 BOOT_ROOT INSTALL_ROOT DRIVER_SOURCE..." >&2
    exit 2
fi

boot_root=$1
install_root=$2
shift 2

boot_drivers="$boot_root/private/Drivers/i386"
install_drivers="$install_root/private/Drivers/i386"
mkdir -p "$boot_drivers" "$install_drivers"

seen=/tmp/reopenstep-driver-seen.$$
: > "$seen"
trap 'rm -f "$seen"' 0 1 2 3 15

for source in "$@"; do
    if test ! -d "$source"; then
        echo "driver source is not a directory: $source" >&2
        exit 1
    fi
    list=/tmp/reopenstep-driver-list.$$
    find "$source" -type d -name '*.config' -prune -print > "$list"
    while read config; do
        name=`basename "$config"`
        folded=`echo "$name" | tr A-Z a-z`
        if grep "^$folded$" "$seen" >/dev/null 2>&1; then
            echo "duplicate driver bundle without declared winner: $name" >&2
            exit 1
        fi
        echo "$folded" >> "$seen"
        ditto "$config" "$boot_drivers/$name"
        ditto "$config" "$install_drivers/$name"
    done < "$list"
    rm -f "$list"
done

echo "drivers copied to startup and installed-system roots"
