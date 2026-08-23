# ReopenStep Workbench

ReopenStep Workbench is a GNUstep/AppKit front end for the repository's
reproducible command-line tools. It never constructs a shell command: paths and
options are passed to `NSTask` as argument arrays, and combined stdout/stderr is
streamed into the application console.

The first application milestone includes:

- Media Inspector, including optional bootability enforcement.
- Bootable ISO Builder with User UFS, startup image, Developer UFS, and NeXT
  disk-label inputs.
- QEMU and 86Box launchers with install, rescue, and installed-disk modes.

The next milestone is the Installation Composer. It will present a staged
payload tree, accept files and folders through native pickers, group adopted
packages such as Patch 4, KB7SQI, Big Green Disc, and Lighthouse, and expose
`mkbom`/`lsbom` as structured actions. The controller will emit a reviewable
recipe and pass argument arrays to the CLI; BOM policy, UFS mutation, and media
mastering remain in the shared backend. Package contents stay in the ignored
vault rather than the application bundle or Git history.

The application locates the repository by walking upward from its working
directory and application bundle. Set `REOPENSTEP_ROOT` when the application is
installed elsewhere.

## GNUstep build

Install GNUstep Make, Base, GUI, and a graphical backend, then load the normal
GNUstep environment and run:

```sh
cd apps/ReopenStepWorkbench
make -f GNUmakefile
openapp ./ReopenStepWorkbench.app
```

## macOS build

The same sources build directly against Cocoa for rapid development and QA:

```sh
make -C apps/ReopenStepWorkbench -f Makefile mac
make -C apps/ReopenStepWorkbench -f Makefile test
open apps/ReopenStepWorkbench/build/ReopenStepWorkbench.app
```

Image manipulation remains in `reopenstep_tool`; adding a GUI action should
normally mean adding an argument-array adapter, not duplicating Python logic in
Objective-C.
