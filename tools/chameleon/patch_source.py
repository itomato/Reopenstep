#!/usr/bin/env python3
"""Apply the reproducible OPENSTEP UFS changes to the pinned Chameleon tree."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{description}: expected one source match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, description: str) -> str:
    result, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{description}: expected one source match, found {count}")
    return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_source.py CHAMELEON_SOURCE")
    source = Path(sys.argv[1]).resolve()
    here = Path(__file__).resolve().parent
    libsaio = source / "i386/libsaio"
    overlay = here / "overlay/i386"
    for source_file in overlay.rglob("*"):
        if source_file.is_file():
            relative = source_file.relative_to(overlay)
            destination = source / "i386" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, destination)

    makefile = libsaio / "Makefile"
    text = makefile.read_text()
    text = replace_once(text, "\tdisk.o sys.o cache.o bootstruct.o \\\n",
                        "\tdisk.o nextlabel.o openstep_boot.o sys.o cache.o bootstruct.o \\\n",
                        "link nextlabel.o")
    text = replace_once(
        text,
        "\tstringTable.o load.o pci.o allocate.o misc.o \\\n",
        "\tstringTable.o load.o pci.o allocate.o misc.o \\\n"
        "\tufs.o ufs_byteorder.o \\\n",
        "link the restored UFS reader",
    )
    text = replace_once(
        text,
        "DEFINES = -DNOTHING",
        "DEFINES = -DNOTHING -D__APPLE_API_UNSTABLE -D__APPLE_API_PRIVATE",
        "expose the legacy Apple UFS interfaces",
    )
    text = replace_once(
        text,
        "-fno-builtin -static $(OMIT_FRAME_POINTER_CFLAG)",
        "-fno-builtin -static $(OMIT_FRAME_POINTER_CFLAG) \\\n"
        "    -mstack-alignment=4 -fno-align-functions",
        "retain the boot2 assembly/C stack ABI on modern Clang",
    )
    text = replace_once(
        text,
        "-march=pentium4 -msse2 -msoft-float",
        "-march=i686 -mno-sse -mno-sse2 -msoft-float",
        "target Socket 370-class i686 CPUs without SSE2",
    )
    makefile.write_text(text)

    boot = source / "i386/boot2/boot.c"
    text = boot.read_text()
    text = replace_once(
        text,
        '#include "modules.h"\n',
        '#include "modules.h"\n#include "openstep_boot.h"\n',
        "include the OPENSTEP handoff adapter",
    )
    text = replace_once(
        text,
        "\tif ( ret != 0 )\n\t\treturn ret;\n\n\t// Reserve space for boot args",
        "\tif ( ret != 0 )\n\t\treturn ret;\n\n"
        "\tif (isOpenStepBootVolume(gBootVolume)) {\n"
		"\t\tbool openStepVBE = false;\n"
		"\t\tgetBoolForKey(\"OPENSTEP VBE\", &openStepVBE, &bootInfo->chameleonConfig);\n"
		"\t\tif (openStepVBE) {\n"
		"\t\t\tsetVideoMode(GRAPHICS_MODE, 0);\n"
		"\t\t\topenStepVBE = (getVideoMode() == GRAPHICS_MODE);\n"
		"\t\t}\n"
        "\t\tvoid *legacyBootStruct = prepareOpenStepBootStruct(\n"
		"\t\t\tkernelEntry, bootArgs->kaddr, bootArgs->ksize, openStepVBE);\n"
        "\t\tclearActivityIndicator();\n"
        "\t\tverbose(\"Starting OPENSTEP i386 at 0x%x\\n\", kernelEntry);\n"
        "\t\texecute_hook(\"Kernel Start\", (void *)kernelEntry, legacyBootStruct, NULL, NULL);\n"
        "\t\tstartprog(kernelEntry, legacyBootStruct);\n"
        "\t\treturn 0;\n"
        "\t}\n\n"
        "\t// Reserve space for boot args",
        "route NeXT UFS kernels through the legacy handoff",
    )
    boot.write_text(text)

    disk = libsaio / "disk.c"
    text = disk.read_text()
    text = replace_once(text, "#define UFS_SUPPORT 0", "#define UFS_SUPPORT 1", "enable UFS")
    text = replace_once(text, '#include "ufs.h"\n', '#include "ufs.h"\n#include "nextlabel.h"\n',
                        "include NeXT label parser")
    text = replace_once(
        text,
        '#if UFS_SUPPORT\n#include "ufs.h"\n#include "nextlabel.h"\n#endif\n#include <limits.h>',
        '#include <limits.h>',
        "defer UFS declarations until libsaio types are available",
    )
    text = replace_once(
        text,
        '#include "disk.h"\n',
        '#include "disk.h"\n#if UFS_SUPPORT\n#include "ufs.h"\n#include "nextlabel.h"\n#endif\n',
        "include UFS declarations after disk types",
    )

    constructor = r'''
#if UFS_SUPPORT
static BVRef newNeXTBVRef(int biosdev, int partno, unsigned int outer_boff,
                          const struct fdisk_part *part)
{
    static const unsigned int labelSectors[] = { 0, 15, 30, 45 };
    unsigned char *label;
    unsigned int i;
    unsigned int ufs_boff;
    BVRef bvr = NULL;

    label = (unsigned char *)malloc(1024);
    if (!label)
        return NULL;
    for (i = 0; i < sizeof(labelSectors) / sizeof(labelSectors[0]); i++) {
        if (readBytes(biosdev, outer_boff + labelSectors[i], 0, 1024, label) != 0)
            continue;
        if (NeXTLabelUFSOffset(label, 1024, labelSectors[i], &ufs_boff) != 0)
            continue;
        bvr = newFDiskBVRef(
            biosdev, partno, outer_boff + ufs_boff, part,
            UFSInitPartition, UFSLoadFile, UFSReadFile, UFSGetDirEntry,
            UFSGetFileBlock, UFSGetUUID, UFSGetDescription, UFSFree,
            1, kBIOSDevTypeHardDrive, kBVFlagSystemVolume);
        if (bvr) {
            strlcpy(bvr->name, "OPENSTEP", BVSTRLEN);
            strlcpy(bvr->type_name, "NeXT UFS", BVSTRLEN);
        }
        break;
    }
    free(label);
    return bvr;
}
#endif

//==============================================================================

'''
    text = replace_once(text, "BVRef newAPMBVRef( int biosdev", constructor + "BVRef newAPMBVRef( int biosdev",
                        "add NeXT volume constructor")
    text = regex_once(
        text,
        r"#if UFS_SUPPORT\n    BVRef\s+booterUFS = NULL;\n#endif\n    int\s+spc;.*?    do \{",
        "    do {",
        "remove obsolete UFS booter geometry",
    )
    text = replace_once(
        text,
        "#if UFS_SUPPORT\n                    case FDISK_UFS:",
        "#if UFS_SUPPORT\n                    case FDISK_NEXTNAME:\n"
        "                        bvr = newNeXTBVRef(biosdev, partno, part->relsect, part);\n"
        "                        break;\n\n                    case FDISK_UFS:",
        "recognize MBR type 0xA7",
    )
    text = regex_once(
        text,
        r"\n#if UFS_SUPPORT\n                    case FDISK_BOOTER:.*?\n#endif\n\n                    case FDISK_FAT32:",
        "\n                    case FDISK_FAT32:",
        "remove duplicate FDISK_BOOTER case",
    )
    text = regex_once(
        text,
        r"\n#if UFS_SUPPORT\n            // Booting from a CD with an UFS filesystem embedded.*?\n#endif\n",
        "\n",
        "remove obsolete booter fallback",
    )

    scanner = r'''#if UFS_SUPPORT
static BVRef diskScanNeXTBootVolumes(int biosdev, int *countPtr)
{
    struct DiskBVMap *map;
    struct fdisk_part part;
    BVRef bvr;

    bzero(&part, sizeof(part));
    part.systid = FDISK_NEXTNAME;
    bvr = newNeXTBVRef(biosdev, 1, 0, &part);
    if (!bvr) {
        if (countPtr)
            *countPtr = 0;
        return NULL;
    }
    map = (struct DiskBVMap *)malloc(sizeof(*map));
    if (!map) {
        UFSFree(bvr);
        if (countPtr)
            *countPtr = 0;
        return NULL;
    }
    map->biosdev = biosdev;
    map->bvr = bvr;
    map->bvrcnt = 1;
    map->next = gDiskBVMap;
    gDiskBVMap = map;
    if (countPtr)
        *countPtr = 1;
    return bvr;
}
#endif

//==============================================================================

'''
    text = replace_once(text, "static BVRef diskScanAPMBootVolumes", scanner + "static BVRef diskScanAPMBootVolumes",
                        "add whole-disk NeXT scanner")
    text = replace_once(
        text,
        "\t\tif (bvr == NULL)\n\t\t{\n\t\t\tbvr = diskScanAPMBootVolumes(biosdev, &count);\n\t\t}",
        "#if UFS_SUPPORT\n\t\tif (bvr == NULL)\n\t\t{\n"
        "\t\t\tbvr = diskScanNeXTBootVolumes(biosdev, &count);\n\t\t}\n#endif\n"
        "\t\tif (bvr == NULL)\n\t\t{\n\t\t\tbvr = diskScanAPMBootVolumes(biosdev, &count);\n\t\t}",
        "scan whole-disk NeXT labels",
    )
    text = replace_once(text, '\t{ FDISK_UFS,\t\t"Apple UFS"      },',
                        '\t{ FDISK_NEXTNAME,\t"NeXT UFS"       },\n'
                        '\t{ FDISK_UFS,\t\t"Apple UFS"      },',
                        "name NeXT partition type")
    disk.write_text(text)

    ufs_byteorder = libsaio / "ufs_byteorder.h"
    text = ufs_byteorder.read_text()
    text = replace_once(
        text,
        "//#include <sys/vnode.h>\n#include <ufs/ffs/fs.h>\n#include <sys/buf.h>\n#include <sys/disk.h>\n#include <ufs/ufs/dinode.h>",
        "//#include <sys/vnode.h>\n"
        "#ifndef _INO_T\n"
        "typedef __darwin_ino_t ino_t;\n"
        "#define _INO_T\n"
        "#endif\n"
        "#include <ufs/ufs/dinode.h>\n"
        "#include <ufs/ffs/fs.h>\n"
        "#include <sys/buf.h>\n"
        "#include <sys/disk.h>",
        "supply UFS inode type and order its on-disk declarations",
    )
    ufs_byteorder.write_text(text)

    ufs = libsaio / "ufs.c"
    text = ufs.read_text()
    text = replace_once(
        text,
        "    *name = strlcpy(gTempName2, dir->d_name, dir->d_namlen+1);",
        "    strlcpy(gTempName2, dir->d_name, dir->d_namlen + 1);\n"
        "    *name = gTempName2;",
        "return the copied UFS directory name",
    )
    ufs.write_text(text)

    modules = source / "i386/modules/Makefile"
    text = modules.read_text()
    text = replace_once(
        text, "SUBDIRS = KernelPatcher",
        "SUBDIRS =\n\nifdef CONFIG_KERNELPATCHER_MODULE\nSUBDIRS += KernelPatcher\nendif",
        "honor disabled KernelPatcher module",
    )
    modules.write_text(text)

    boot2_makefile = source / "i386/boot2/Makefile"
    text = boot2_makefile.read_text().replace(" -Werror", "")
    segment_anchor = "\t\t\t-Wl,-segaddr,__INIT,"
    if text.count(segment_anchor) != 3:
        raise SystemExit(
            "set the legacy boot2 segment alignment: expected three source matches"
        )
    text = text.replace(
        segment_anchor,
        "\t\t\t-Wl,-segalign,0x1 \\\n" + segment_anchor,
    )
    boot2_makefile.write_text(text)

    rules = source / "Make.rules"
    text = rules.read_text().replace(" -Werror", "")
    text = replace_once(
        text,
        '@echo "#define I386BOOT_BUILDDATE \\"`date \\"+%Y-%m-%d %H:%M:%S\\"`\\"" >> $@',
        '@echo "#define I386BOOT_BUILDDATE \\"`git -C $(SRCROOT) show -s --format=%ci HEAD | cut -c1-19`\\"" >> $@',
        "make the embedded BootE build date reproducible",
    )
    text = replace_once(
        text,
        '@echo "#define I386BOOT_CHAMELEONREVISION \\"`svnversion -n | tr -d [:alpha:]`\\"" >> $@',
        '@echo "#define I386BOOT_CHAMELEONREVISION \\"`git -C $(SRCROOT) rev-parse --short=12 HEAD`\\"" >> $@',
        "identify the pinned Chameleon source revision",
    )
    rules.write_text(text)

    commit_date = subprocess.check_output(
        ["git", "-C", str(source), "show", "-s", "--format=%ci", "HEAD"],
        text=True,
    ).strip()[:19]
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "--short=12", "HEAD"],
        text=True,
    ).strip()
    version = (source / "version").read_text().strip()
    (source / "vers.h").write_text(
        '#define I386BOOT_VERSION "5.0.132"\n'
        f'#define I386BOOT_BUILDDATE "{commit_date}"\n'
        f'#define I386BOOT_CHAMELEONVERSION "{version}"\n'
        f'#define I386BOOT_CHAMELEONREVISION "{revision}"\n'
    )


if __name__ == "__main__":
    main()
