#!/bin/sh
set -eu

commit=6ef2908f3d7ef85f593ecb6501e8589ba55c8810
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$here/src"
bin_dir="$here/bin"

if [ ! -d "$source_dir/.git" ]; then
    git clone https://github.com/ostrich/nextufs.git "$source_dir"
fi
git -C "$source_dir" fetch origin "$commit"
git -C "$source_dir" reset --hard "$commit"
git -C "$source_dir" checkout --detach "$commit"
rm -f "$source_dir/src/commands/mount_stub.c"
git -C "$source_dir" apply "$here/offline.patch"
# The offline build must retain the formatter, grower, and checker.  The
# original offline patch predates RDR mastering and replaced these commands
# with a FUSE-only stub; restore the upstream offline-capable sources while
# retaining the patch's raw-browse and mutation changes.
git -C "$source_dir" show HEAD:Makefile > "$source_dir/Makefile.upstream"
git -C "$source_dir" show HEAD:src/commands/mkimg.c > "$source_dir/src/commands/mkimg.c"
git -C "$source_dir" show HEAD:src/commands/resize.c > "$source_dir/src/commands/resize.c"
git -C "$source_dir" show HEAD:src/commands/fsck.c > "$source_dir/src/commands/fsck.c"
git -C "$source_dir" show HEAD:src/commands/mount.c > "$source_dir/src/commands/mount.c"
mv "$source_dir/Makefile.upstream" "$source_dir/Makefile"
# Build without FUSE on macOS, but keep mount_stub so the command remains
# explicit rather than accidentally linking against a partial mount backend.
perl -0pi -e 's#src/commands/mount\.c#src/commands/mount_stub.c#g; s#src/commands/fsck\.c ##g; s/\$\(FUSE_CFLAGS\)//g; s/\$\(FUSE_LIBS\)//g; s/\$\(OBJ_DIR\)\/src\/commands\/mount\.o:/\$\(OBJ_DIR\)\/src\/commands\/mount_stub.o:/g; s/FSCK_SRCS = .*?\n/FSCK_SRCS =\n/s' "$source_dir/Makefile"
perl -0pi -e 's/\n\t(?:dir_scan|pass1|source\.c).*?\nFSCK_OBJS/\nFSCK_OBJS/s' "$source_dir/Makefile"
perl -0pi -e 's/\nint nextufs_mkimg_main.*?\nint nextufs_resize_main.*?\n/\n/s' "$source_dir/src/commands/mount_stub.c"
# Keep the historical byte-swapped helper as the default OPENSTEP editor.
make -C "$source_dir" nextufs \
    CFLAGS='-Iinclude -Isrc -O2 -g -std=gnu99 -Wall -Wextra' \
    FORMAT_CFLAGS='-O2 -g -std=gnu89 -Wall -Wextra'
cp "$source_dir/nextufs" "$bin_dir/nextufs"
# Emit native-endian RDR UFS from the same formatter.  The formatter normally
# byte-swaps its BSD structures for NeXTSTEP's historical on-disk order;
# RDR/i386 stores those structures in host (little-endian) order.
python3 - "$source_dir/src/mkimg_format/format_io.c" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
for name, args, noops in (
    ("swap_csum", "struct csum *cs", "\t(void)cs;"),
    ("swap_superblock", "struct fs *fs", "\t(void)fs;"),
    ("swap_cg", "struct cg *cg", "\t(void)cg;"),
    ("swap_inode_block_bytes", "struct dinode *dp, int count", "\t(void)dp;\n\t(void)count;"),
):
    pattern = rf"(void\n{name}\({re.escape(args)}\)\n\{{\n)(.*?)(\n\}})"
    match = re.search(pattern, text, re.S)
    if not match:
        raise SystemExit(f"cannot locate {name} in formatter")
    replacement = (match.group(1) + "#ifdef NEXTUFS_RDR_NATIVE\n" + noops +
                   "\n\treturn;\n#else\n" + match.group(2) +
                   "\n#endif" + match.group(3))
    text = text[:match.start()] + replacement + text[match.end():]
path.write_text(text)
PY
# The shared reader/mutator uses explicit big-endian helpers.  For the RDR
# binary, make those helpers native little-endian while retaining their API.
python3 - "$source_dir/src/core/layout.c" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
text = text.replace(
    'return ((uint16_t)p[0] << 8) | p[1];',
    'return (uint16_t)p[0] | ((uint16_t)p[1] << 8);')
text = text.replace(
    'return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |\n\t    ((uint32_t)p[2] << 8) | p[3];',
    'return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |\n\t    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);')
text = text.replace(
    'p[0] = (uint8_t)(v >> 8);\n\tp[1] = (uint8_t)v;',
    'p[0] = (uint8_t)v;\n\tp[1] = (uint8_t)(v >> 8);')
text = text.replace(
    'p[0] = (uint8_t)(v >> 24);\n\tp[1] = (uint8_t)(v >> 16);\n\tp[2] = (uint8_t)(v >> 8);\n\tp[3] = (uint8_t)v;',
    'p[0] = (uint8_t)v;\n\tp[1] = (uint8_t)(v >> 8);\n\tp[2] = (uint8_t)(v >> 16);\n\tp[3] = (uint8_t)(v >> 24);')
path.write_text(text)
PY
make -C "$source_dir" clean >/dev/null
mkdir -p "$source_dir/.scratch" "$bin_dir"
make -C "$source_dir" nextufs \
    CFLAGS='-Iinclude -Isrc -O2 -g -std=gnu99 -Wall -Wextra -DNEXTUFS_RDR_NATIVE' \
    FORMAT_CFLAGS='-O2 -g -std=gnu89 -Wall -Wextra -DNEXTUFS_RDR_NATIVE'
cp "$source_dir/nextufs" "$bin_dir/nextufs-rdr"
printf '%s\n' "$commit" > "$bin_dir/SOURCE_COMMIT"
