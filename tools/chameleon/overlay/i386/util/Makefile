SRCROOT = $(abspath $(CURDIR)/../..)
OBJROOT = $(SRCROOT)/obj/i386/util
SYMROOT = $(SRCROOT)/sym/i386
DSTROOT = $(SRCROOT)/dst/i386
DOCROOT = $(SRCROOT)/doc
IMGROOT = $(SRCROOT)/sym/cache
IMGSKELROOT = $(SRCROOT)/imgskel
CDBOOT = ${IMGROOT}/usr/standalone/i386/cdboot

DIR = util
include ${SRCROOT}/Make.rules

# These are build-host utilities, not booter payloads. Building them for the
# native host avoids obsolete i386 libSystem/framework link dependencies.
PROGRAMS = machOconv dyldsymboltool segsize
OBJS = machOconv.o dyldsymboltool.o segsize.o

ifeq (${CONFIG_BDMESG}, y)
PROGRAMS += bdmesg
OBJS += bdmesg.o
endif

ifeq (${CONFIG_OPENUP}, y)
PROGRAMS += openUp
OBJS += openUp.o
endif

OBJS := $(addprefix $(OBJROOT)/, $(OBJS))
SYMPROG := $(addprefix $(SYMROOT)/, $(PROGRAMS))
DIRS_NEEDED = $(OBJROOT) $(SYMROOT)
LDFLAGS = -framework IOKit -framework CoreFoundation
SUBDIRS = fdisk

all: $(DIRS_NEEDED) $(SYMPROG) all-recursive

$(SYMPROG): $(SYMROOT)/%: $(OBJROOT)/%.o
	@echo "\t[HOSTLD] $(@F)"
	@$(CC) $(CFLAGS) $(LDFLAGS) $(DEFINES) -o $@ $<

-include $(OBJROOT)/Makedep

clean-local:
	@rm -f $(SYMPROG) $(OBJS)
