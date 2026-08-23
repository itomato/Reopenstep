#import <AppKit/AppKit.h>
#import "RSCommandRunner.h"

@interface RSWorkbenchController : NSObject <NSApplicationDelegate, RSCommandRunnerDelegate> {
    NSWindow *_window;
    NSTextView *_console;
    NSTextField *_status;
    NSButton *_cancelButton;
    RSCommandRunner *_runner;
    NSString *_repositoryRoot;

    NSTextField *_inspectPath;
    NSButton *_requireBootable;

    NSTextField *_ufsPath;
    NSTextField *_bootPath;
    NSTextField *_developerPath;
    NSTextField *_labelPath;
    NSTextField *_outputPath;

    NSTextField *_emulatorISO;
    NSPopUpButton *_emulatorBackend;
    NSPopUpButton *_emulatorMode;

    NSTextField *_composerRoot;
    NSTextField *_composerName;
    NSTextField *_composerTitle;
    NSTextField *_composerVersion;
    NSTextField *_composerDescription;
    NSTextField *_composerLocation;
    NSTextField *_composerRecipe;
    NSTextField *_composerPackage;
}
@end
