#import "Voodoo2.h"

#import <driverkit/IODeviceDescription.h>
#import <driverkit/generalFuncs.h>
#import <driverkit/i386/IOPCIDirectDevice.h>
#import <mach/kern_return.h>
#import <stdio.h>

static Voodoo2 *v2Devices[V2_MAX_DEVICES];
static unsigned int v2DeviceCount;

static Voodoo2 *
V2DeviceAt(unsigned int index)
{
    if (index >= v2DeviceCount)
        return nil;
    return v2Devices[index];
}

@implementation Voodoo2

+ (BOOL)probe
{
    return NO;
}

+ (BOOL)probe:deviceDescription
{
    Voodoo2 *device;

    if (v2DeviceCount >= V2_MAX_DEVICES) {
        IOLog("Voodoo2: refusing unit %u (maximum is %u)\n",
              v2DeviceCount, V2_MAX_DEVICES);
        return NO;
    }

    device = [[self alloc] initFromDeviceDescription:deviceDescription];
    return device != nil;
}

- initFromDeviceDescription:deviceDescription
{
    unsigned long commandStatus;
    unsigned int unit;
    unsigned int rangeIndex;
    unsigned int rangeCount;
    IORange *ranges;
    char name[32];

    if (v2DeviceCount >= V2_MAX_DEVICES) {
        [self free];
        return nil;
    }

    self = [super initFromDeviceDescription:deviceDescription];
    if (self == nil)
        return nil;

    unit = v2DeviceCount;
    sprintf(name, "Voodoo2_%u", unit);
    [self setName:name];
    [self setUnit:unit];
    [self setDeviceKind:"Voodoo2"];

    if ([self registerDevice] == nil) {
        IOLog("%s: registerDevice failed\n", name);
        [self free];
        return nil;
    }

    v2Devices[unit] = self;
    v2DeviceCount++;
    ranges = [deviceDescription memoryRangeList];
    rangeCount = [deviceDescription numMemoryRanges];
    for (rangeIndex = 0; rangeIndex < rangeCount; rangeIndex++)
        IOLog("%s: memory range %u = 0x%x + 0x%x\n", name, rangeIndex,
              ranges[rangeIndex].start, ranges[rangeIndex].size);

    if ([self getPCIConfigData:&commandStatus
                    atRegister:V2_PCI_COMMAND_STATUS] != IO_R_SUCCESS) {
        IOLog("%s: cannot read PCI command register\n", name);
    } else if (!(commandStatus & V2_PCI_COMMAND_MEMORY)) {
        commandStatus |= V2_PCI_COMMAND_MEMORY;
        if ([self setPCIConfigData:commandStatus
                       atRegister:V2_PCI_COMMAND_STATUS] != IO_R_SUCCESS)
            IOLog("%s: cannot enable PCI memory decoding\n", name);
    }

    IOLog("%s: registered, device port %u\n", name, [self devicePort]);
    return self;
}

- (port_t)devicePort
{
    return [[self deviceDescription] devicePort];
}

- (IOReturn)createMachPort:(port_t *)machPort
{
    if (machPort == 0)
        return IO_R_INVALID_ARG;
    *machPort = [self devicePort];
    return (*machPort != PORT_NULL) ? IO_R_SUCCESS : IO_R_NO_DEVICE;
}

@end

kern_return_t
V2Driver_ReadConfigLong(port_t serverPort, unsigned int deviceIndex,
                        unsigned int address, unsigned int *value)
{
    Voodoo2 *device = V2DeviceAt(deviceIndex);
    unsigned long data;

    if (device == nil || value == 0 || (address & 3) || address > 252)
        return KERN_FAILURE;
    if ([device getPCIConfigData:&data atRegister:(unsigned char)address]
        != IO_R_SUCCESS)
        return KERN_FAILURE;
    *value = (unsigned int)data;
    return KERN_SUCCESS;
}

kern_return_t
V2Driver_WriteConfigLong(port_t serverPort, unsigned int deviceIndex,
                         unsigned int address, unsigned int value)
{
    Voodoo2 *device = V2DeviceAt(deviceIndex);

    if (device == nil || (address & 3) || address > 252)
        return KERN_FAILURE;
    if ([device setPCIConfigData:(unsigned long)value
                      atRegister:(unsigned char)address] != IO_R_SUCCESS)
        return KERN_FAILURE;
    return KERN_SUCCESS;
}

kern_return_t
V2Driver_ReadConfig(port_t serverPort, unsigned int deviceIndex,
                    unsigned int config[64])
{
    unsigned int address;

    if (V2DeviceAt(deviceIndex) == nil || config == 0)
        return KERN_FAILURE;
    for (address = 0; address < 256; address += 4) {
        if (V2Driver_ReadConfigLong(serverPort, deviceIndex, address,
                                    &config[address / 4]) != KERN_SUCCESS)
            return KERN_FAILURE;
    }
    return KERN_SUCCESS;
}

kern_return_t
V2Driver_PrintDeviceName(port_t serverPort, unsigned int deviceIndex)
{
    Voodoo2 *device = V2DeviceAt(deviceIndex);

    if (device == nil)
        return KERN_FAILURE;
    IOLog("Voodoo2[%u]: %s\n", deviceIndex, [device name]);
    return KERN_SUCCESS;
}

kern_return_t
V2Driver_PrintDeviceProperty(port_t serverPort, unsigned int deviceIndex,
                             unsigned int propertyIndex)
{
    Voodoo2 *device = V2DeviceAt(deviceIndex);
    IORange *ranges;
    unsigned int count;

    if (device == nil)
        return KERN_FAILURE;
    ranges = [[device deviceDescription] memoryRangeList];
    count = [[device deviceDescription] numMemoryRanges];
    if (propertyIndex >= count)
        return KERN_FAILURE;
    IOLog("Voodoo2[%u] range[%u] = 0x%x + 0x%x\n", deviceIndex,
          propertyIndex, ranges[propertyIndex].start, ranges[propertyIndex].size);
    return KERN_SUCCESS;
}
