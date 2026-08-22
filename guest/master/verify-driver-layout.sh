#!/bin/sh
set -eu

root="${1-/}"
driver_root="$root/private/Drivers/i386"

if test ! -d "$driver_root"; then
    echo "missing installed driver directory: $driver_root" >&2
    exit 1
fi

status=0
for driver in EIDE EISABus Floppy NE2000; do
    matches=`find "$driver_root" -type d -name "*$driver*.config" -print 2>/dev/null`
    if test -z "$matches"; then
        echo "missing required driver matching $driver" >&2
        status=1
    fi
done

exit "$status"
