#!/bin/sh
set -eu

if test "$#" -lt 4; then
    echo "usage: $0 DEVELOPER_ROOT MEDIA_ROOT STAGING_ROOT STATE_DIR [PACKAGE...]" >&2
    exit 2
fi

developer_root=$1
media_root=$2
staging_root=$3
state_dir=$4
shift 4

script_dir=`dirname "$0"`
if test "$#" -eq 0; then
    set -- DeveloperTools DeveloperLibs DeveloperDoc GNUSource ProfileLibs
fi

"$script_dir/install-overlay-packages.sh" \
    "$developer_root" "$media_root" "$state_dir" "$@"

# Re-copying the complete installed-driver directory into the staging root
# ensures newly slipstreamed .config bundles enter the aggregate BOM. The old
# base BOM already limits every other part of the User media.
"$script_dir/rebuild-base-bom.sh" \
    "$media_root" "$staging_root" "$state_dir" private/Drivers/i386
