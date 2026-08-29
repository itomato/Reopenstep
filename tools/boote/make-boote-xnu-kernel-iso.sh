#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
kernel=${XNU_KERNEL_OUTPUT:-$project/out/xnu/mach_kernel}
output=${1:-$project/out/boote/boote-xnu-kernel.iso}
root=${BOOTE_XNU_ROOT:-$project/out/boote/xnu-kernel-root}
profile=${BOOTE_CONFIG:-$here/config/xnu-ufs-vesa.toml}
volume=${BOOTE_VOLUME:-BOOTE_XNU}
load_mode=${BOOTE_NOEMUL_LOAD_MODE:-canonical}

if ! test -f "$kernel"; then
    XNU_KERNEL_OUTPUT="$kernel" "$project/tools/xnu/build-xnu-kernel.sh"
fi

"$project/reopenstep" xnu inspect-kernel "$kernel" --require-boote >/dev/null
BOOTE_CONFIG="$profile" "$here/build-boote.sh" build

temporary=$(mktemp -d "${TMPDIR:-/tmp}/boote-xnu-kernel.XXXXXX")
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
stage="$temporary/root"
mkdir -p "$stage/Extra"

cp "$project/out/boote/boote-cdboot" "$stage/cdboot"
cp "$kernel" "$stage/mach_kernel"

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
  <string>${XNU_KERNEL_FLAGS:--v keepsyms=1}</string>
  <key>Verbose</key>
  <string>Yes</string>
  <key>Graphics Mode</key>
  <string>${XNU_GRAPHICS_MODE:-1024x768x32}</string>
</dict>
</plist>
EOF

if test -d "$root"; then
    cp -R "$root/." "$stage/"
fi

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
elif command -v xorriso >/dev/null 2>&1; then
    echo "xorriso fallback cannot create the HFS hybrid expected by this Chameleon CD path" >&2
    exit 3
else
    echo "BootE XNU ISO mastering requires hdiutil for HFS/ISO hybrid output" >&2
    exit 3
fi

"$project/reopenstep" image inspect "$output" --require-bootable >/dev/null
echo "BootE XNU kernel ISO: $output"
ls -lh "$output"
shasum -a 256 "$output"
