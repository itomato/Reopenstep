#import "RSWorkbenchController.h"

enum {
    RSInspectPathTag = 1,
    RSUFSPathTag,
    RSBootPathTag,
    RSDeveloperPathTag,
    RSLabelPathTag,
    RSOutputPathTag,
    RSEmulatorISOPathTag
};

static NSString *RSRepositoryAtOrAbove(NSString *candidate) {
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *path = [candidate stringByStandardizingPath];
    unsigned int depth;
    for (depth = 0; depth < 10 && [path length] > 1; depth++) {
        BOOL directory = NO;
        if ([manager fileExistsAtPath:[path stringByAppendingPathComponent:@"reopenstep"] isDirectory:&directory] && !directory &&
            [manager fileExistsAtPath:[path stringByAppendingPathComponent:@"reopenstep_tool"] isDirectory:&directory] && directory)
            return path;
        path = [path stringByDeletingLastPathComponent];
    }
    return nil;
}

static NSString *RSFindRepositoryRoot(void) {
    NSString *configured = [[[NSProcessInfo processInfo] environment] objectForKey:@"REOPENSTEP_ROOT"];
    NSString *found;
    if (configured && (found = RSRepositoryAtOrAbove(configured))) return found;
    found = RSRepositoryAtOrAbove([[NSFileManager defaultManager] currentDirectoryPath]);
    if (found) return found;
    return RSRepositoryAtOrAbove([[NSBundle mainBundle] bundlePath]);
}

static NSTextField *RSLabel(NSString *title, NSRect frame) {
    NSTextField *field = [[[NSTextField alloc] initWithFrame:frame] autorelease];
    [field setStringValue:title];
    [field setEditable:NO];
    [field setSelectable:NO];
    [field setBezeled:NO];
    [field setDrawsBackground:NO];
    return field;
}

static NSTextField *RSTextField(NSString *value, NSRect frame) {
    NSTextField *field = [[[NSTextField alloc] initWithFrame:frame] autorelease];
    [field setStringValue:(value ? value : @"")];
    [field setAutoresizingMask:NSViewWidthSizable];
    return field;
}

static NSButton *RSButton(NSString *title, id target, SEL action, NSRect frame) {
    NSButton *button = [[[NSButton alloc] initWithFrame:frame] autorelease];
    [button setTitle:title];
    [button setTarget:target];
    [button setAction:action];
    [button setBezelStyle:NSRoundedBezelStyle];
    return button;
}

@interface RSWorkbenchController (Private)
- (NSView *)mediaViewWithFrame:(NSRect)frame;
- (NSView *)builderViewWithFrame:(NSRect)frame;
- (NSView *)emulatorViewWithFrame:(NSRect)frame;
- (void)appendConsole:(NSString *)text;
- (void)runExecutable:(NSString *)executable arguments:(NSArray *)arguments environment:(NSDictionary *)environment;
- (void)choosePath:(id)sender;
- (void)inspectMedia:(id)sender;
- (void)buildISO:(id)sender;
- (void)launchEmulator:(id)sender;
- (void)previewEmulator:(id)sender;
- (void)cancelCommand:(id)sender;
@end

@implementation RSWorkbenchController

- (id)init {
    self = [super init];
    if (self) {
        _repositoryRoot = [RSFindRepositoryRoot() copy];
        _runner = [[RSCommandRunner alloc] initWithDelegate:self];
    }
    return self;
}

