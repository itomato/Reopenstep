#import <Foundation/Foundation.h>
#import "RSFarmProtocol.h"

static BOOL RSSafeName(id value) {
    unsigned int i;
    NSCharacterSet *allowed;
    if (![value isKindOfClass:[NSString class]] || [(NSString *)value length] == 0) return NO;
    allowed = [NSCharacterSet characterSetWithCharactersInString:
        @"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.+-"];
    for (i = 0; i < [(NSString *)value length]; i++)
        if (![allowed characterIsMember:[(NSString *)value characterAtIndex:i]]) return NO;
    return YES;
}

@interface RSController : NSObject <RSFarmController> {
    NSMutableArray *_jobs;
    NSMutableDictionary *_workers;
    NSString *_statePath;
}
- (id)initWithStatePath:(NSString *)path;
- (void)reapWorkers:(NSTimer *)timer;
- (void)save;
@end

@implementation RSController
- (id)initWithStatePath:(NSString *)path {
    NSDictionary *state;
    NSEnumerator *enumerator;
    NSDictionary *item;
    self = [super init];
    if (!self) return nil;
    _statePath = [path copy];
    state = [NSDictionary dictionaryWithContentsOfFile:path];
    _jobs = [[NSMutableArray alloc] init];
    enumerator = [[state objectForKey:@"jobs"] objectEnumerator];
    while ((item = [enumerator nextObject])) [_jobs addObject:[NSMutableDictionary dictionaryWithDictionary:item]];
    _workers = [[NSMutableDictionary alloc] init];
    enumerator = [[state objectForKey:@"workers"] objectEnumerator];
    while ((item = [enumerator nextObject]))
        [_workers setObject:[NSMutableDictionary dictionaryWithDictionary:item] forKey:[item objectForKey:@"name"]];
    [NSTimer scheduledTimerWithTimeInterval:15.0 target:self selector:@selector(reapWorkers:) userInfo:nil repeats:YES];
    return self;
}
- (void)dealloc {
    [_jobs release]; [_workers release]; [_statePath release]; [super dealloc];
}
- (void)save {
    NSDictionary *state = [NSDictionary dictionaryWithObjectsAndKeys:_jobs, @"jobs", _workers, @"workers", nil];
    [state writeToFile:_statePath atomically:YES];
}
- (NSDictionary *)submitBuild:(NSDictionary *)spec {
    NSArray *architectures = [spec objectForKey:@"architectures"];
    NSString *snapshot = [spec objectForKey:@"snapshot"];
    NSString *project = [spec objectForKey:@"project"];
    NSString *target = [spec objectForKey:@"target"];
    NSString *profile = [spec objectForKey:@"profile"];
    NSEnumerator *enumerator;
    NSString *architecture;
    NSMutableArray *ids = [NSMutableArray array];
    if (!RSSafeName(snapshot) || !RSSafeName(project) || !RSSafeName(target) || !RSSafeName(profile))
        return [NSDictionary dictionaryWithObject:@"unsafe or missing build field" forKey:@"error"];
    if (![architectures isKindOfClass:[NSArray class]] || [architectures count] == 0)
        return [NSDictionary dictionaryWithObject:@"architectures must be a non-empty array" forKey:@"error"];
    enumerator = [architectures objectEnumerator];
    while ((architecture = [enumerator nextObject])) {
        NSString *jobID;
        NSMutableDictionary *job;
        if (!([architecture isEqual:@"m68k"] || [architecture isEqual:@"i386"] ||
              [architecture isEqual:@"hppa"] || [architecture isEqual:@"sparc"]))
            return [NSDictionary dictionaryWithObject:@"unsupported architecture" forKey:@"error"];
        jobID = [NSString stringWithFormat:@"%@-%@-%@", snapshot, target, architecture];
        job = [NSMutableDictionary dictionaryWithDictionary:spec];
        [job setObject:jobID forKey:@"jobID"];
        [job setObject:architecture forKey:@"architecture"];
        [job setObject:@"queued" forKey:@"state"];
        [job setObject:[NSNumber numberWithInt:0] forKey:@"retries"];
        [_jobs addObject:job];
        [ids addObject:jobID];
    }
    [self save];
    return [NSDictionary dictionaryWithObjectsAndKeys:@"queued", @"state", ids, @"jobs", nil];
}
- (NSArray *)jobs { return [NSArray arrayWithArray:_jobs]; }
- (NSArray *)workers { return [_workers allValues]; }
- (BOOL)cancelJob:(NSString *)jobID {
    unsigned int i;
    for (i = 0; i < [_jobs count]; i++) {
        NSMutableDictionary *job = [_jobs objectAtIndex:i];
        if ([[job objectForKey:@"jobID"] isEqual:jobID] &&
            ![[job objectForKey:@"state"] isEqual:@"complete"]) {
            [job setObject:@"cancelled" forKey:@"state"];
            [self save]; return YES;
        }
    }
    return NO;
}
- (BOOL)registerWorker:(NSString *)name capabilities:(NSDictionary *)capabilities {
    NSMutableDictionary *worker;
    if (!RSSafeName(name) || ![[capabilities objectForKey:@"architectures"] isKindOfClass:[NSArray class]]) return NO;
    worker = [NSMutableDictionary dictionaryWithDictionary:capabilities];
    [worker setObject:name forKey:@"name"];
    [worker setObject:[NSDate date] forKey:@"lastHeartbeat"];
    [worker setObject:@"online" forKey:@"state"];
    [_workers setObject:worker forKey:name];
    [self save]; return YES;
}
- (BOOL)heartbeat:(NSString *)name {
    NSMutableDictionary *worker = [_workers objectForKey:name];
    if (!worker) return NO;
    [worker setObject:[NSDate date] forKey:@"lastHeartbeat"];
    [worker setObject:@"online" forKey:@"state"];
    return YES;
}
- (NSDictionary *)nextJobForWorker:(NSString *)name {
    NSDictionary *worker = [_workers objectForKey:name];
    NSArray *architectures = [worker objectForKey:@"architectures"];
    unsigned int i;
    if (!worker || ![[worker objectForKey:@"state"] isEqual:@"online"]) return nil;
    for (i = 0; i < [_jobs count]; i++) {
        NSMutableDictionary *job = [_jobs objectAtIndex:i];
        if ([[job objectForKey:@"state"] isEqual:@"queued"] &&
            [architectures containsObject:[job objectForKey:@"architecture"]]) {
            [job setObject:@"running" forKey:@"state"];
            [job setObject:name forKey:@"worker"];
            [job setObject:[NSDate date] forKey:@"started"];
            [self save]; return [NSDictionary dictionaryWithDictionary:job];
        }
    }
    return nil;
}
- (BOOL)finishJob:(NSString *)jobID result:(NSDictionary *)result {
    unsigned int i;
    for (i = 0; i < [_jobs count]; i++) {
        NSMutableDictionary *job = [_jobs objectAtIndex:i];
        if ([[job objectForKey:@"jobID"] isEqual:jobID]) {
            BOOL infrastructure = [[result objectForKey:@"infrastructureFailure"] boolValue];
            int retries = [[job objectForKey:@"retries"] intValue];
            [job setObject:result forKey:@"result"];
            [job setObject:[NSDate date] forKey:@"finished"];
            if (infrastructure && retries < 1) {
                [job setObject:[NSNumber numberWithInt:retries + 1] forKey:@"retries"];
                [job setObject:@"queued" forKey:@"state"];
                [job removeObjectForKey:@"worker"];
            } else {
                [job setObject:([[result objectForKey:@"success"] boolValue] ? @"complete" : @"failed") forKey:@"state"];
            }
            [self save]; return YES;
        }
    }
    return NO;
}
- (void)reapWorkers:(NSTimer *)timer {
    NSEnumerator *enumerator = [_workers keyEnumerator];
    NSString *name;
    NSDate *now = [NSDate date];
    while ((name = [enumerator nextObject])) {
        NSMutableDictionary *worker = [_workers objectForKey:name];
        if ([now timeIntervalSinceDate:[worker objectForKey:@"lastHeartbeat"]] > 45.0) {
            unsigned int i;
            [worker setObject:@"offline" forKey:@"state"];
            for (i = 0; i < [_jobs count]; i++) {
                NSMutableDictionary *job = [_jobs objectAtIndex:i];
                if ([[job objectForKey:@"state"] isEqual:@"running"] && [[job objectForKey:@"worker"] isEqual:name]) {
                    int retries = [[job objectForKey:@"retries"] intValue];
                    [job setObject:(retries < 1 ? @"queued" : @"failed") forKey:@"state"];
                    [job setObject:[NSNumber numberWithInt:retries + 1] forKey:@"retries"];
                    [job removeObjectForKey:@"worker"];
                }
            }
        }
    }
    [self save];
}
@end

int main(int argc, const char **argv) {
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    NSString *state = argc > 1 ? [NSString stringWithCString:argv[1]] : @"/LocalLibrary/Reopenstep/farm-state.plist";
    RSController *controller = [[[RSController alloc] initWithStatePath:state] autorelease];
    NSConnection *connection = [NSConnection defaultConnection];
    [connection setRootObject:controller];
    if (![connection registerName:@"ReopenstepFarmController"]) {
        NSLog(@"cannot register ReopenstepFarmController"); [pool release]; return 1;
    }
    NSLog(@"Reopenstep farm controller ready");
    [[NSRunLoop currentRunLoop] run];
    [pool release]; return 0;
}
