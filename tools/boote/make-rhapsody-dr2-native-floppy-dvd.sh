#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
if test -n "${RHAPSODY_DR2_ISO:-}"; then
    source_iso=$RHAPSODY_DR2_ISO
else
    source_iso="$project/Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)/rhapsody_dr2_x86.iso"
fi
if test -n "${RHAPSODY_DR2_FLOPPY:-}"; then
    boot_floppy=$RHAPSODY_DR2_FLOPPY
else
    boot_floppy="$project/Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)/Boot floppy/rhapsody_dr2_x86_InstallationFloppy.img"
fi
if test -n "${RHAPSODY_DR2_DRIVER_FLOPPY:-}"; then
    driver_floppy=$RHAPSODY_DR2_DRIVER_FLOPPY
else
    driver_floppy="$project/Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)/Boot floppy/rhapsody_dr2_x86_DriverDisk.img"
fi
output=${1:-$project/out/boote/rhapsody-dr2-native-floppy-dvd.iso}
ufs=${RHAPSODY_DR2_UFS:-$project/out/rhapsody-dr2/rhapsody-dr2-front.ufs}
label=${RHAPSODY_DR2_LABEL:-$project/out/rhapsody-dr2/RHAPSODY_DR2_LABEL.bin}
combined_floppy=${RHAPSODY_DR2_COMBINED_FLOPPY:-$project/out/rhapsody-dr2/rhapsody-dr2-install-driver-2880.img}

if ! test -f "$source_iso"; then
    echo "Rhapsody DR2 source ISO not found: $source_iso" >&2
    exit 2
fi
if ! test -f "$boot_floppy"; then
    echo "Rhapsody DR2 install floppy not found: $boot_floppy" >&2
    exit 2
fi
if ! test -f "$driver_floppy"; then
    echo "Rhapsody DR2 driver floppy not found: $driver_floppy" >&2
    exit 2
fi

mkdir -p "$(dirname -- "$ufs")" "$(dirname -- "$label")" "$(dirname -- "$combined_floppy")"
if ! test -f "$ufs"; then
    python3 - "$source_iso" "$ufs" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
root_offset = 0xA0000
size = 300000 * 2048
with source.open("rb") as input_handle, output.open("wb") as output_handle:
    input_handle.seek(root_offset)
    remaining = size
    while remaining:
        chunk = input_handle.read(min(1024 * 1024, remaining))
        if not chunk:
            raise SystemExit("short Rhapsody DR2 UFS extraction")
        output_handle.write(chunk)
        remaining -= len(chunk)
PY
fi
if ! test -f "$label"; then
    python3 - "$source_iso" "$label" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
with source.open("rb") as input_handle:
    output.write_bytes(input_handle.read(7680))
PY
fi

"$project/reopenstep" floppy combine-2880 \
    --install "$boot_floppy" --drivers "$driver_floppy" --output "$combined_floppy" >/dev/null

"$project/reopenstep" rdrufs extract "$ufs" /mach_kernel "$project/out/rhapsody-dr2/native-check-mach_kernel" --root-offset 0 >/dev/null
"$project/reopenstep" image wrap --boot-mode floppy \
    --ufs "$ufs" --root-kind rhapsody-dr2 \
    --boot-image "$combined_floppy" \
    --label-template "$label" \
    --label-offset 112 --label-format u16be \
    --volume RHAPSODY_NATIVE --output "$output"

echo "Native Rhapsody DR2 floppy-boot DVD image: $output"
echo "Combined 2.88MB El Torito floppy image: $combined_floppy"
ls -lh "$output"
shasum -a 256 "$output"
