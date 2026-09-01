# Project Builder 2.6 kernel-server project for Rhapsody DR2/i386.

NAME = Voodoo2
PROJECTVERSION = 2.6
PROJECT_TYPE = KernelServer
LANGUAGE = English

MFILES = Voodoo2.m
CFILES = V2DriverServer.c
DEFSFILES = V2Driver.defs
OTHERSRCS = Makefile Voodoo2.h V2Driver.defs Load_Commands.sect

MAKEFILEDIR = $(MAKEFILEPATH)/pb_makefiles
MAKEFILE = kernelserver.make

include $(MAKEFILEDIR)/platform.make
-include Makefile.preamble
include $(MAKEFILEDIR)/$(MAKEFILE)
-include Makefile.postamble
-include Makefile.dependencies
