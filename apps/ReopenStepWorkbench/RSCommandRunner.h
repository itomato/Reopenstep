#import <Foundation/Foundation.h>

@class RSCommandRunner;

@protocol RSCommandRunnerDelegate
- (void)commandRunner:(RSCommandRunner *)runner receivedText:(NSString *)text;
- (void)commandRunner:(RSCommandRunner *)runner finishedWithStatus:(int)status;
@end

@interface RSCommandRunner : NSObject {
    NSTask *_task;
    NSPipe *_pipe;
    NSFileHandle *_readHandle;
    id<RSCommandRunnerDelegate> _delegate;
    BOOL _running;
    BOOL _taskExited;
    BOOL _sawEOF;
    int _exitStatus;
}
- (id)initWithDelegate:(id<RSCommandRunnerDelegate>)delegate;
- (BOOL)runExecutable:(NSString *)executable
            arguments:(NSArray *)arguments
     workingDirectory:(NSString *)workingDirectory
          environment:(NSDictionary *)environment;
- (void)cancel;
- (BOOL)isRunning;
@end
