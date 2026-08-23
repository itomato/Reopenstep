SOURCES = main.m RSCommandRunner.m RSWorkbenchController.m
HEADERS = RSCommandRunner.h RSWorkbenchController.h
BUILD_DIR = build
MAC_APP = $(BUILD_DIR)/ReopenStepWorkbench.app
MAC_BINARY = $(MAC_APP)/Contents/MacOS/ReopenStepWorkbench

.PHONY: mac test clean

mac: $(MAC_BINARY)

$(MAC_BINARY): $(SOURCES) $(HEADERS) Info.plist
	mkdir -p $(MAC_APP)/Contents/MacOS
	cp Info.plist $(MAC_APP)/Contents/Info.plist
	clang -std=gnu99 -Wall -Wextra -Wno-deprecated-declarations -fno-objc-arc \
		-framework Foundation -framework AppKit $(SOURCES) -o $(MAC_BINARY)

test: $(BUILD_DIR)/RSCommandRunnerTest
	$(BUILD_DIR)/RSCommandRunnerTest

$(BUILD_DIR)/RSCommandRunnerTest: RSCommandRunner.m RSCommandRunner.h host-test/RSCommandRunnerTest.m
	mkdir -p $(BUILD_DIR)
	clang -std=gnu99 -Wall -Wextra -Werror -fno-objc-arc -I. \
		-framework Foundation RSCommandRunner.m host-test/RSCommandRunnerTest.m -o $@

clean:
	rm -rf $(BUILD_DIR)
