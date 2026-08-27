#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d "${TMPDIR:-/tmp}/boote-config.XXXXXX")
trap 'rm -rf "$temporary"' EXIT HUP INT TERM

python3 "$here/generate_config.py" \
    --profile "$here/config/minimal.toml" --output-dir "$temporary" >/dev/null

test -s "$temporary/.config"
test -s "$temporary/auto.conf"
test -s "$temporary/autoconf.h"
test -s "$temporary/autoconf.inc"
grep -q '^CONFIG_OPTIMIZATION_LEVEL="-Oz"$' "$temporary/auto.conf"
grep -q '^# CONFIG_MODULES is not set$' "$temporary/auto.conf"
grep -q '^#define CONFIG_BOOT0_VERBOSE CONFIG_IS_BUILTIN$' "$temporary/autoconf.h"
grep -q '^#define CONFIG_OPENSTEP_HANDOFF CONFIG_IS_BUILTIN$' "$temporary/autoconf.h"
grep -q '^CONFIG_MODULES EQU 0$' "$temporary/autoconf.inc"
cmp "$temporary/.config" "$temporary/auto.conf"

python3 "$here/generate_config.py" \
    --profile "$here/config/vesa.toml" --output-dir "$temporary" >/dev/null
grep -q '^CONFIG_OPENSTEP_DRIVERS="EISABus PCIBus Intel824X0 PS2Keyboard EIDE BusLogicSCSIDriver Adaptec2940SCSIDriver VBE20DisplayDriver MatroxMGA2064WDisplayDriver"$' "$temporary/auto.conf"
grep -q '^CONFIG_OPENSTEP_KERNEL_FLAGS="rootdev=hd0a"$' "$temporary/auto.conf"
grep -q '^#define CONFIG_OPENSTEP_SARLD CONFIG_IS_BUILTIN$' "$temporary/autoconf.h"
grep -q '^# CONFIG_OPENSTEP_VBE is not set$' "$temporary/auto.conf"
grep -q '^#define CONFIG_OPENSTEP_EIDE_SAFE CONFIG_IS_BUILTIN$' "$temporary/autoconf.h"
echo "BootE static configuration: ok"
