#ifndef REOPENSTEP_V2SERVER_H
#define REOPENSTEP_V2SERVER_H

#import <driverkit/driverTypes.h>
#import <mach/cthreads.h>
#import <mach/mach.h>

#define V2SERVER_MAX_DEVICES 2
#define V2SERVER_MAX_RANGES 10
#define V2SERVER_QUERY_MAX_RANGES 15

typedef struct V2ServerDevice {
    port_t devicePort;
    unsigned int rangeCount;
    IORange ranges[V2SERVER_MAX_RANGES];
    port_t ownerTask;
    boolean_t resetOnDisconnect;
} V2ServerDevice;
/* This layout deliberately matches the original 0x60-byte PPC record. */
typedef char V2ServerDeviceRecordSize[(sizeof(V2ServerDevice) == 0x60) ? 1 : -1];

extern port_t V2KernelDriverPort;

kern_return_t V2ServerAddDevice(port_t devicePort);
void V2ServerReleaseOwner(port_t ownerTask);
any_t V2ServerCleanupThread(any_t argument);

kern_return_t V2Server_CountDevices(port_t serverPort,
                                    unsigned int *deviceCountOut);
kern_return_t V2Server_ReadConfigLong(port_t serverPort,
                                      unsigned int deviceIndex,
                                      unsigned int address,
                                      unsigned int *value);
kern_return_t V2Server_WriteConfigLong(port_t serverPort,
                                       unsigned int deviceIndex,
                                       unsigned int address,
                                       unsigned int value);
kern_return_t V2Server_MapDeviceMemory(port_t serverPort, port_t targetTask,
                                       unsigned int deviceIndex,
                                       vm_address_t *baseAddress,
                                       vm_size_t *length,
                                       boolean_t resetOnDisconnect);

#endif
