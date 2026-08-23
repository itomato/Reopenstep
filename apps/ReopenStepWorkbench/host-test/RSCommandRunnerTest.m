#import <Foundation/Foundation.h>
#import "RSCommandRunner.h"

@interface RSTestDelegate : NSObject <RSCommandRunnerDelegate> {
    NSMutableString *_output;
    BOOL _finished;
    int _status;
}
- (BOOL)finished;
- (int)status;
- (NSString *)output;
@end

@implementation RSTestDelegate
- (id)init {
    self = [super init];
    if (self) _output = [[NSMutableString alloc] init];
    return self;
}
- (void)dealloc { [_output release]; [super dealloc]; }
- (void)commandRunner:(RSCommandRunner *)runner receivedText:(NSString *)text { [_output appendString:text]; }
- (void)commandRunner:(RSCommandRunner *)runner finishedWithStatus:(int)status { _status = status; _finished = YES; }
- (BOOL)finished { return _finished; }
- (int)status { return _status; }
- (NSString *)output { return _output; }
@end

int main(void) {
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    RSTestDelegate *delegate = [[[RSTestDelegate alloc] init] autorelease];
    RSCommandRunner *runner = [[[RSCommandRunner alloc] initWithDelegate:delegate] autorelease];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5.0];
    if (![runner runExecutable:@"/usr/bin/printf"
        arguments:[NSArray arrayWithObjects:@"workbench-output:%s", @"ok", nil]
        workingDirectory:nil environment:nil]) return 1;
    while (![delegate finished] && [deadline timeIntervalSinceNow] > 0)
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
    if (![delegate finished] || [delegate status] != 0 || ![[delegate output] isEqual:@"workbench-output:ok"]) {
        NSLog(@"runner failed: finished=%d status=%d output=%@", [delegate finished], [delegate status], [delegate output]);
        [pool release];
        return 1;
    }
    puts("RSCommandRunner: ok");
    [pool release];
    return 0;
}
