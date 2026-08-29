# Rhapsody Bootloader And Kernel RE Notes

## Local Artifacts

| Artifact | Role | Evidence |
| --- | --- | --- |
| `out/re/rhapsody-dr2/floppy-boot2.bin` | Rhapsody DR2 i386 boot2 extracted from install floppy | Raw x86 loader blob imported in Ghidra as `x86:LE:16:Real Mode`; contains 32-bit code and absolute low-memory references. |
| `out/re/rhapsody-dr2/cd-boot2.bin` | Rhapsody DR2 i386 boot2 extracted from CD path | Same loader string surface as floppy boot2. |
| `out/re/rhapsody-dr2/cd-mach_kernel` | Rhapsody DR2 i386 kernel | Mach-O i386, imported in Ghidra as `x86:LE:32:default`. |
| `out/rhapsody-dr2/rhapsody-dr2-front.ufs` | Extracted Rhapsody CD/front root | Native little-endian UFS1, 8192-byte blocks, 2048-byte fragments. |
| `Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)/Boot floppy/rhapsody_dr2_x86_InstallationFloppy.img` | Stock install floppy | NeXT `dlV3` label points root UFS to byte offset `0x18000`; superblock at `0x1a000`. |
| `vault/Darwin-0.3.toast` | Darwin 0.3 APM image | Contains `Apple_HFS`, `Darwin_OF3_Booter`, `SecondaryLoader`, and `Apple_Rhapsody_UFS` partitions. The UFS root starts at `0x10908800`. |
| `vault/Darwin_6_0_2_x86.iso` | Darwin 6.0.2 x86 installer ISO | El Torito hard-disk-emulation image with `usr/standalone/i386/cdboot.dmg`, fat `mach_kernel`, `Extensions.mkext`, and kext bundles. |
| `out/re/darwin-6.0.2/mach_kernel.i386` | Darwin 6.0.2 i386 kernel slice | Thin Mach-O i386 slice from the fat kernel, imported in Ghidra as `x86:LE:32:default`. |
| `out/re/darwin-6.0.2/cdboot-partition.img` | Darwin 6.0.2 boot-helper partition | Nested Apple Boot/UFS-style big-endian UFS1 image with `mach_kernel.rcz`, `private`, and `System`. |

## Boot1 And Boot2 Contract

Recovered Rhapsody DR2 boot1 behavior:

1. BIOS loads sector zero at `0000:7c00`.
2. boot1 relocates and reads the NeXT `dlV3` label from sector 15.
3. boot1 reads media sector size at label-relative offset `0x5c`.
4. boot1 reads boot2 block at label-relative offset `0x7c`.
5. boot1 computes `boot2_lba = boot2_block * (media_sector_size / 512)`.
6. boot1 loads `0x58` BIOS sectors at physical `0x3000`.

Observed install floppy values:

| Field | Value |
| --- | --- |
| `media_sector_size` | `1024` |
| `boot2_block` | `0x20` |
| `boot2_lba` | `0x40` |
| `boot2_byte_offset` | `0x8000` |
| root UFS byte offset | `0x18000` |

## Filesystem Difference

Rhapsody DR2 i386 does not use OPENSTEP's byte-swapped UFS layout. Both boot2
and the kernel use BSD/FFS-native little-endian UFS1. Early Darwin roots are
not identical to that Rhapsody/i386 shape: the local Darwin 0.3 and Darwin
6.0.2 boot-helper UFS images are big-endian UFS1, matching their Apple
partition/boot lineage rather than the RDR/i386 floppy layout.

Evidence:

| Field | Rhapsody/RDR value |
| --- | --- |
| UFS1 magic | `0x00011954`, stored little-endian as `54 19 01 00` |
| superblock magic offset | `0x55c` |
| `fs_bsize` offset | `0x30` |
| `fs_fsize` offset | `0x34` |
| `fs_frag` offset | `0x38` |
| install floppy root | `fs_bsize=8192`, `fs_fsize=1024`, `fs_frag=8` |
| CD/front root | `fs_bsize=8192`, `fs_fsize=2048`, `fs_frag=4` |
| Darwin 0.3 root | APM `Apple_Rhapsody_UFS` at `0x108b8800`; UFS root at `0x10908800`; superblock at `0x1090a800`; big-endian `8192/2048/4` |
| Darwin 6.0.2 `cdboot.dmg` helper | UFS root at `0x3c000`; superblock at `0x3e000`; big-endian `4096/1024/4` |

Kernel evidence from Ghidra:

- `_vfs_mountroot` at `0x00105e54` first calls a root-mount hook if present,
  then iterates the filesystem configuration list and invokes each fs
  `mountroot` callback. Failure text is `%s_mountroot failed: %d`.
- `_ffs_mountroot` at `0x0015f424` creates a block-device vnode, allocates the
  root mount structure via `vfs_rootmountalloc`, calls `_ffs_mountfs`, then
  links the mount into the global mount list and calls `_ffs_statfs`.
- Kernel strings include `cd9660_mountroot`, `nfs_mountroot`, and `UFS mount`,
  so Rhapsody's root path is BSD VFS/FFS, not the OPENSTEP-only UFS handoff.

Darwin evidence:

- `Darwin-0.3.toast` has a valid big-endian UFS1 root under the APM
  `Apple_Rhapsody_UFS` partition. The root contains `/mach_kernel`,
  `/System/Library`, and `/usr`, so it satisfies the current Darwin root
  contract for BootE/XNU probing.
