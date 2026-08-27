#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
output=${1:-$project/out/boote/boote-openstep-2880.iso}

# The ISO contains the installer/driver UFS payload; its El Torito entry is
# a BIOS-visible 2.88 MB floppy image containing BootE.
BOOTE_BOOT_MODE=floppy "$here/make-boote-openstep-disc.sh" "$output"

echo "BootE 2.88 MB floppy-emulation installer: $output"
