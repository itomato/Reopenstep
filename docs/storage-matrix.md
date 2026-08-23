# Storage driver matrix

ReOpenStep treats storage as separate, testable compatibility lanes. “Newest”
means the newest driver for the controller's actual PCI identity, not the
driver with the highest version number across unrelated adapters.

| Lane | Driver | Controller identity | QEMU | 86Box/Whitebox |
|---|---|---|---|---|
| PIIX EIDE/ATAPI | EIDE 16.2 | Intel `1230/7010/7111` | i440FX PIIX IDE | AM-BX133 PIIX4E |
| AMD PCscsi | AMD PC SCSI 9 | AMD `1022:2020` | `am53c974` | unavailable |
| BusLogic MultiMaster | BusLogic 8 | BusLogic `104b:1040` | unavailable | BT-958D |
| BusLogic FlashPoint | BusLogicFP 7 | BusLogic `104b:8130` | unavailable | unavailable |
| Adaptec 2940 | Adaptec 19.2 | Adaptec `9004:0078` | unavailable | unavailable |

PIIX EIDE is the best current common denominator and the only lane that also
covers primary/secondary ATAPI. It should remain the default installer, while
AMD PCscsi and BT-958D get independent media and VM profiles. Mixing IDE and
SCSI disks in one acceptance machine makes persistence failures ambiguous.

CUBX is excluded from EIDE acceptance because Whitebox models its onboard CMD
PCI-0648 quad-channel controller; none of the available EIDE tables identify
that device. Adaptec 2940 and FlashPoint remain important real-hardware targets
but require future emulator devices or physical-machine testing.

For every lane, the startup image and installed root must agree on all three
inputs:

1. `System.config` names the boot driver.
2. The driver bundle contains the matching `_reloc` binary.
3. The selected `Default.table`/`Instance0.table` identifies the emulated PCI
   device and its correct bus type.
