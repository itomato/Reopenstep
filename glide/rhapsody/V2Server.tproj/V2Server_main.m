#import "V2Server.h"

#import <driverkit/IODeviceMaster.h>
#import <mach/mach_init.h>
#import <mach/task_special_ports.h>
#import <servers/netname.h>
#import <stdio.h>
#import <string.h>
#import <syslog.h>

extern boolean_t V2Server_server(msg_header_t *request, msg_header_t *reply);

static void
discoverDevices(void)
{
    IODeviceMaster *master = [IODeviceMaster new];
    unsigned int index;

    for (index = 0; index < V2SERVER_MAX_DEVICES; index++) {
        IOObjectNumber objectNumber;
        IOString kind;
        IOString name;
        port_t devicePort = PORT_NULL;

        sprintf(name, "Voodoo2_%u", index);
        if ([master lookUpByDeviceName:name objectNumber:&objectNumber
                            deviceKind:&kind] != IO_R_SUCCESS)
            break;
        if ([master createMachPort:&devicePort objectNumber:objectNumber]
            != IO_R_SUCCESS)
            break;
        if (V2ServerAddDevice(devicePort) != KERN_SUCCESS)
            break;
        syslog(LOG_NOTICE, "V2Server: found %s", name);
    }
    [master free];
}

int
main(int argc, char **argv)
{
    port_t serverPort = PORT_NULL;
    port_t notifyPort = PORT_NULL;
    cthread_t cleanupThread;
    kern_return_t result;
    union { msg_header_t head; unsigned char bytes[MSG_SIZE_MAX]; } request;
    union { msg_header_t head; unsigned char bytes[MSG_SIZE_MAX]; } reply;

    openlog("V2Server", LOG_PID, LOG_DAEMON);
    result = netname_look_up(name_server_port, "", "V2Driver",
                             &V2KernelDriverPort);
    if (result != KERN_SUCCESS || V2KernelDriverPort == PORT_NULL) {
        syslog(LOG_ERR, "cannot find V2Driver kernel port: %d", result);
        return 1;
    }

    result = port_allocate(task_self(), &serverPort);
    if (result != KERN_SUCCESS)
        return 1;
    result = netname_check_in(name_server_port, "Voodoo2Server",
                              task_self(), serverPort);
    if (result != KERN_SUCCESS) {
        syslog(LOG_ERR, "cannot register Voodoo2Server port: %d", result);
        return 1;
    }

    result = port_allocate(task_self(), &notifyPort);
    if (result != KERN_SUCCESS ||
        task_set_notify_port(task_self(), notifyPort) != KERN_SUCCESS) {
        syslog(LOG_ERR, "cannot establish task notification port");
        return 1;
    }
    cleanupThread = cthread_fork(V2ServerCleanupThread, (any_t)notifyPort);
    cthread_detach(cleanupThread);

    discoverDevices();
    for (;;) {
        memset(&request, 0, sizeof(request));
        request.head.msg_size = sizeof(request);
        request.head.msg_local_port = serverPort;
        result = msg_receive(&request.head, MSG_OPTION_NONE, 0);
        if (result != RCV_SUCCESS)
            continue;
        memset(&reply, 0, sizeof(reply));
        if (!V2Server_server(&request.head, &reply.head))
            continue;
        if (reply.head.msg_remote_port != PORT_NULL)
            msg_send(&reply.head, MSG_OPTION_NONE, 0);
    }
}