- (void)dealloc {
    [_runner release];
    [_repositoryRoot release];
    [_console release];
    [_status release];
    [_cancelButton release];
    [_inspectPath release];
    [_requireBootable release];
    [_ufsPath release];
    [_bootPath release];
    [_developerPath release];
    [_labelPath release];
    [_outputPath release];
    [_emulatorISO release];
    [_emulatorBackend release];
    [_emulatorMode release];
    [_window release];
    [super dealloc];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSRect contentFrame = NSMakeRect(0, 0, 940, 680);
    NSView *content;
    NSTabView *tabs;
    NSTabViewItem *item;
    NSScrollView *scroll;
    NSMenu *mainMenu;
    NSMenuItem *applicationItem;
    NSMenu *applicationMenu;

    mainMenu = [[[NSMenu alloc] initWithTitle:@"Main"] autorelease];
    applicationItem = [[[NSMenuItem alloc] initWithTitle:@"ReopenStep Workbench" action:NULL keyEquivalent:@""] autorelease];
    [mainMenu addItem:applicationItem];
    applicationMenu = [[[NSMenu alloc] initWithTitle:@"ReopenStep Workbench"] autorelease];
    [applicationMenu addItemWithTitle:@"Quit ReopenStep Workbench" action:@selector(terminate:) keyEquivalent:@"q"];
    [applicationItem setSubmenu:applicationMenu];
    [NSApp setMainMenu:mainMenu];

    _window = [[NSWindow alloc] initWithContentRect:contentFrame
        styleMask:(NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask)
        backing:NSBackingStoreBuffered defer:NO];
    [_window setTitle:@"ReopenStep Workbench"];
    [_window setMinSize:NSMakeSize(760, 560)];
    content = [_window contentView];

    tabs = [[[NSTabView alloc] initWithFrame:NSMakeRect(14, 270, 912, 396)] autorelease];
    [tabs setAutoresizingMask:(NSViewWidthSizable | NSViewHeightSizable)];
    item = [[[NSTabViewItem alloc] initWithIdentifier:@"media"] autorelease];
    [item setLabel:@"Media Inspector"];
    [item setView:[self mediaViewWithFrame:NSMakeRect(0, 0, 890, 350)]];
    [tabs addTabViewItem:item];
    item = [[[NSTabViewItem alloc] initWithIdentifier:@"builder"] autorelease];
    [item setLabel:@"ISO Builder"];
    [item setView:[self builderViewWithFrame:NSMakeRect(0, 0, 890, 350)]];
    [tabs addTabViewItem:item];
    item = [[[NSTabViewItem alloc] initWithIdentifier:@"emulator"] autorelease];
    [item setLabel:@"Emulator Launcher"];
    [item setView:[self emulatorViewWithFrame:NSMakeRect(0, 0, 890, 350)]];
    [tabs addTabViewItem:item];
    [content addSubview:tabs];

    scroll = [[[NSScrollView alloc] initWithFrame:NSMakeRect(14, 42, 912, 216)] autorelease];
    [scroll setAutoresizingMask:(NSViewWidthSizable | NSViewMaxYMargin)];
    [scroll setHasVerticalScroller:YES];
    [scroll setBorderType:NSBezelBorder];
    _console = [[NSTextView alloc] initWithFrame:[[scroll contentView] bounds]];
    [_console setEditable:NO];
    [_console setSelectable:YES];
    [_console setTextColor:[NSColor textColor]];
    [_console setBackgroundColor:[NSColor textBackgroundColor]];
    [_console setFont:[NSFont userFixedPitchFontOfSize:12.0]];
    [_console setAutoresizingMask:(NSViewWidthSizable | NSViewHeightSizable)];
    [scroll setDocumentView:_console];
    [content addSubview:scroll];

    _status = [RSTextField(@"Ready", NSMakeRect(16, 10, 730, 24)) retain];
    [_status setEditable:NO];
    [_status setBezeled:NO];
    [_status setDrawsBackground:NO];
    [_status setAutoresizingMask:NSViewWidthSizable];
    [content addSubview:_status];
    _cancelButton = [RSButton(@"Cancel", self, @selector(cancelCommand:), NSMakeRect(820, 7, 104, 28)) retain];
    [_cancelButton setEnabled:NO];
    [_cancelButton setAutoresizingMask:NSViewMinXMargin];
    [content addSubview:_cancelButton];

    if (_repositoryRoot) {
        [self appendConsole:[NSString stringWithFormat:@"Repository: %@\n", _repositoryRoot]];
    } else {
        [_status setStringValue:@"Repository not found; set REOPENSTEP_ROOT"];
        [self appendConsole:@"Could not find the reopenstep executable. Set REOPENSTEP_ROOT to the repository path.\n"];
    }
    [_window center];
    [_window makeKeyAndOrderFront:nil];
    if ([NSApp respondsToSelector:@selector(activateIgnoringOtherApps:)])
        [NSApp activateIgnoringOtherApps:YES];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)application { return YES; }

