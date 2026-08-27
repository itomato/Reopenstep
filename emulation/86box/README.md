# 86Box acceptance targets

The sibling `../Whitebox` tree is the reference 86Box port for NeXTSTEP and
OPENSTEP hardware. Its presets are intentionally kept outside this repository
so Whitebox remains the source of truth for emulated hardware and ROM assets.

The primary performance target is now the AM-BX133/440BX Socket 370 profile:
`whitebox-s370-celeron533-matrox-voodoo2.cfg`. It uses Whitebox's eligible
`celeron_mendocino` family at 533 MHz, 128 MB RAM, Matrox G100 primary video,
and a Voodoo2 add-on. This is an experimental fast build target; use the
Epson/Canon profiles when diagnosing storage or installer failures.

Start with the stable storage targets:

- `../Whitebox/tools/whitebox/presets/whitebox-486-isa-epson-nx.cfg`
  — Epson NX, dual IDE, on-board Wingine, 486DX2/66.
- `../Whitebox/tools/whitebox/presets/whitebox-486-vlb-canon-object-station-41.cfg`
  — Canon object.station 41, BusLogic VLB SCSI, PCnet-32, WSS, Wingine plan.

For graphics experiments after a base install:

- `whitebox-full-tilt-voodoo2.cfg` — Matrox Millennium II plus Voodoo2.
- `whitebox-s370-voodoo2-full-tilt.cfg` — Matrox G100 plus Voodoo2.

Launch a reference machine with:

```sh
./reopenstep vm 86box \
  --config ../Whitebox/tools/whitebox/presets/whitebox-486-isa-epson-nx.cfg \
  --print-command
```

86Box accepts a configuration with `-C`; the preset itself owns disk and CD
attachment details. Keep the first install target conservative: Epson NX or
Canon object.station storage, 32 MB RAM, and VGA/S3 fallback. Add Matrox or
Voodoo only after the base system boots, because those devices require their
matching OpenStep bundles and are not generic VGA replacements.

For the EIDE installer, attach exactly one target disk as IDE primary master
(`0:0`, type `ide`) and the ATAPI CD-ROM as secondary master (`1:0`). Never
attach the same VHD through both IDE and SCSI, and never mark a hard disk as
`atapi`. After installation, eject the ISO or change the firmware boot order
to the hard disk.

If an earlier installation omitted EIDE from its installed boot table, boot
it once with `out/reopenstep-4.2-eide-rescue-piix.iso`. That startup image preloads
EIDE and uses `rootdev=sd0a`. Once the installed root is available, run
`guest/master/install-eide-boot.sh` with the target root and a complete beta
`EIDE.config` bundle to make subsequent hard-disk boots independent of the
rescue ISO.

The 86Box wrapper encodes this lifecycle directly:

```sh
scripts/run-openstep-autoboot-86box.sh install
scripts/run-openstep-autoboot-86box.sh rescue
scripts/run-openstep-autoboot-86box.sh disk
```

BootE has a separate keyboard-debug lane using the Patch 4/VBE UFS fixture,
CUBX/PIIX4E, Matrox Millennium II, and the explicit
`keyboard_ps2` device:

```sh
REOPENSTEP_86BOX_LOG=out/86box-boote-keyboard.log \
  scripts/run-openstep-autoboot-86box.sh boote
```

The mode mounts `out/boote/boote-vesa.iso` as primary-slave ATAPI and
`out/boote/openstep-user-patch4-vesa.raw` as primary-master IDE. This matches
the topology of the working interactive 86Box configuration. The raw disk
is an existing fixture and is not created or converted by the wrapper. Select
`CDROM, C, A` under CUBX BIOS Setup (Delete, then BIOS Features Setup) if saved
NVRAM prefers the hard disk. `DISK BOOT FAILURE` at this stage means the BIOS
attempted the NeXT UFS disk directly; that fixture intentionally relies on the
BootE CD and has no independently usable PC MBR boot path. The wrapper uses the
portable 86Box VM-directory interface, generating
`out/86box-cubx-boote-vm/86box.cfg` and launching that directory with `-P`;
the macOS frontend does not reliably honor standalone `-C` configurations.
Do not mount the BootE ISO in the older full-tilt `Reopenstep` VM for this
acceptance test. Its SiI 0648, BusLogic, PCnet, and Voodoo devices distinguish
it from the isolated PIIX/Matrox profile, and its installed VHD is not the
NeXT-labeled UFS fixture BootE expects. In that configuration `cdboot: done`
only proves the El Torito payload loaded; the subsequent BIOS boot cycle means
BootE did not select the expected UFS volume. The isolated profile's active
disk and CD stay on the Intel `8086:7111` PIIX primary channel. CUBX also
exposes its onboard CMD `1095:0648` tertiary and quaternary controller, but
this lane attaches nothing to it until an appropriate OPENSTEP table is
available. PCnet, BusLogic, and 3dfx remain absent from the isolated test.
For controller-level traces, a Whitebox/86Box development build must also
compile `src/device/kbc_at.c` with `ENABLE_KBC_AT_LOG`; `-L` alone only captures
logging compiled into the emulator.

The combined v5 lane creates a separate dynamic VHD with 4095/16/63 geometry
(just under 2 GiB), leaving enough room for the User system and all five
Developer packages. Older 504 MiB test disks remain untouched.

`disk` leaves the virtual CD drive empty so firmware cannot fall back into the
installer after a successful installation.

For the beta EIDE acceptance test on CUBX, use only IDE channels `0:0` and
`0:1`, which are served by the supported Intel PIIX4E controller
(`8086:7111`). Whitebox models the board's CMD PCI-0648 as tertiary and
quaternary IDE; those channels remain empty because this EIDE bundle has no
matching PCI configuration table.

The Whitebox notes identify Matrox PCI IDs `102B:0519` (MGA-2064W) and
`102B:051A/051E` (MGA-1064SG), and its source includes Wingine, MGA, and Voodoo
device implementations. Reopenstep treats those as acceptance targets, not as
proof that the corresponding OpenStep driver packages are installed.
