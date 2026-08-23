#import "RSCommandRunner.h"

@implementation RSCommandRunner

- (void)finishIfComplete {
    if (!_taskExited || !_sawEOF) return;
    _running = NO;
    [_delegate commandRunner:self finishedWithStatus:_exitStatus];
}

- (id)initWithDelegate:(id<RSCommandRunnerDelegate>)delegate {
    self = [super init];
    if (self) _delegate = delegate;
    return self;
}

- (void)dealloc {
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    if (_running) [_task terminate];
    [_task release];
    [_pipe release];
    [super dealloc];
}

- (BOOL)isRunning { return _running; }

- (BOOL)runExecutable:(NSString *)executable
            arguments:(NSArray *)arguments
     workingDirectory:(NSString *)workingDirectory
          environment:(NSDictionary *)environment {
    if (_running) return NO;

    [_task release];
    [_pipe release];
    _task = [[NSTask alloc] init];
    _pipe = [[NSPipe alloc] init];
    _readHandle = [_pipe fileHandleForReading];
    [_task setLaunchPath:executable];
    [_task setArguments:arguments];
    if (workingDirectory) [_task setCurrentDirectoryPath:workingDirectory];
    if (environment) [_task setEnvironment:environment];
    [_task setStandardOutput:_pipe];
    [_task setStandardError:_pipe];
    _taskExited = NO;
    _sawEOF = NO;
    _exitStatus = -1;

    [[NSNotificationCenter defaultCenter] addObserver:self
        selector:@selector(readCompleted:)
        name:NSFileHandleReadCompletionNotification object:_readHandle];
    [[NSNotificationCenter defaultCenter] addObserver:self
        selector:@selector(taskTerminated:)
        name:NSTaskDidTerminateNotification object:_task];
    [_readHandle readInBackgroundAndNotify];

    NS_DURING
        [_task launch];
        _running = YES;
    NS_HANDLER
        NSString *message = [NSString stringWithFormat:@"Launch failed: %@\n", [localException reason]];
        [_delegate commandRunner:self receivedText:message];
        [[NSNotificationCenter defaultCenter] removeObserver:self name:NSFileHandleReadCompletionNotification object:_readHandle];
        [[NSNotificationCenter defaultCenter] removeObserver:self name:NSTaskDidTerminateNotification object:_task];
        return NO;
    NS_ENDHANDLER
    return YES;
}

- (void)readCompleted:(NSNotification *)notification {
    NSData *data = [[notification userInfo] objectForKey:NSFileHandleNotificationDataItem];
    if ([data length] != 0) {
        NSString *text = [[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] autorelease];
        if (!text) text = [[[NSString alloc] initWithData:data encoding:NSISOLatin1StringEncoding] autorelease];
        if (text) [_delegate commandRunner:self receivedText:text];
        [_readHandle readInBackgroundAndNotify];
    } else {
        _sawEOF = YES;
        [[NSNotificationCenter defaultCenter] removeObserver:self name:NSFileHandleReadCompletionNotification object:_readHandle];
        [self finishIfComplete];
    }
}

- (void)taskTerminated:(NSNotification *)notification {
    _exitStatus = [_task terminationStatus];
    _taskExited = YES;
    [[NSNotificationCenter defaultCenter] removeObserver:self name:NSTaskDidTerminateNotification object:_task];
    [self finishIfComplete];
}

- (void)cancel {
    if (_running) [_task terminate];
}

@end
