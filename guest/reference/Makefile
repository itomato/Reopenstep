ARCHS = m68k i386 hppa sparc
CC = cc
ARCH_FLAGS = $(foreach arch,$(ARCHS),-arch $(arch))

all: hello

hello: hello.c
	$(CC) $(ARCH_FLAGS) -o $@ hello.c
	@echo "Verify with: lipo -info hello"

clean:
	rm -f hello