- (NSView *)mediaViewWithFrame:(NSRect)frame {
    NSView *view = [[[NSView alloc] initWithFrame:frame] autorelease];
    NSString *defaultPath = _repositoryRoot ? [_repositoryRoot stringByAppendingPathComponent:@"out/reopenstep-4.2-eide-developer-v6.iso"] : @"";
    NSButton *choose;
    [view addSubview:RSLabel(@"Image or media file", NSMakeRect(18, 280, 170, 22))];
    _inspectPath = [RSTextField(defaultPath, NSMakeRect(18, 250, 730, 26)) retain];
    [view addSubview:_inspectPath];
    choose = RSButton(@"Choose…", self, @selector(choosePath:), NSMakeRect(758, 248, 110, 30));
    [choose setTag:RSInspectPathTag];
    [choose setAutoresizingMask:NSViewMinXMargin];
    [view addSubview:choose];
    _requireBootable = [RSButton(@"Require a valid El Torito boot catalog", nil, NULL, NSMakeRect(18, 205, 310, 24)) retain];
    [_requireBootable setButtonType:NSSwitchButton];
    [_requireBootable setState:NSOnState];
    [view addSubview:_requireBootable];
    [view addSubview:RSButton(@"Inspect Media", self, @selector(inspectMedia:), NSMakeRect(18, 150, 150, 34))];
    [view addSubview:RSLabel(@"The full structured report is written to the console below.", NSMakeRect(185, 155, 520, 22))];
    return view;
}

- (void)addBuilderRow:(NSView *)view title:(NSString *)title field:(NSTextField **)field
                 value:(NSString *)value y:(float)y tag:(int)tag {
    NSButton *choose;
    [view addSubview:RSLabel(title, NSMakeRect(18, y + 3, 142, 22))];
    *field = [RSTextField(value, NSMakeRect(160, y, 588, 26)) retain];
    [view addSubview:*field];
    choose = RSButton((tag == RSOutputPathTag ? @"Save As…" : @"Choose…"), self,
                      @selector(choosePath:), NSMakeRect(758, y - 2, 110, 30));
    [choose setTag:tag];
    [choose setAutoresizingMask:NSViewMinXMargin];
    [view addSubview:choose];
}

- (NSView *)builderViewWithFrame:(NSRect)frame {
    NSView *view = [[[NSView alloc] initWithFrame:frame] autorelease];
    NSString *root = _repositoryRoot ? _repositoryRoot : @"";
    [self addBuilderRow:view title:@"User UFS" field:&_ufsPath
        value:[root stringByAppendingPathComponent:@"out/mastered/user-base/OPENSTEP42CD-eide-developer-v5.UFS"] y:292 tag:RSUFSPathTag];
    [self addBuilderRow:view title:@"Startup image" field:&_bootPath
        value:[root stringByAppendingPathComponent:@"out/mastered/user-base/boot/F288-eide-autoinstall.img"] y:248 tag:RSBootPathTag];
    [self addBuilderRow:view title:@"Developer UFS" field:&_developerPath
        value:[root stringByAppendingPathComponent:@"out/mastered/combined-base/OPENSTEP42DEV.UFS"] y:204 tag:RSDeveloperPathTag];
    [self addBuilderRow:view title:@"NeXT label" field:&_labelPath
        value:[root stringByAppendingPathComponent:@"out/mastered/user-base/NEXT_LABEL.bin"] y:160 tag:RSLabelPathTag];
    [self addBuilderRow:view title:@"Output ISO" field:&_outputPath
        value:[root stringByAppendingPathComponent:@"out/reopenstep-custom.iso"] y:116 tag:RSOutputPathTag];
    [view addSubview:RSButton(@"Build Bootable ISO", self, @selector(buildISO:), NSMakeRect(18, 58, 180, 36))];
    [view addSubview:RSLabel(@"Uses the corrected dlV3 partition records and exposes Developer media as partition b.",
                            NSMakeRect(215, 65, 630, 22))];
    return view;
}

