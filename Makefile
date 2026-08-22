.PHONY: check inventory inspect-test-iso

check:
	python3 -m compileall -q reopenstep_tool tests
	python3 -m unittest discover -v

inventory:
	./reopenstep media inventory

inspect-test-iso:
	./reopenstep image inspect test.iso --require-bootable
