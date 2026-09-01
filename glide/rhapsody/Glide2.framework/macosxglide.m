/*
 * THIS SOFTWARE IS SUBJECT TO COPYRIGHT PROTECTION AND IS OFFERED ONLY
 * PURSUANT TO THE 3DFX GLIDE GENERAL PUBLIC LICENSE. THERE IS NO RIGHT
 * TO USE THE GLIDE TRADEMARK WITHOUT PRIOR WRITTEN PERMISSION OF 3DFX
 * INTERACTIVE, INC. A COPY OF THIS LICENSE MAY BE OBTAINED FROM THE
 * DISTRIBUTOR OR BY CONTACTING 3DFX INTERACTIVE INC (info@3dfx.com).
 * THIS PROGRAM IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER
 * EXPRESSED OR IMPLIED. SEE THE 3DFX GLIDE GENERAL PUBLIC LICENSE FOR A
 * FULL TEXT OF THE NON-WARRANTY PROVISIONS.
 *
 * USE, DUPLICATION OR DISCLOSURE BY THE GOVERNMENT IS SUBJECT TO
 * RESTRICTIONS AS SET FORTH IN SUBDIVISION (C)(1)(II) OF THE RIGHTS IN
 * TECHNICAL DATA AND COMPUTER SOFTWARE CLAUSE AT DFARS 252.227-7013,
 * AND/OR IN SIMILAR OR SUCCESSOR CLAUSES IN THE FAR, DOD OR NASA FAR
 * SUPPLEMENT. UNPUBLISHED RIGHTS RESERVED UNDER THE COPYRIGHT LAWS OF
 * THE UNITED STATES.
 *
 * COPYRIGHT 3DFX INTERACTIVE, INC. 1999, ALL RIGHTS RESERVED
 *
 * Rhapsody/i386 platform layer reconstructed in 2026 from the public 3dfx
 * interfaces and observable behavior of Omni's PowerPC framework.
 */

#import <Foundation/Foundation.h>
#import <mach/mach.h>
#import <servers/netname.h>
#import <stdlib.h>
#import <string.h>

#import "V2Server.h"
#import "3dfx.h"
#define FX_DLL_DEFINITION
#import "fxdll.h"
#import "fxpci.h"

#define V2_SERVER_NAME "Voodoo2Server"
#define V2_MAX_DEVICES 10

enum {
    V2_PCI_NO_ERROR = 0,
    V2_PCI_CONNECT_ERROR,
    V2_PCI_DISCONNECT_ERROR,
    V2_PCI_COUNT_ERROR,
    V2_PCI_NO_CARD,
    V2_PCI_READ_ERROR,
    V2_PCI_WRITE_ERROR,
    V2_PCI_MAP_ERROR
};

FxU32 pciErrorCode = V2_PCI_NO_ERROR;
FxU32 pciVxdVer = 0;
FxBool pciLibraryInitialized = FXFALSE;

static port_t serverPort = PORT_NULL;
static FxU32 numberOfDevices;
static FxU32 *mappedDevices[V2_MAX_DEVICES];

const PciRegister PCI_VENDOR_ID        = { 0x00, 2, READ_ONLY };
const PciRegister PCI_DEVICE_ID        = { 0x02, 2, READ_ONLY };
const PciRegister PCI_COMMAND          = { 0x04, 2, READ_WRITE };
const PciRegister PCI_STATUS           = { 0x06, 2, READ_WRITE };
const PciRegister PCI_REVISION_ID      = { 0x08, 1, READ_ONLY };
const PciRegister PCI_CLASS_CODE       = { 0x09, 3, READ_ONLY };
const PciRegister PCI_CACHE_LINE_SIZE  = { 0x0c, 1, READ_WRITE };
const PciRegister PCI_LATENCY_TIMER    = { 0x0d, 1, READ_WRITE };
const PciRegister PCI_HEADER_TYPE      = { 0x0e, 1, READ_ONLY };
const PciRegister PCI_BIST             = { 0x0f, 1, READ_WRITE };
const PciRegister PCI_BASE_ADDRESS_0   = { 0x10, 4, READ_WRITE };
const PciRegister PCI_BASE_ADDRESS_1   = { 0x14, 4, READ_WRITE };
const PciRegister PCI_IO_BASE_ADDRESS  = { 0x18, 4, READ_WRITE };
const PciRegister PCI_SUBVENDOR_ID     = { 0x2c, 4, READ_ONLY };
const PciRegister PCI_SUBSYSTEM_ID     = { 0x2e, 2, READ_ONLY };
const PciRegister PCI_ROM_BASE_ADDRESS = { 0x30, 4, READ_WRITE };
const PciRegister PCI_CAP_PTR          = { 0x34, 4, READ_WRITE };
const PciRegister PCI_INTERRUPT_LINE   = { 0x3c, 1, READ_WRITE };
const PciRegister PCI_INTERRUPT_PIN    = { 0x3d, 1, READ_ONLY };
const PciRegister PCI_MIN_GNT          = { 0x3e, 1, READ_ONLY };
const PciRegister PCI_MAX_LAT          = { 0x3f, 1, READ_ONLY };
const PciRegister PCI_FAB_ID           = { 0x40, 1, READ_ONLY };
const PciRegister PCI_CONFIG_STATUS    = { 0x4c, 4, READ_WRITE };
const PciRegister PCI_CONFIG_SCRATCH   = { 0x50, 4, READ_WRITE };
const PciRegister PCI_AGP_CAP_ID       = { 0x54, 4, READ_ONLY };
const PciRegister PCI_AGP_STATUS       = { 0x58, 4, READ_ONLY };
const PciRegister PCI_AGP_CMD          = { 0x5c, 4, READ_WRITE };
const PciRegister PCI_ACPI_CAP_ID      = { 0x60, 4, READ_ONLY };
const PciRegister PCI_CNTRL_STATUS     = { 0x64, 4, READ_WRITE };
const PciRegister PCI_SST1_INIT_ENABLE = { 0x40, 4, READ_WRITE };
const PciRegister PCI_SST1_BUS_SNOOP_0 = { 0x44, 4, READ_WRITE };
const PciRegister PCI_SST1_BUS_SNOOP_1 = { 0x48, 4, READ_WRITE };
const PciRegister PCI_SST1_CFG_STATUS  = { 0x4c, 4, READ_WRITE };

