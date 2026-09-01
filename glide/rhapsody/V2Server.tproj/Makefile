# Project Builder 2.6 tool project for Rhapsody DR2/i386.

NAME = V2Server
PROJECTVERSION = 2.6
PROJECT_TYPE = Tool
LANGUAGE = English

MFILES = V2Server_main.m
CFILES = V2Server.c V2ServerServer.c V2DriverUser.c
DEFSFILES = V2Server.defs
HFILES = V2Server.h
OTHERSRCS = Makefile
OTHER_GENERATED_SRCFILES = V2Driver.h V2DriverUser.c

V2DRIVER_DEFS = ../Voodoo2.lksproj/V2Driver.defs

V2Driver.h V2DriverUser.c: $(V2DRIVER_DEFS)
	$(MIG) $(ALL_MIGFLAGS) $(V2DRIVER_DEFS)

MAKEFILEDIR = $(MAKEFILEPATH)/pb_makefiles
MAKEFILE = tool.make
LIBS = -lDriver

include $(MAKEFILEDIR)/platform.make
-include Makefile.preamble
include $(MAKEFILEDIR)/$(MAKEFILE)
-include Makefile.postamble
-include Makefile.dependencies
