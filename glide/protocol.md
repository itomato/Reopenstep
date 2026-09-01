# Reconstructed Voodoo2 protocols

The interfaces below were recovered from the generated MIG server dispatchers
in the PPC `Voodoo2_reloc` and `V2Server` binaries.  Offsets are offsets in the
old Mach message layout used by Rhapsody.

## Kernel service: `V2Driver`, subsystem 67000

| ID | Routine | Request bytes | Arguments after server port | Reply bytes |
|---:|---|---:|---|---:|
| 67000 | `ReadConfigLong` | 40 | device, register | 40 (value) |
| 67001 | `WriteConfigLong` | 48 | device, register, value | 32 |
| 67002 | `ReadConfig` | 32 | device | 292 (64 words) |
| 67003 | `PrintDeviceName` | 32 | device | 32 |
| 67004 | `PrintDeviceProperty` | 40 | device, property | 32 |

The original `ReadConfig` implementation is a success-returning stub and does
not fill its 256-byte result.  The reconstructed driver fills it because that
is safer and makes the interface useful.  `PrintDeviceName` and
`PrintDeviceProperty` were diagnostics for the PPC IORegistry; their i386
versions report the DriverKit device and its memory ranges.

`Load_Commands.sect` wires the loadable and installs `V2Driver_server` with an
`SMAP` command.

## User service: `V2Server`, subsystem 67100

| ID | Routine | Request bytes | Result |
|---:|---|---:|---|
| 67100 | `CountDevices` | 24 | one device-count word |
| 67101 | `ReadConfigLong` | 40 | one value word |
| 67102 | `WriteConfigLong` | 48 | status only |
| 67103 | `MapDeviceMemory` | 48, complex | mapped address and length |

`MapDeviceMemory` takes a target task send right, device index, and a
reset-on-disconnect flag.  The PPC server records one owner task per device,
maps the device's first memory range into that task, and rejects a second
owner.  A task-death notification clears ownership.  If reset was requested,
the cleanup path forks and performs a short Glide initialize/query/select/
shutdown cycle to return the board to a quiet state.

The server's internal device record is 0x60 bytes: device port at 0x00, memory
range count at 0x04, range storage from 0x08, owner task at 0x58, and reset flag
at 0x5c.  `V2Server.tproj/V2Server.defs` captures the recovered wire contract.
The reconstructed server implements single-owner mapping and task-death
cleanup.  Its deferred-reset log is intentional: the original reset path calls
Glide. The i386 framework source now exists, but that reset path remains
disabled until the framework native-links and can be safely made a V2Server
dependency.
