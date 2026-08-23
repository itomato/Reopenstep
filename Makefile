.PHONY: check inventory inspect-test-iso workbench-mac workbench-test workbench-compose-fixture boote-test boote-qemu-test boote-qemu-matrix boote-test-full boote-prepare boote-build boote-iso

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
