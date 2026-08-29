#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
if test -n "${RHAPSODY_DR2_ISO:-}"; then
    source_iso=$RHAPSODY_DR2_ISO
else
    source_iso="$project/Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)/rhapsody_dr2_x86.iso"
fi
output=${1:-$project/out/boote/boote-rhapsody-dr2-dvd.iso}
kernel=${RHAPSODY_DR2_KERNEL:-$project/out/re/rhapsody-dr2/cd-mach_kernel}
volume=${BOOTE_VOLUME:-RHAPSODY_DR2}
profile=${BOOTE_CONFIG:-$here/config/xnu-ufs-vesa.toml}
load_mode=${BOOTE_NOEMUL_LOAD_MODE:-canonical}

if ! test -f "$source_iso"; then
    echo "Rhapsody DR2 source ISO not found: $source_iso" >&2
    echo "Set RHAPSODY_DR2_ISO=/path/to/rhapsody_dr2_x86.iso" >&2
    exit 2
fi

mkdir -p "$(dirname -- "$kernel")"
if ! test -f "$kernel"; then
    "$project/reopenstep" rdrufs extract "$source_iso" /mach_kernel "$kernel" >/dev/null
fi

"$project/reopenstep" xnu inspect-kernel "$kernel" --require-boote >/dev/null
BOOTE_CONFIG="$profile" "$here/build-boote.sh" build

temporary=$(mktemp -d "${TMPDIR:-/tmp}/boote-rhapsody-dvd.XXXXXX")
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
stage="$temporary/root"
mkdir -p "$stage/Extra" "$stage/Payload" "$stage/Docs"

cp "$project/out/boote/boote-cdboot" "$stage/cdboot"
cp "$kernel" "$stage/mach_kernel"
cp "$source_iso" "$stage/Payload/rhapsody_dr2_x86.iso"

cat > "$stage/Extra/org.chameleon.Boot.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>GUI</key>
  <string>No</string>
  <key>Instant Menu</key>
  <string>Yes</string>
  <key>Timeout</key>
  <string>0</string>
  <key>Kernel</key>
  <string>mach_kernel</string>
  <key>UseKernelCache</key>
  <string>No</string>
  <key>Kernel Flags</key>
  <string>${RHAPSODY_KERNEL_FLAGS:--v keepsyms=1}</string>
  <key>Verbose</key>
  <string>Yes</string>
  <key>Graphics Mode</key>
  <string>${RHAPSODY_GRAPHICS_MODE:-1024x768x32}</string>
</dict>
</plist>
EOF

cat > "$stage/Docs/README.txt" <<EOF
BootE Rhapsody DR2 i386 DVD test image

This image is a BootE/Chameleon no-emulation HFS/ISO hybrid.
It contains:

- cdboot: BootE El Torito loader
- mach_kernel: extracted from Titan1U Rhapsody DR2 i386 media
- Payload/rhapsody_dr2_x86.iso: original Rhapsody DR2 source ISO payload

The kernel is staged for BootE loader testing. The payload ISO is included so
the disc is self-contained for installer/filesystem experiments.
EOF

mkdir -p "$(dirname -- "$output")"
if command -v hdiutil >/dev/null 2>&1; then
    hdiutil makehybrid -hfs -iso -joliet -default-volume-name "$volume" \
        -eltorito-boot "$stage/cdboot" -no-emul-boot -ov \
        -o "$output" "$stage" >/dev/null
    if test "$load_mode" = "full"; then
        "$project/tools/boote/patch-noemul-load-size.py" \
            "$output" "$project/out/boote/boote-cdboot"
    elif test "$load_mode" != "canonical"; then
        echo "unsupported BOOTE_NOEMUL_LOAD_MODE: $load_mode (use canonical or full)" >&2
        exit 2
    fi
else
    echo "BootE Rhapsody DVD mastering requires hdiutil for HFS/ISO hybrid output" >&2
    exit 3
fi

"$project/reopenstep" image inspect "$output" --require-bootable >/dev/null
echo "BootE Rhapsody DR2 DVD image: $output"
echo "no-emulation load mode: $load_mode"
ls -lh "$output"
shasum -a 256 "$output"