- `Darwin_6_0_2_x86.iso` was mastered with hard-disk El Torito booting and a
  nested `cdboot.dmg`. The ISO root carries a fat `mach_kernel`, while the
  boot-helper UFS carries `mach_kernel.rcz` and early boot support files.
- Darwin 6.0.2 kernel strings identify `Darwin Kernel Version 6.0` and
  `xnu-10-1-root.obj/RELEASE_I386`; the same image also carries a PowerPC
  slice.

## Driver Difference

Rhapsody DR2 keeps the familiar DriverKit media shape but changes the kernel
side around it.

Boot2 driver strings:

```text
/usr/standalone/i386/sarld
/private/Drivers/i386
/usr/Devices/System.config/Default.table
/private/Drivers/i386/System.config/Default.table
%s/System.config/InstallHints/%s.table
/private/Drivers/i386/%s.config/%s_reloc
Can't link driver %s without sarld
```

Rhapsody CD/front root contains:

```text
/private/Drivers/i386/System.config/Default.table
/private/Drivers/i386/System.config/Instance0.table
/private/Drivers/i386/*/*.config/*_reloc
```

The local Rhapsody CD/front root does not contain `/usr/Devices`, so boot2's
`/usr/Devices` path is a fallback/compatibility search path rather than the
required DR2 media layout.

Kernel evidence:

- Rhapsody DR2 kernel identifies as:
  `Rhapsody Operating System Release 5.1:
  Fri Apr 17 13:07:52 PDT 1998; root(rcbuilder):Objects/kernel-105.6.obj~2/RELEASE_I386`
- Kernel strings include `driverkit-115`, `driverKitVersionForDriverNamed:`,
  `WARNING: driver %s uses incompatible DriverKit version %d`, and
  `WARNING: No config table in KERNBOOTSTRUCT!`.
- Ghidra disassembly confirms exported kernel functions for DriverKit MIG
  entry points such as `_kern_IOGetDriverConfig`, `_kern_IOProbeDriver`, and
  `_kern_IOUnloadDriver`.

Darwin changes the driver lane substantially. Darwin 6.0.2 boot media names
`Extensions.mkext`, `System/Library/Extensions`, kext bundles, `IOCatalogue`,
`IOKitBSDInit`, `IOMedia`, and `Apple_UFS`. Its boot strings include both
`Apple UFS` and `Apple HFS` paths, while the kernel strings include IOKit,
kmod, and kext-loading machinery. That is not a drop-in replacement for the
Rhapsody DR2 `sarld` plus `*_reloc` DriverKit path.

Darwin 0.3 bridges the eras but is still not an i386 Rhapsody installer
kernel. Its image layout is PowerPC/OpenFirmware/APM-oriented, with HFS boot
partitions and a big-endian `Apple_Rhapsody_UFS` root. Package/string evidence
shows DriverKit-era lineage such as `driverkit_139.1-3`, but the media handoff
is not the RDR/i386 floppy/CD path.

## Compatibility Matrix

| Family | Filesystem | Driver/config media | Kernel handoff implication |
| --- | --- | --- | --- |
| NeXTStep/OPENSTEP Mach | byte-swapped NeXT/openstep UFS | `/private/Drivers/i386/*.config`, `System.config`, `*_reloc`, `sarld` | OPENSTEP kernel expects legacy KERNBOOTSTRUCT and OPENSTEP UFS semantics. |
| Rhapsody DR2 i386 | native little-endian BSD 4.4 UFS1 | Similar DriverKit `.config` layout, plus boot2 fallback probes under `/usr/Devices` | Rhapsody kernel uses BSD VFS/FFS root and DriverKit version checks. |
| Darwin 0.3 PPC | big-endian `Apple_Rhapsody_UFS` plus HFS/APM boot partitions | Transitional DriverKit-era package lineage, but OpenFirmware/APM media shape | Useful bridge evidence for UFS and package layout; not an x86 installer kernel lane. |
| Darwin 6.0.2 x86 | ISO plus nested big-endian Apple Boot/UFS helper; fat kernel on ISO root | `Extensions.mkext`, kext bundles, IOKit catalog/init paths | Latest local x86 XNU lane; uses XNU boot args and IOKit/kext handoff, not Rhapsody `sarld`/`*_reloc`. |

## Current Recommendation

Use the newest kernel only within its compatible ABI lane:

- OPENSTEP media customization should keep the OPENSTEP Mach kernel and
  DriverKit/KERNBOOTSTRUCT path.
- Rhapsody DR2 installation/customization can use the Rhapsody DR2
  `kernel-105.6` kernel with native little-endian RDR UFS roots.
- Darwin 0.3 is useful as bridge evidence because it has a real
  `Apple_Rhapsody_UFS` root, but it is PowerPC/OpenFirmware/APM-oriented.
- Darwin 6.0.2 is the latest verified local x86 kernel lane. It is
  BootE-compatible as an i386 Mach-O/XNU test target, but it should be used for
  Darwin customization/package experiments rather than as a universal
  OPENSTEP/Rhapsody installer kernel.

A single universal latest kernel is not viable without a compatibility loader
that translates both filesystem format and driver/bootstrap ABI. The practical
path is a shared El Torito/BootE wrapper with per-family root and driver
handoff profiles: `openstep`, `rhapsody-dr2`, `darwin-0.3`, and
`darwin-6.x`.
