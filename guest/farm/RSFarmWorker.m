#import <Foundation/Foundation.h>
#import "RSFarmProtocol.h"

static NSDictionary *RSRunJob(NSDictionary *job, NSString *sharedRoot) {
    NSString *snapshot = [job objectForKey:@"snapshot"];
    NSString *project = [job objectForKey:@"project"];
    NSString *target = [job objectForKey:@"target"];
    NSString *architecture = [job objectForKey:@"architecture"];
    NSString *jobID = [job objectForKey:@"jobID"];
    NSString *directory = [sharedRoot stringByAppendingPathComponent:
        [NSString stringWithFormat:@"snapshots/%@/%@", snapshot, project]];
    NSString *logPath = [sharedRoot stringByAppendingPathComponent:
        [NSString stringWithFormat:@"logs/%@.log", jobID]];
    NSFileHandle *log;
    NSTask *task;
    int status;
    [[NSFileManager defaultManager] createDirectoryAtPath:[logPath stringByDeletingLastPathComponent] attributes:nil];
    [[NSFileManager defaultManager] createFileAtPath:logPath contents:[NSData data] attributes:nil];
    log = [NSFileHandle fileHandleForWritingAtPath:logPath];
    task = [[[NSTask alloc] init] autorelease];
    [task setCurrentDirectoryPath:directory];
    [task setLaunchPath:@"/usr/bin/make"];
    [task setArguments:[NSArray arrayWithObjects:target,
        [NSString stringWithFormat:@"ARCHS=%@", architecture], nil]];
    [task setStandardOutput:log]; [task setStandardError:log];
    NS_DURING
        [task launch]; [task waitUntilExit]; status = [task terminationStatus];
    NS_HANDLER
        [log closeFile];
        return [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithBool:NO], @"success",
            [NSNumber numberWithBool:YES], @"infrastructureFailure", [localException reason], @"message", logPath, @"log", nil];
    NS_ENDHANDLER
    [log closeFile];
    return [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithBool:(status == 0)], @"success",
        [NSNumber numberWithBool:NO], @"infrastructureFailure", [NSNumber numberWithInt:status], @"exitStatus", logPath, @"log", nil];
}

int main(int argc, const char **argv) {
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    NSString *name = argc > 1 ? [NSString stringWithCString:argv[1]] : [[NSHost currentHost] name];
    NSString *host = argc > 2 ? [NSString stringWithCString:argv[2]] : nil;
    NSString *root = argc > 3 ? [NSString stringWithCString:argv[3]] : @"/Net/buildmaster/ReopenstepFarm";
    id controller = [NSConnection rootProxyForConnectionWithRegisteredName:@"ReopenstepFarmController" host:host];
    NSDictionary *capabilities = [NSDictionary dictionaryWithObjectsAndKeys:
        [NSArray arrayWithObjects:@"m68k", @"i386", @"hppa", @"sparc", nil], @"architectures",
        [NSNumber numberWithInt:1], @"slots", nil];
    if (!controller) { NSLog(@"cannot connect to controller"); [pool release]; return 1; }
    [controller setProtocolForProxy:@protocol(RSFarmController)];
    if (![controller registerWorker:name capabilities:capabilities]) { [pool release]; return 1; }
    for (;;) {
        NSAutoreleasePool *iteration = [[NSAutoreleasePool alloc] init];
        NSDictionary *job;
        [controller heartbeat:name];
        job = [controller nextJobForWorker:name];
        if (job) [controller finishJob:[job objectForKey:@"jobID"] result:RSRunJob(job, root)];
        [NSThread sleepUntilDate:[NSDate dateWithTimeIntervalSinceNow:5.0]];
        [iteration release];
    }
    [pool release]; return 0;
}
