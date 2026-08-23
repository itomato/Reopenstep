#!/bin/sh
set -eu

if test "$#" -ne 2; then
    echo "usage: $0 TARGET_ROOT EIDE.config" >&2
    exit 2
fi

target_root=$1
source_bundle=$2
driver_root="$target_root/private/Drivers/i386"
system_bundle="$driver_root/System.config"
destination="$driver_root/EIDE.config"

for required in EIDE_reloc EIDE_PIIX.table Default.table; do
    if test ! -f "$source_bundle/$required"; then
        echo "incomplete EIDE bundle: missing $required" >&2
        exit 1
    fi
done
if test ! -d "$system_bundle"; then
    echo "installed System.config not found: $system_bundle" >&2
    exit 1
fi

if test -d "$destination" && ! test -e "$destination.pre-reopenstep"; then
    mv "$destination" "$destination.pre-reopenstep"
fi
ditto "$source_bundle" "$destination"

for table in "$system_bundle/Default.table" "$system_bundle/Instance0.table"; do
    if test ! -f "$table"; then
        continue
    fi
    if grep '"Boot Drivers"' "$table" | grep EIDE >/dev/null 2>&1; then
        continue
    fi
    if ! test -e "$table.pre-reopenstep"; then
        cp -p "$table" "$table.pre-reopenstep"
    fi
    temporary=/tmp/reopenstep-eide-table.$$
    sed 's/"Boot Drivers" = "\([^"]*\)";/"Boot Drivers" = "\1 EIDE";/' \
        "$table" > "$temporary"
    cp "$temporary" "$table"
    chmod 444 "$table"
    rm -f "$temporary"
done

echo "EIDE installed and added to the target boot tables"
