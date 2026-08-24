#ifndef __OPENSTEP_BOOT_H
#define __OPENSTEP_BOOT_H

#include "bootstruct.h"

/* True when the selected volume requires the legacy NeXT i386 kernel ABI. */
bool isOpenStepBootVolume(BVRef volume);
void *preserveOpenStepBaseFile(void *binary);

/* Materialize the fixed-address KERNBOOTSTRUCT consumed by OPENSTEP 4.2. */
void *prepareOpenStepBootStruct(entry_t kernelEntry,
                                void *baseFileAddress,
                                unsigned long kernelAddress,
                                unsigned long kernelSize,
                                bool graphicsBoot,
                                const char *driverNames);

#endif /* __OPENSTEP_BOOT_H */
