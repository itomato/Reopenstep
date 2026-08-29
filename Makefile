.PHONY: check inventory inspect-test-iso workbench-mac workbench-test workbench-compose-fixture boote-test boote-qemu-test boote-qemu-matrix boote-test-full boote-prepare boote-build boote-iso boote-vesa-iso boote-openstep-disc boote-openstep-floppy boote-xnu-kernel-iso boote-xnu-ufs-vesa boote-rhapsody-dr2-dvd rhapsody-dr2-native-floppy-dvd xnu-kernel rhapsody-gap rhapsody-boot-analysis patch4-vesa-fixture

check:
	python3 -m compileall -q reopenstep_tool tests
	python3 -m unittest discover -v

inventory:
	./reopenstep media inventory

inspect-test-iso:
	./reopenstep image inspect test.iso --require-bootable

workbench-mac:
	$(MAKE) -C apps/ReopenStepWorkbench -f Makefile mac

workbench-test:
	$(MAKE) -C apps/ReopenStepWorkbench -f Makefile test

workbench-compose-fixture: workbench-mac
	/usr/bin/osascript scripts/compose-workbench-fixture.applescript "$(CURDIR)"

boote-test:
	tools/boote/test-config.sh
	tools/chameleon/test-nextlabel.sh

boote-qemu-test: boote-test
	python3 tools/boote/test-qemu.py

boote-qemu-matrix: boote-test
	python3 tools/boote/test-qemu.py --matrix

boote-test-full: boote-test boote-build boote-iso
	python3 tools/boote/test-qemu.py

boote-prepare:
	tools/boote/build-boote.sh prepare

boote-build:
	tools/boote/build-boote.sh build

boote-iso:
	tools/boote/make-boote-iso.sh
boote-vesa-iso:
	BOOTE_CONFIG=tools/boote/config/vesa.toml tools/boote/build-boote.sh build
	BOOTE_ROOT=tools/boote/root-vesa tools/boote/make-boote-iso.sh out/boote/boote-vesa.iso

boote-openstep-disc:
	tools/boote/make-boote-openstep-disc.sh

boote-openstep-floppy:
	tools/boote/make-boote-openstep-floppy.sh

boote-xnu-kernel-iso:
	tools/boote/make-boote-xnu-kernel-iso.sh

boote-xnu-ufs-vesa:
	tools/boote/make-boote-xnu-ufs-vesa.sh

boote-rhapsody-dr2-dvd:
	tools/boote/make-boote-rhapsody-dr2-dvd.sh

rhapsody-dr2-native-floppy-dvd:
	tools/boote/make-rhapsody-dr2-native-floppy-dvd.sh

xnu-kernel:
	tools/xnu/build-xnu-kernel.sh

rhapsody-gap:
	./reopenstep rhapsody gap

rhapsody-boot-analysis:
	python3 tools/analyze_rhapsody_boot.py "Apple ''Rhapsody'' (Titan1U x86 Developer Release 2)/Boot floppy/rhapsody_dr2_x86_InstallationFloppy.img" --max-full-scan-bytes 0x200000

patch4-vesa-fixture:
	./reopenstep patch4 overlay vault/OS42MachUserPatch4.tar --image out/openstep-user-ufs.raw --output out/boote/openstep-user-patch4.raw
	./reopenstep patch4 set-vesa-mode --image out/boote/openstep-user-patch4.raw --output out/boote/openstep-user-patch4-vesa.raw --mode 0x118
