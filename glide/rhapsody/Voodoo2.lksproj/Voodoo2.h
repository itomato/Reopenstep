#import <driverkit/IODirectDevice.h>

#define V2_MAX_DEVICES 2
#define V2_PCI_COMMAND_STATUS 0x04
#define V2_PCI_COMMAND_MEMORY 0x00000002

@interface Voodoo2 : IODirectDevice
{
}

+ (BOOL)probe;
+ (BOOL)probe:deviceDescription;
- initFromDeviceDescription:deviceDescription;
- (port_t)devicePort;
- (IOReturn)createMachPort:(port_t *)machPort;

@end
