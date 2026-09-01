# Native Rhapsody DR2/i386 build for the public 3dfx Glide 2 CVG source.

NAME = Glide2
SOURCE_ROOT ?= ../../../out/glide/3dfx-glide-1999
CVG = $(SOURCE_ROOT)/glide2x/cvg
GLIDE_SRC = $(CVG)/glide/src
INIT_SRC = $(CVG)/init
SWLIBS = $(SOURCE_ROOT)/swlibs
BUILD = build

CC = cc
MIG = mig
ARCH_FLAGS = -arch i386
DEFINES = -DGLIDE_LIB=1 -DFX_DLL_BUILD=1
INCLUDES = -I$(BUILD) -I. -I$(GLIDE_SRC) -I$(CVG)/incsrc \
	-I$(INIT_SRC) -I$(SWLIBS)/fxmisc -I$(SWLIBS)/fxmemmap \
	-I$(SWLIBS)/newpci/pcilib
CFLAGS = $(ARCH_FLAGS) -O2 $(DEFINES) $(INCLUDES) -include macosxglide.h

GLIDE_FILES = fifo.c gsplash.c g3df.c gu.c guclip.c gpci.c gump.c \
	diglide.c disst.c ditex.c gbanner.c gerror.c gmovie.c digutex.c \
	ddgump.c gaa.c gdraw.c gglide.c glfb.c gsst.c gtex.c gtexdl.c \
	gutex.c gxdraw.c cpudetect.c
INIT_FILES = dac.c gamma.c gdebug.c info.c parse.c print.c sli.c \
	sst1init.c util.c video.c
MISC_FILES = fxos.c fximg.c
OBJECTS = $(addprefix $(BUILD)/,$(GLIDE_FILES:.c=.o)) \
	$(addprefix $(BUILD)/,$(INIT_FILES:.c=.o)) \
	$(addprefix $(BUILD)/,$(MISC_FILES:.c=.o)) \
	$(BUILD)/macosxglide.o $(BUILD)/V2ServerUser.o

VPATH = $(GLIDE_SRC):$(INIT_SRC):$(SWLIBS)/fxmisc

.PHONY: all framework clean check-source

all: framework

check-source:
	@test -f $(SOURCE_ROOT)/REOPENSTEP_BASELINE_COMMIT || \
		(echo "Run 'make glide-rhapsody-glide-source' on the host first." >&2; exit 1)
	@test "`cat $(SOURCE_ROOT)/REOPENSTEP_BASELINE_COMMIT`" = \
		0de38e8b22542d636b2796be0411b21c0d038500

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/V2Server.h $(BUILD)/V2ServerUser.c: ../V2Server.tproj/V2Server.defs | $(BUILD)
	$(MIG) $(ARCH_FLAGS) -user $(BUILD)/V2ServerUser.c \
		-server /dev/null -header $(BUILD)/V2Server.h $<

$(BUILD)/fxgasm: $(GLIDE_SRC)/fxgasm.c | $(BUILD)
	$(CC) $(CFLAGS) -o $@ $<

$(BUILD)/fxinline.h $(BUILD)/fxgasm.h: $(BUILD)/fxgasm
	$(BUILD)/fxgasm > $(BUILD)/fxgasm.h
	$(BUILD)/fxgasm -inline > $(BUILD)/fxinline.h

$(BUILD)/fxbldno: $(GLIDE_SRC)/fxbldno.c | $(BUILD)
	$(CC) $(CFLAGS) -o $@ $<

$(BUILD)/fxbldno.h: $(BUILD)/fxbldno
	BUILD_NUMBER=254 $(BUILD)/fxbldno > $@

$(BUILD)/parse.o: $(INIT_SRC)/parse.c $(BUILD)/fxinline.h $(BUILD)/fxbldno.h
	$(CC) $(CFLAGS) -Dgetenv=GetDefault -c $< -o $@

$(BUILD)/sst1init.o: $(INIT_SRC)/sst1init.c $(BUILD)/fxinline.h $(BUILD)/fxbldno.h
	$(CC) $(CFLAGS) -Dsst1InitCaching=sst1InitCaching_3dfx -c $< -o $@

$(BUILD)/%.o: %.c $(BUILD)/fxinline.h $(BUILD)/fxbldno.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/macosxglide.o: macosxglide.m $(BUILD)/V2Server.h | $(BUILD)
	$(CC) $(CFLAGS) -ObjC -c $< -o $@

$(BUILD)/V2ServerUser.o: $(BUILD)/V2ServerUser.c $(BUILD)/V2Server.h
	$(CC) $(ARCH_FLAGS) $(INCLUDES) -c $< -o $@

$(BUILD)/Glide2: check-source $(OBJECTS)
	$(CC) $(ARCH_FLAGS) -dynamiclib -o $@ $(OBJECTS) \
		-framework Foundation -framework System -lm \
		-install_name /Library/Frameworks/Glide2.framework/Versions/2/Glide2 \
		-compatibility_version 2.54 -current_version 2.54

framework: $(BUILD)/Glide2
	rm -rf $(BUILD)/Glide2.framework
	mkdir -p $(BUILD)/Glide2.framework/Versions/2/Headers
	cp $(BUILD)/Glide2 $(BUILD)/Glide2.framework/Versions/2/Glide2
	cp $(SWLIBS)/fxmisc/3dfx.h $(BUILD)/Glide2.framework/Versions/2/Headers
	cp $(GLIDE_SRC)/glide.h $(GLIDE_SRC)/glidesys.h \
		$(GLIDE_SRC)/glideutl.h $(GLIDE_SRC)/gump.h \
		$(CVG)/incsrc/sst1vid.h macosxglide.h \
		$(BUILD)/Glide2.framework/Versions/2/Headers
	ln -s 2 $(BUILD)/Glide2.framework/Versions/Current
	ln -s Versions/Current/Glide2 $(BUILD)/Glide2.framework/Glide2
	ln -s Versions/Current/Headers $(BUILD)/Glide2.framework/Headers

clean:
	rm -rf $(BUILD)
