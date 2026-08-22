# 86Box acceptance targets

The sibling `../Whitebox` tree is the reference 86Box port for NeXTSTEP and
OPENSTEP hardware. Its presets are intentionally kept outside this repository
so Whitebox remains the source of truth for emulated hardware and ROM assets.

The primary performance target is now the ASUS CUBX/440BX Socket 370 profile:
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

The Whitebox notes identify Matrox PCI IDs `102B:0519` (MGA-2064W) and
`102B:051A/051E` (MGA-1064SG), and its source includes Wingine, MGA, and Voodoo
device implementations. Reopenstep treats those as acceptance targets, not as
proof that the corresponding OpenStep driver packages are installed.
