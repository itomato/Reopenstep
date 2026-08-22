#import <Foundation/Foundation.h>
#include <unistd.h>
#import "RSFarmProtocol.h"

static void RSPrint(id value) {
    NSData *data = [[value description] dataUsingEncoding:NSUTF8StringEncoding];
    write(1, [data bytes], [data length]); write(1, "\n", 1);
}

int main(int argc, const char **argv) {
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    NSString *command;
    id controller;
    if (argc < 2) { fprintf(stderr, "usage: rsfarm submit|status|logs|cancel|workers ...\n"); return 2; }
    command = [NSString stringWithCString:argv[1]];
    controller = [NSConnection rootProxyForConnectionWithRegisteredName:@"ReopenstepFarmController" host:nil];
    if (!controller) { fprintf(stderr, "cannot connect to farm controller\n"); return 1; }
    [controller setProtocolForProxy:@protocol(RSFarmController)];
    if ([command isEqual:@"submit"] && argc == 3) {
        NSDictionary *spec = [NSDictionary dictionaryWithContentsOfFile:[NSString stringWithCString:argv[2]]];
        if (!spec) { fprintf(stderr, "invalid OpenStep property-list build spec\n"); return 2; }
        RSPrint([controller submitBuild:spec]);
    } else if ([command isEqual:@"status"]) {
        RSPrint([controller jobs]);
    } else if ([command isEqual:@"workers"]) {
        RSPrint([controller workers]);
    } else if ([command isEqual:@"cancel"] && argc == 3) {
        return [controller cancelJob:[NSString stringWithCString:argv[2]]] ? 0 : 1;
    } else if ([command isEqual:@"logs"]) {
        RSPrint([controller jobs]);
    } else {
        fprintf(stderr, "invalid command or arguments\n"); return 2;
    }
    [pool release]; return 0;
}