static const char *errorStrings[] = {
    "No Error",
    "Cannot find V2Server port",
    "Cannot disconnect from V2Server port",
    "Error counting cards in machine",
    "No card found",
    "Error reading config data",
    "Error writing config data",
    "Error mapping card memory"
};

FX_ENTRY const char * FX_CALL
pciGetErrorString(void)
{
    return errorStrings[(pciErrorCode <= V2_PCI_MAP_ERROR) ? pciErrorCode : 0];
}

FX_ENTRY FxU32 FX_CALL
pciGetErrorCode(void)
{
    return pciErrorCode;
}

FX_ENTRY FxBool FX_CALL
pciOpen(void)
{
    kern_return_t result;

    if (pciLibraryInitialized)
        return FXTRUE;
    result = netname_look_up(name_server_port, "", V2_SERVER_NAME, &serverPort);
    if (result != KERN_SUCCESS) {
        pciErrorCode = V2_PCI_CONNECT_ERROR;
        return FXFALSE;
    }
    result = V2Client_CountDevices(serverPort, &numberOfDevices);
    if (result != KERN_SUCCESS) {
        port_deallocate(task_self(), serverPort);
        serverPort = PORT_NULL;
        pciErrorCode = V2_PCI_COUNT_ERROR;
        return FXFALSE;
    }
    if (numberOfDevices == 0) {
        pciErrorCode = V2_PCI_NO_CARD;
        return FXFALSE;
    }
    if (numberOfDevices > V2_MAX_DEVICES)
        numberOfDevices = V2_MAX_DEVICES;
    pciErrorCode = V2_PCI_NO_ERROR;
    pciLibraryInitialized = FXTRUE;
    return FXTRUE;
}

FX_ENTRY FxBool FX_CALL
pciClose(void)
{
    kern_return_t result;

    result = port_deallocate(task_self(), serverPort);
    if (result != KERN_SUCCESS) {
        pciErrorCode = V2_PCI_DISCONNECT_ERROR;
        return FXFALSE;
    }
    serverPort = PORT_NULL;
    numberOfDevices = 0;
    pciLibraryInitialized = FXFALSE;
    memset(mappedDevices, 0, sizeof(mappedDevices));
    pciErrorCode = V2_PCI_NO_ERROR;
    return FXTRUE;
}

FX_ENTRY FxBool FX_CALL
pciGetConfigData(PciRegister reg, FxU32 device, FxU32 *data)
{
    FxU32 value;
    FxU32 shift;
    kern_return_t result;

    if (!pciLibraryInitialized || device >= numberOfDevices || data == 0)
        return FXFALSE;
    result = V2Client_ReadConfigLong(serverPort, device,
                                     reg.regAddress & ~3U, &value);
    if (result != KERN_SUCCESS) {
        pciErrorCode = V2_PCI_READ_ERROR;
        return FXFALSE;
    }
    shift = (reg.regAddress & 3U) * 8U;
    value >>= shift;
    if (reg.sizeInBytes < 4)
        value &= (1U << (reg.sizeInBytes * 8U)) - 1U;
    *data = value;
    pciErrorCode = V2_PCI_NO_ERROR;
    return FXTRUE;
}