- (NSView *)emulatorViewWithFrame:(NSRect)frame {
    NSView *view = [[[NSView alloc] initWithFrame:frame] autorelease];
    NSString *defaultISO = _repositoryRoot ? [_repositoryRoot stringByAppendingPathComponent:@"out/reopenstep-4.2-eide-developer-v6.iso"] : @"";
    NSButton *choose;
    [view addSubview:RSLabel(@"Installer ISO", NSMakeRect(18, 280, 130, 22))];
    _emulatorISO = [RSTextField(defaultISO, NSMakeRect(18, 250, 730, 26)) retain];
    [view addSubview:_emulatorISO];
    choose = RSButton(@"Choose…", self, @selector(choosePath:), NSMakeRect(758, 248, 110, 30));
    [choose setTag:RSEmulatorISOPathTag];
    [choose setAutoresizingMask:NSViewMinXMargin];
    [view addSubview:choose];

    [view addSubview:RSLabel(@"Backend", NSMakeRect(18, 205, 100, 22))];
    _emulatorBackend = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(120, 200, 180, 30) pullsDown:NO];
    [_emulatorBackend addItemsWithTitles:[NSArray arrayWithObjects:@"QEMU", @"86Box", nil]];
    [view addSubview:_emulatorBackend];
    [view addSubview:RSLabel(@"Mode", NSMakeRect(330, 205, 80, 22))];
    _emulatorMode = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(400, 200, 180, 30) pullsDown:NO];
    [_emulatorMode addItemsWithTitles:[NSArray arrayWithObjects:@"install", @"rescue", @"disk", nil]];
    [view addSubview:_emulatorMode];
    [view addSubview:RSButton(@"Preview Command", self, @selector(previewEmulator:), NSMakeRect(18, 140, 170, 34))];
    [view addSubview:RSButton(@"Launch Emulator", self, @selector(launchEmulator:), NSMakeRect(205, 140, 170, 34))];
    [view addSubview:RSLabel(@"Disk mode ejects the ISO and boots the persistent target disk.", NSMakeRect(18, 95, 650, 22))];
    return view;
}

- (NSTextField *)fieldForTag:(int)tag {
    switch (tag) {
        case RSInspectPathTag: return _inspectPath;
        case RSUFSPathTag: return _ufsPath;
        case RSBootPathTag: return _bootPath;
        case RSDeveloperPathTag: return _developerPath;
        case RSLabelPathTag: return _labelPath;
        case RSOutputPathTag: return _outputPath;
        case RSEmulatorISOPathTag: return _emulatorISO;
    }
    return nil;
}

- (void)choosePath:(id)sender {
    NSTextField *field = [self fieldForTag:[sender tag]];
    if ([sender tag] == RSOutputPathTag) {
        NSSavePanel *panel = [NSSavePanel savePanel];
        if ([panel runModal] == NSOKButton) [field setStringValue:[panel filename]];
    } else {
        NSOpenPanel *panel = [NSOpenPanel openPanel];
        [panel setCanChooseFiles:YES];
        [panel setCanChooseDirectories:NO];
        [panel setAllowsMultipleSelection:NO];
        if ([panel runModal] == NSOKButton) [field setStringValue:[panel filename]];
    }
}

- (void)inspectMedia:(id)sender {
    NSMutableArray *arguments = [NSMutableArray arrayWithObjects:@"image", @"inspect", [_inspectPath stringValue], nil];
    if ([_requireBootable state] == NSOnState) [arguments addObject:@"--require-bootable"];
    [self runExecutable:[_repositoryRoot stringByAppendingPathComponent:@"reopenstep"] arguments:arguments environment:nil];
}

