# Installation Composer and OPENSTEP packages

ReopenStep can compose a classic single-volume Installer package entirely on a
modern host. The output is a `.pkg` directory containing the four required
components:

- `Name.tar.Z`: a classic USTAR payload compressed with UNIX `compress`;
- `Name.bom`: the editable OPENSTEP transport bill of materials;
- `Name.info`: Installer metadata;
- `Name.sizes`: file count and installed/compressed size estimates.

This follows NeXT's published [Installer package specification](https://www.nextop.de/NeXTstep_3.3_Developer_Documentation/Concepts/Installer.htmld/index.html).
The packer requires `compress` or `ncompress`; it does not substitute gzip.

## Stage and build a package

Arrange the payload root exactly as it should appear relative to the package's
install location. For a fixed `/` installation, for example, an application
destined for `/LocalApps` belongs at `payload/LocalApps/Example.app`.

Create a reviewable recipe:

```sh
./reopenstep package plan \
  --root out/composer/payload \
  --name ReopenStepExtras \
  --title "ReopenStep Extras" \
  --version 1.0 \
  --description "Custom OPENSTEP software and drivers" \
  --default-location / \
  --output out/composer/ReopenStepExtras.recipe.json
```

The recipe records every path, type, mode, size, modification time, file hash,
link target, and a digest of the complete payload. Building fails if anything
changes after review:

```sh
./reopenstep package build \
  --recipe out/composer/ReopenStepExtras.recipe.json \
  --output out/composer/ReopenStepExtras.pkg

./reopenstep package inspect out/composer/ReopenStepExtras.pkg
```

The output directory must not already exist. This prevents an accidental
overwrite of a previously tested package.

## BOM maker and inspector

Generate only the editable transport BOM when iterating on payload ownership:

```sh
./reopenstep package bom \
  --root out/composer/payload \
  --owner 0 --group 0 \
  --output out/composer/ReopenStepExtras.bom

./reopenstep package bom-inspect out/composer/ReopenStepExtras.bom
```

NeXT's specification describes this BOM as one ASCII record per installed
file, excluding directories. Installer converts the delivered record into its
binary receipt form. The inspector distinguishes three important formats:

- `openstep-text`: the editable package-transport form generated here;
- `openstep-installed-binary`: the older NeXT receipt form observed on the
  OPENSTEP 4.2 Patch 4 media;
- `darwin-bomstore`: the newer Mac OS X format emitted by current macOS
  `mkbom`, which must not be substituted without an OPENSTEP compatibility
  test.

The generated archive owns its entries as `root:wheel` (`0/0` by default),
preserves modes and timestamps, and rejects non-ASCII, unsafe, or classic-tar-
incompatible paths. FIFOs, sockets, and device nodes are also rejected rather
than silently producing a package with ambiguous host-specific behavior.

## Workbench

![ReopenStep Workbench Installation Composer](images/reopenstep-workbench-composer.png)

The Installation Composer tab exposes the same plan, build, and inspect
operations. It passes paths and metadata to the repository CLI as argument
arrays; package rules are not duplicated in Objective-C. The initial surface
composes one payload root. Package collections, scripts, localized resources,
collision views, and direct UFS/ISO insertion can build on the versioned recipe
without changing the package format.

The host-side structural result is a compatibility candidate. The remaining
acceptance test is to open and install a generated fixture with OPENSTEP 4.2
Installer, then verify its receipt and uninstall behavior.

## App-driven acceptance workflow

The checked-in fixture places one harmless marker at
`/LocalLibrary/ReopenStep/ComposerFixture.txt`. On macOS, build Workbench and
drive the complete plan/build/inspect sequence through the application:

```sh
make workbench-compose-fixture
```

The target runs this explicit AppleScript entry point:

```sh
/usr/bin/osascript scripts/compose-workbench-fixture.applescript "$PWD"
```

The script uses System Events to select the Installation Composer tab, populate
all eight fields, and click `Create Recipe`, `Build Package`, and
`Inspect Package`. It waits for Workbench's status after every action and
returns the application console as its command output. For a clean acceptance
log, it gracefully closes an existing Workbench session before launching the
built application. macOS must grant the calling terminal Accessibility
permission for System Events UI scripting.

The generated, ignored artifacts are:

```text
out/composer/WorkbenchFixture.recipe.json
out/composer/WorkbenchFixture.pkg/
  WorkbenchFixture.bom
  WorkbenchFixture.info
  WorkbenchFixture.sizes
  WorkbenchFixture.tar.Z
```

The package builder deliberately refuses to replace an existing `.pkg`.
Archive or remove the previous fixture before repeating this acceptance run.
After host inspection reports `compatible_candidate: true`, copy the `.pkg`
directory without changing its contents onto ISO/UFS test media, open it with
OPENSTEP Installer, and verify:

1. `/LocalLibrary/ReopenStep/ComposerFixture.txt` is installed;
2. `/NextLibrary/Receipts/WorkbenchFixture.pkg` contains the generated receipt;
3. Installer can remove the fixture using that receipt;
4. the marker file is absent after removal.

Record Installer console output and receipt BOM identification alongside the
VM configuration used for the test. This final guest pass—not host structural
inspection—is the compatibility authority.