FX_ENTRY FxBool FX_CALL
pciSetConfigData(PciRegister reg, FxU32 device, FxU32 *data)
{
    FxU32 oldValue;
    FxU32 value;
    FxU32 shift;
    FxU32 mask;
    kern_return_t result;

    if (!pciLibraryInitialized || device >= numberOfDevices || data == 0 ||
        reg.sizeInBytes == 0 || reg.sizeInBytes > 4 ||
        (reg.regAddress & 3U) + reg.sizeInBytes > 4) {
        pciErrorCode = V2_PCI_WRITE_ERROR;
        return FXFALSE;
    }
    shift = (reg.regAddress & 3U) * 8U;
    if (reg.sizeInBytes == 4) {
        value = *data;
    } else {
        result = V2Client_ReadConfigLong(serverPort, device,
                                         reg.regAddress & ~3U, &oldValue);
        if (result != KERN_SUCCESS) {
            pciErrorCode = V2_PCI_WRITE_ERROR;
            return FXFALSE;
        }
        mask = ((1U << (reg.sizeInBytes * 8U)) - 1U) << shift;
        value = (oldValue & ~mask) | ((*data << shift) & mask);
    }
    result = V2Client_WriteConfigLong(serverPort, device,
                                      reg.regAddress & ~3U, value);
    if (result != KERN_SUCCESS) {
        pciErrorCode = V2_PCI_WRITE_ERROR;
        return FXFALSE;
    }
    pciErrorCode = V2_PCI_NO_ERROR;
    return FXTRUE;
}

FX_ENTRY FxBool FX_CALL
pciFindCardMulti(FxU32 vendorID, FxU32 deviceID, FxU32 *device,
                 FxU32 cardNumber)
{
    if (!pciOpen() || device == 0 || cardNumber >= numberOfDevices) {
        pciErrorCode = V2_PCI_NO_CARD;
        return FXFALSE;
    }
    *device = cardNumber;
    pciErrorCode = V2_PCI_NO_ERROR;
    return FXTRUE;
}

FX_ENTRY FxU32 * FX_CALL
pciMapCardMulti(FxU32 vendorID, FxU32 deviceID, FxI32 requestedLength,
                FxU32 *device, FxU32 cardNumber, FxU32 addressNumber)
{
    vm_address_t address;
    vm_size_t length;
    kern_return_t result;

    if (addressNumber != 0 ||
        !pciFindCardMulti(vendorID, deviceID, device, cardNumber)) {
        pciErrorCode = V2_PCI_MAP_ERROR;
        return 0;
    }
    if (mappedDevices[cardNumber] != 0)
        return mappedDevices[cardNumber];
    result = V2Client_MapDeviceMemory(serverPort, task_self(), cardNumber,
                                      &address, &length, TRUE);
    if (result != KERN_SUCCESS) {
        pciErrorCode = V2_PCI_MAP_ERROR;
        return 0;
    }
    mappedDevices[cardNumber] = (FxU32 *)address;
    pciErrorCode = V2_PCI_NO_ERROR;
    return mappedDevices[cardNumber];
}

FX_ENTRY void FX_CALL
pciUnmapPhysical(unsigned long address, FxU32 length)
{
    /* V2Server owns the mapping until this task's port is destroyed. */
}

FX_ENTRY FxBool FX_CALL
pciLinearRangeSetPermission(const unsigned long address, const FxU32 length,
                            const FxBool writeable)
{
    return FXFALSE;
}

FX_ENTRY FxBool FX_CALL
pciSetPassThroughBase(FxU32 *baseAddress, FxU32 length)
{
    return FXFALSE;
}

/* Omni disabled the x86 MTRR path; V2Server maps the BAR uncached. */
FX_ENTRY FxBool FX_CALL
pciFindMTRRMatch(FxU32 base, FxU32 length, PciMemType type, FxU32 *number)
{
    return FXFALSE;
}

FX_ENTRY FxBool FX_CALL
pciFindFreeMTRR(FxU32 *number)
{
    return FXFALSE;
}

FX_ENTRY FxBool FX_CALL
pciSetMTRR(FxU32 number, FxU32 base, FxU32 length, PciMemType type)
{
    return FXFALSE;
}

FX_ENTRY FxBool FX_CALL
pciSetMTRRAmdK6(FxU32 number, FxU32 base, FxU32 length, PciMemType type)
{
    return FXFALSE;
}

FX_ENTRY FxBool FX_CALL
pciOutputDebugString(const char *message)
{
    return FXFALSE;
}

extern FxBool sst1InitCheckBoard(FxU32 *baseAddress);

FX_ENTRY FxBool FX_CALL
sst1InitCaching(FxU32 *baseAddress, FxBool enable)
{
    (void)sst1InitCheckBoard(baseAddress);
    return FXFALSE;
}

/* sst1InitGetenv is built with getenv renamed to this function. */
char *
GetDefault(const char *key)
{
    NSAutoreleasePool *pool;
    NSString *keyString;
    NSString *value;
    char *copy;
    unsigned int length;

    pool = [[NSAutoreleasePool alloc] init];
    keyString = [[NSString alloc] initWithCString:key];
    value = [[NSUserDefaults standardUserDefaults]
             stringForKey:keyString];
    if (value == 0) {
        [keyString release];
        [pool release];
        return 0;
    }
    length = [value length];
    copy = malloc(length + 1);
    if (copy != 0)
        [value getCString:copy];
    [keyString release];
    [pool release];
    return copy;
}
