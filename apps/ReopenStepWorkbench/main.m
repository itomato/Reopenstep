#import <AppKit/AppKit.h>
#import "RSWorkbenchController.h"

int main(int argc, const char **argv) {
    (void)argc;
    (void)argv;
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    NSApplication *application = [NSApplication sharedApplication];
    RSWorkbenchController *controller = [[[RSWorkbenchController alloc] init] autorelease];
    [application setDelegate:controller];
    [application run];
    [pool release];
    return 0;
}
