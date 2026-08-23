#!/bin/sh
set -eu

if test "$#" -ne 1; then
    echo "usage: $0 UFS_ROOT" >&2
    exit 2
fi

root=$1
strings="$root/NextCD/CDIS/English.lproj/Localizable.strings"
if test ! -f "$strings"; then
    echo "CDIS English localization not found: $strings" >&2
    exit 1
fi

temporary=/tmp/reopenstep-cdis-strings.$$
trap 'rm -f "$temporary"' 0 1 2 3 15
sed 's#^"REMOVE_FLOPPY" = .*#"REMOVE_FLOPPY" = "Press Return to restart the computer.";#' \
    "$strings" > "$temporary"
if cmp -s "$strings" "$temporary"; then
    if grep '^"REMOVE_FLOPPY" = "Press Return to restart the computer\.";' "$strings" >/dev/null 2>&1; then
        echo "CDIS restart prompt already patched"
        exit 0
    fi
    echo "REMOVE_FLOPPY key was not found" >&2
    exit 1
fi
cp -p "$strings" "$strings.pre-reopenstep"
cp "$temporary" "$strings"
echo "CDIS floppy-removal text replaced with the restart prompt"
