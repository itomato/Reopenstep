.PHONY: check inventory inspect-test-iso workbench-mac workbench-test workbench-compose-fixture boote-test boote-qemu-test boote-qemu-matrix boote-test-full boote-prepare boote-build boote-iso boote-vesa-iso patch4-vesa-fixture

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

patch4-vesa-fixture:
	./reopenstep patch4 overlay vault/OS42MachUserPatch4.tar --image out/openstep-user-ufs.raw --output out/boote/openstep-user-patch4.raw
	./reopenstep patch4 set-vesa-mode --image out/boote/openstep-user-patch4.raw --output out/boote/openstep-user-patch4-vesa.raw --mode 0x118
