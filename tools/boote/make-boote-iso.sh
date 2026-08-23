#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project=$(CDPATH= cd -- "$here/../.." && pwd)
loader="$project/out/boote/boote-cdboot"
output=${1:-$project/out/boote/boote-smoke.iso}

if ! test -f "$loader"; then
    "$here/build-boote.sh" build
fi

temporary=$(mktemp -d "${TMPDIR:-/tmp}/boote-iso.XXXXXX")
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
stage="$temporary/root"
mkdir -p "$stage"
cp -R "$here/root/." "$stage/"
cp "$loader" "$stage/cdboot"
mkdir -p "$(dirname -- "$output")"

if command -v hdiutil >/dev/null 2>&1; then
    hdiutil makehybrid -iso -joliet -default-volume-name BOOTE \
        -eltorito-boot "$stage/cdboot" -no-emul-boot -ov \
        -o "$output" "$stage" >/dev/null
elif command -v xorriso >/dev/null 2>&1; then
    xorriso -as mkisofs -R -J -V BOOTE -b cdboot -no-emul-boot \
        -boot-load-size 4 -o "$output" "$stage" >/dev/null
else
    echo "BootE ISO mastering requires hdiutil or xorriso" >&2
    exit 3
fi

echo "BootE test ISO: $output"
ls -lh "$output"
shasum -a 256 "$output"
