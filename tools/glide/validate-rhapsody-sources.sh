#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)
headers=${GLIDE_DR2_HEADERS:-$project_dir/out/glide/dr2-sdk-reference/System-Headers-B}
source_dir=$project_dir/glide/rhapsody

if ! test -d "$headers"; then
    echo "DR2 headers not found: $headers" >&2
    echo "Run 'make glide-dr2-reference' first." >&2
    exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/reopenstep-glide-validate.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM

# Modern Apple MIG needs the explicit Mach IPC branch when consuming the DR2
# std_types.defs.  DR2's own /usr/bin/mig selects its equivalent at build time.
mig -arch i386 -DMACH_IPC_FLAVOR=1 -I"$headers" \
    -server "$work_dir/V2DriverServer.c" \
    -user "$work_dir/V2DriverUser.c" \
    -header "$work_dir/V2Driver.h" \
    "$source_dir/Voodoo2.lksproj/V2Driver.defs"
mig -arch i386 -DMACH_IPC_FLAVOR=1 -I"$headers" \
    -server "$work_dir/V2ServerServer.c" \
    -user "$work_dir/V2ServerUser.c" \
    -header "$work_dir/V2Server.h" \
    "$source_dir/V2Server.tproj/V2Server.defs"

for symbol in V2Client_CountDevices V2Client_ReadConfigLong \
              V2Client_WriteConfigLong V2Client_MapDeviceMemory; do
    if ! grep -q "$symbol" "$work_dir/V2ServerUser.c"; then
        echo "generated Glide MIG client lacks $symbol" >&2
        exit 1
    fi
done

clang -fsyntax-only -x objective-c -Wno-everything -fno-builtin \
    -Di386 -D__i386__ -DKERNEL -D_KERNEL -DMACH_USER_API \
    -I"$headers" -I"$headers/bsd" \
    "$source_dir/Voodoo2.lksproj/Voodoo2.m"

clang -fsyntax-only -x c -Wno-everything -fno-builtin \
    -Di386 -D__i386__ -I"$headers" -I"$headers/bsd" \
    "$source_dir/V2Server.tproj/V2Server.c"
clang -fsyntax-only -x objective-c -Wno-everything -fno-builtin \
    -Di386 -D__i386__ -I"$headers" -I"$headers/bsd" \
    "$source_dir/V2Server.tproj/V2Server_main.m"

glide_public=${GLIDE2_SOURCE_ROOT:-$project_dir/out/glide/3dfx-glide-1999}
if test -f "$glide_public/REOPENSTEP_BASELINE_COMMIT"; then
    clang -fsyntax-only -x objective-c -Wno-everything -fno-builtin \
        -Di386 -D__i386__ -I"$script_dir/validation-stubs" \
        -I"$work_dir" -I"$headers" -I"$headers/bsd" \
        -I"$glide_public/swlibs/fxmisc" \
        -I"$glide_public/swlibs/newpci/pcilib" \
        "$source_dir/Glide2.framework/macosxglide.m"
fi

for symbol in V2Driver_ReadConfigLong V2Driver_WriteConfigLong \
              V2Driver_ReadConfig V2Driver_PrintDeviceName \
              V2Driver_PrintDeviceProperty; do
    if ! grep -q "$symbol" "$work_dir/V2DriverServer.c"; then
        echo "generated kernel MIG server lacks $symbol" >&2
        exit 1
    fi
done

for symbol in pciOpen pciGetConfigData pciSetConfigData pciMapCardMulti \
              GetDefault sst1InitCaching; do
    if ! grep -q "$symbol" "$source_dir/Glide2.framework/macosxglide.m"; then
        echo "Rhapsody Glide platform layer lacks $symbol" >&2
        exit 1
    fi
done

echo "Rhapsody Glide MIG contracts and DriverKit source validated."