- (void)buildISO:(id)sender {
    NSMutableArray *arguments;
    if ([[_ufsPath stringValue] length] == 0 || [[_bootPath stringValue] length] == 0 ||
        [[_labelPath stringValue] length] == 0 || [[_outputPath stringValue] length] == 0) {
        [self appendConsole:@"ISO build requires User UFS, startup image, NeXT label, and output paths.\n"];
        return;
    }
    arguments = [NSMutableArray arrayWithObjects:@"image", @"wrap",
        @"--ufs", [_ufsPath stringValue], @"--boot-image", [_bootPath stringValue],
        @"--label-template", [_labelPath stringValue], @"--label-offset", @"112",
        @"--label-format", @"u16be", @"--output", [_outputPath stringValue], nil];
    if ([[_developerPath stringValue] length] != 0) {
        [arguments insertObject:[_developerPath stringValue] atIndex:6];
        [arguments insertObject:@"--developer-ufs" atIndex:6];
    }
    [self runExecutable:[_repositoryRoot stringByAppendingPathComponent:@"reopenstep"] arguments:arguments environment:nil];
}

- (NSArray *)emulatorCommand {
    NSString *wrapper = [[_emulatorBackend titleOfSelectedItem] isEqual:@"86Box"] ?
        @"scripts/run-openstep-autoboot-86box.sh" : @"scripts/run-openstep-autoboot.sh";
    return [NSArray arrayWithObjects:[_repositoryRoot stringByAppendingPathComponent:wrapper],
        [_emulatorMode titleOfSelectedItem], nil];
}

- (void)previewEmulator:(id)sender {
    NSArray *command = [self emulatorCommand];
    NSString *variable = [[_emulatorBackend titleOfSelectedItem] isEqual:@"86Box"] ?
        @"REOPENSTEP_86BOX_ISO" : @"REOPENSTEP_QEMU_ISO";
    [self appendConsole:[NSString stringWithFormat:@"$ %@=%@ %@ %@\n", variable,
        [_emulatorISO stringValue], [command objectAtIndex:0], [command objectAtIndex:1]]];
}

- (void)launchEmulator:(id)sender {
    NSArray *command = [self emulatorCommand];
    NSMutableDictionary *environment = [NSMutableDictionary dictionaryWithDictionary:[[NSProcessInfo processInfo] environment]];
    NSString *variable = [[_emulatorBackend titleOfSelectedItem] isEqual:@"86Box"] ?
        @"REOPENSTEP_86BOX_ISO" : @"REOPENSTEP_QEMU_ISO";
    if ([[_emulatorMode titleOfSelectedItem] isEqual:@"disk"]) {
        [environment removeObjectForKey:variable];
    } else {
        [environment setObject:[_emulatorISO stringValue] forKey:variable];
    }
    [self runExecutable:[command objectAtIndex:0]
        arguments:[NSArray arrayWithObject:[command objectAtIndex:1]] environment:environment];
}

- (void)runExecutable:(NSString *)executable arguments:(NSArray *)arguments environment:(NSDictionary *)environment {
    if (!_repositoryRoot) {
        [self appendConsole:@"Repository unavailable. Set REOPENSTEP_ROOT and restart.\n"];
        return;
    }
    if ([_runner isRunning]) {
        [self appendConsole:@"A command is already running. Cancel it before starting another.\n"];
        return;
    }
    [self appendConsole:[NSString stringWithFormat:@"\n$ %@ %@\n", executable, [arguments componentsJoinedByString:@" "]]];
    [_status setStringValue:@"Running…"];
    [_cancelButton setEnabled:YES];
    if (![_runner runExecutable:executable arguments:arguments workingDirectory:_repositoryRoot environment:environment]) {
        [_status setStringValue:@"Launch failed"];
        [_cancelButton setEnabled:NO];
    }
}

- (void)cancelCommand:(id)sender { [_runner cancel]; }

- (void)appendConsole:(NSString *)text {
    NSTextStorage *storage = [_console textStorage];
    [storage appendAttributedString:[[[NSAttributedString alloc] initWithString:text] autorelease]];
    [_console scrollRangeToVisible:NSMakeRange([[storage string] length], 0)];
}

- (void)commandRunner:(RSCommandRunner *)runner receivedText:(NSString *)text {
    [self appendConsole:text];
}

- (void)commandRunner:(RSCommandRunner *)runner finishedWithStatus:(int)status {
    [self appendConsole:[NSString stringWithFormat:@"[exit %d]\n", status]];
    [_status setStringValue:(status == 0 ? @"Completed" : [NSString stringWithFormat:@"Failed (exit %d)", status])];
    [_cancelButton setEnabled:NO];
}

@end
