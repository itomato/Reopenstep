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

    memory = source / "i386/libsa/memory.h"
    text = memory.read_text()
    text = replace_once(text, "#define BOOT2_SEG\t\t\t0x2000",
                        "#define BOOT2_SEG\t\t\t0x5000",
                        "place BootE above the native sarld image")
    text = replace_once(text, "#define BOOT2_OFS\t\t\t0x0200",
                        "#define BOOT2_OFS\t\t\t0x2000",
                        "start BootE at sarld's 0x52000 ceiling")
    text = replace_once(text, "#define BOOT2_MAX_LENGTH\t\t0x6FE00",
                        "#define BOOT2_MAX_LENGTH\t\t0x4E000",
                        "keep BootE below PC firmware memory")
    memory.write_text(text)

    boot_makefile = source / "i386/boot2/Makefile"
    text = boot_makefile.read_text()
    text = replace_once(text, "BOOT2ADDR = 20200", "BOOT2ADDR = 52000",
                        "link BootE immediately above native sarld")
    text = replace_once(text, "MAXBOOTSIZE = 458240", "MAXBOOTSIZE = 319488",
                        "enforce the conventional-memory BootE window")
    text = replace_once(text, "DATA_PAD = 3582", "DATA_PAD = 512",
                        "keep BootE data and BSS below the PC EBDA")
    text = replace_once(
        text,
        "-fno-stack-protector \\\n\t\t-march=pentium4",
        "-fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \\\n"
        "\t\t-march=pentium4",
        "omit unusable BootE unwind metadata",
    )
    text = replace_once(
        text,
        "-march=pentium4 -msse2 -msoft-float",
        "-march=i686 -mno-sse -mno-sse2 -msoft-float",
        "target the Mendocino-class BootE execution path",
    )
    boot_makefile.write_text(text)

    cdboot = source / "i386/cdboot/cdboot.s"
    text = cdboot.read_text(encoding="latin-1")
    text = replace_once(text, "kBoot2MaxSize\t     EQU  458240",
                        "kBoot2MaxSize\t     EQU  319488",
                        "limit CD BootE below firmware memory")
    text = replace_once(text, "kBoot2Segment        EQU  0x2000",
                        "kBoot2Segment        EQU  0x5000",
                        "select BootE's sarld-safe segment")
    text = replace_once(text, "kBoot2Address        EQU  0x0200",
                        "kBoot2Address        EQU  0x2000",
                        "load BootE at sarld's ceiling")
    cdboot.write_text(text, encoding="latin-1")

    for boot1_name in ("boot1f32.s", "boot1h.s", "boot1he.s", "boot1hp.s"):
        boot1 = source / "i386/boot1" / boot1_name
        text = boot1.read_text(encoding="latin-1")
        text = replace_once(text, "kBoot2Segment\t\tEQU\t\t0x2000",
                            "kBoot2Segment\t\tEQU\t\t0x5000",
                            f"select the {boot1_name} BootE segment")
        text = replace_once(text, "kBoot2Address\t\tEQU\t\tkSectorBytes",
                            "kBoot2Address\t\tEQU\t\t0x2000",
                            f"load {boot1_name} BootE above sarld")
        boot1.write_text(text, encoding="latin-1")

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
        "\tentry_t\t\tkernelEntry;\n",
        "\tentry_t\t\tkernelEntry;\n"
        "\tvoid            *openStepBaseFile = NULL;\n",
        "reserve the preserved OPENSTEP basefile pointer",
    )
    text = replace_once(
        text,
        "\tbootArgs->kaddr = bootArgs->ksize = 0;\n"
        "\texecute_hook(\"ExecKernel\", (void*)binary, NULL, NULL, NULL);\n",
        "\tbootArgs->kaddr = bootArgs->ksize = 0;\n"
        "\tif (isOpenStepBootVolume(gBootVolume))\n"
        "\t\topenStepBaseFile = preserveOpenStepBaseFile(binary);\n"
        "\texecute_hook(\"ExecKernel\", (void*)binary, NULL, NULL, NULL);\n",
        "preserve the thin Mach-O before DecodeKernel maps over it",
    )
    text = replace_once(
        text,
        "\tif ( ret != 0 )\n\t\treturn ret;\n\n\t// Reserve space for boot args",
        "\tif ( ret != 0 )\n\t\treturn ret;\n\n"
        "\tif (isOpenStepBootVolume(gBootVolume)) {\n"
		"\t\tbool openStepVBE = false;\n"
		"\t\tconst char *openStepDrivers = NULL;\n"
		"\t\tint openStepDriverLength = 0;\n"
		"\t\tgetBoolForKey(\"OPENSTEP VBE\", &openStepVBE, &bootInfo->chameleonConfig);\n"
		"\t\tgetValueForKey(\"OPENSTEP Drivers\", &openStepDrivers, &openStepDriverLength,\n"
		"\t\t               &bootInfo->chameleonConfig);\n"
		"#if CONFIG_OPENSTEP_SARLD\n"
		"\t\topenStepDrivers = CONFIG_OPENSTEP_DRIVERS;\n"
		"#endif\n"
		"#if CONFIG_OPENSTEP_VBE\n"
		"\t\topenStepVBE = true;\n"
		"#endif\n"
		"\t\tif (openStepVBE) {\n"
		"\t\t\tsetVideoMode(GRAPHICS_MODE, 0);\n"
		"\t\t\topenStepVBE = (getVideoMode() == GRAPHICS_MODE);\n"
		"\t\t}\n"
        "\t\tvoid *legacyBootStruct = prepareOpenStepBootStruct(\n"
		"\t\t\tkernelEntry, openStepBaseFile, bootArgs->kaddr, bootArgs->ksize,\n"
		"\t\t\topenStepVBE, openStepDrivers);\n"
        "\t\tclearActivityIndicator();\n"
        "\t\tverbose(\"Starting OPENSTEP i386 at 0x%x\\n\", kernelEntry);\n"
        "\t\texecute_hook(\"Kernel Start\", (void *)kernelEntry, legacyBootStruct, NULL, NULL);\n"
        "\t\tstartprog(kernelEntry, legacyBootStruct);\n"
        "\t\treturn 0;\n"
        "\t}\n\n"
        "#if CONFIG_OPENSTEP_VBE\n"
        "\t/* The XNU lane uses normal Chameleon boot args but keeps a VBE\n"
        "\t * framebuffer when its root volume is NeXT UFS. */\n"
        "\tif (gBootVolume && strcmp(gBootVolume->type_name, \"NeXT UFS\") == 0)\n"
        "\t\tsetVideoMode(GRAPHICS_MODE, 0);\n"
        "#endif\n\n"
        "\t// Reserve space for boot args",
        "route NeXT UFS kernels through the legacy handoff",
    )
    boot.write_text(text)

    boot_entry = source / "i386/boot2/boot2.s"
    text = boot_entry.read_text()
    text = replace_once(
        text,
        "    mov     %ax, %es\n\n"
        "    data32\n"
        "    call    __switch_stack",
        "    mov     %ax, %es\n\n"
        "#ifdef CONFIG_OPENSTEP_ENTRY_PROBE\n"
        "    // Avoid BIOS services: mark the final VGA row, then stop at entry.\n"
        "    movw    $0xb800, %ax\n"
        "    movw    %ax, %es\n"
        "    movw    $0x4f42, %es:0x0f00\n"
        "    movw    $0x4f32, %es:0x0f02\n"
        "Lopenstep_entry_probe_halt:\n"
        "    cli\n"
        "    hlt\n"
        "    jmp     Lopenstep_entry_probe_halt\n"
        "#endif\n\n"
        "    data32\n"
        "    call    __switch_stack",
        "add the optional CUBX real-mode entry probe",
    )
    text = replace_once(
        text,
        "    call    __real_to_prot      # Enter protected mode.\n\n"
        "    fninit                      # FPU init",
        "    call    __real_to_prot      # Enter protected mode.\n\n"
        "    cli                         # Keep IRQs off until the legacy kernel owns the CPU.\n"
        "    fninit                      # FPU init",
        "mask hardware IRQs during the protected-mode loader transition",
    )
    boot_entry.write_text(text)

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
        "    struct direct *dir;\n"
        "    char          *buffer;\n"
        "    long long     index;\n"
        "    long          dirBlockNum, dirBlockOffset;",
        "    struct direct *dir;\n"
        "    struct direct  localDir;\n"
        "    char          *buffer;\n"
        "    long long     index;\n"
        "    long          dirBlockNum, dirBlockOffset, copyLength;",
        "reserve a private UFS directory record",
    )
    text = replace_once(
        text,
        "        dir = (struct direct *)(buffer + dirBlockOffset);\n"
        "        byte_swap_dir_block_in((char *)dir, 1);",
        "        copyLength = DIRBLKSIZ - dirBlockOffset;\n"
        "        if (copyLength > sizeof(localDir))\n"
        "            copyLength = sizeof(localDir);\n"
        "        bzero(&localDir, sizeof(localDir));\n"
        "        bcopy(buffer + dirBlockOffset, &localDir, copyLength);\n"
        "        dir = &localDir;\n"
        "        byte_swap_dir_block_in((char *)dir, 1);",
        "avoid byte-swapping the shared UFS block cache",
    )
    text = replace_once(
        text,
        "        *dirIndex += dir->d_reclen;\n"
        "        \n"
        "        if (dir->d_ino != 0) break;\n"
        "        \n"
        "        if (dirBlockOffset != 0) return -1;",
        "        if (dir->d_reclen < 12 ||\n"
        "            dir->d_reclen > DIRBLKSIZ - dirBlockOffset)\n"
        "            return -1;\n"
        "        *dirIndex += dir->d_reclen;\n"
        "\n"
        "        if (dir->d_ino != 0) break;\n"
        "        if (*dirIndex >= dirInode->di_size) return -1;",
        "skip valid free UFS directory records",
    )
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
        "\t\t\t-Wl,-dead_strip -Wl,-segalign,0x1 \\\n" + segment_anchor,
    )
    boot2_makefile.write_text(text)

    rules = source / "Make.rules"
    text = rules.read_text().replace(" -Werror", "")
    text = replace_once(
        text,
        "CFLAGS\t= $(CONFIG_OPTIMIZATION_LEVEL) -g -Wmost",
        "CFLAGS\t= $(CONFIG_OPTIMIZATION_LEVEL) -g -Wmost "
        "-fno-unwind-tables -fno-asynchronous-unwind-tables",
        "omit freestanding unwind metadata from BootE libraries",
    )
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
    text = replace_once(
        text,
        '@echo "#define I386BOOT_VERSION \\"5.0.132\\"" > $@',
        '@echo "#define I386BOOT_VERSION \\"5.0.133\\"" > $@',
        "bump the itomato Chameleon boot ABI banner",
    )
    text = replace_once(
        text,
        '@echo "#define I386BOOT_CHAMELEONVERSION \\"`cat $(SRCROOT)/version`\\"" >> $@',
        '@echo "#define I386BOOT_CHAMELEONVERSION \\"2.3-itomato\\"" >> $@',
        "identify the itomato Chameleon fork",
    )
    rules.write_text(text)

    prompt = source / "i386/boot2/prompt.c"
    text = prompt.read_text()
    text = replace_once(
        text,
        '" - Chameleon v" I386BOOT_CHAMELEONVERSION " r" I386BOOT_CHAMELEONREVISION "\\n"',
        '" - Chameleon itomato v" I386BOOT_CHAMELEONVERSION " r" I386BOOT_CHAMELEONREVISION "\\n"',
        "brand the itomato Chameleon fork",
    )
    prompt.write_text(text)

    commit_date = subprocess.check_output(
        ["git", "-C", str(source), "show", "-s", "--format=%ci", "HEAD"],
        text=True,
    ).strip()[:19]
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "--short=12", "HEAD"],
        text=True,
    ).strip()
    version = (source / "version").read_text().strip()
    if version == "2.2svn":
        version = "2.3-itomato"
    (source / "vers.h").write_text(
        '#define I386BOOT_VERSION "5.0.133"\n'
        f'#define I386BOOT_BUILDDATE "{commit_date}"\n'
        f'#define I386BOOT_CHAMELEONVERSION "{version}"\n'
        f'#define I386BOOT_CHAMELEONREVISION "{revision}"\n'
    )


if __name__ == "__main__":
    main()
