/*
 * OPENSTEP 4.2 i386 kernel handoff adapter.
 *
 * Unlike Darwin, this kernel does not consume the pointer passed in EAX.  It
 * reads a NeXT KERNBOOTSTRUCT from physical address 0x11000.  Keep the layout
 * expressed as checked offsets until the remaining standalone-driver fields
 * have been recovered from boot v40.13.1.
 */

#include "libsaio.h"
#include "bootstruct.h"
#include "memory.h"
#include "openstep_boot.h"

#define OPENSTEP_BOOT_STRING_OFFSET    0x00000002U
#define OPENSTEP_BOOT_MAGIC_OFFSET     0x000000a4U
#define OPENSTEP_BOOT_DEVICE_OFFSET    0x000000acU
#define OPENSTEP_CONVMEM_OFFSET        0x000000b0U
#define OPENSTEP_EXTMEM_OFFSET         0x000000b4U
#define OPENSTEP_BOOT_FILE_OFFSET      0x000000b8U
#define OPENSTEP_LOW_MEMORY_OFFSET     0x00000138U
#define OPENSTEP_DISPLAY_MODE_OFFSET   0x0000014cU
#define OPENSTEP_BOOT_MODE_OFFSET      0x00000150U
#define OPENSTEP_DRIVER_COUNT_OFFSET   0x00000154U
#define OPENSTEP_CONFIG_END_OFFSET     0x00000158U
#define OPENSTEP_CONFIG_OFFSET         0x000024fcU
#define OPENSTEP_CONFIG_LIMIT          0x0000d000U
#define OPENSTEP_SYSTEM_CONFIG         "/private/Drivers/i386/System.config/Default.table"

#define OPENSTEP_BOOT_MAGIC            0xa7a7a7a7U
#define OPENSTEP_LOW_MEMORY_END        0x00020000U

static void put32(unsigned char *base, unsigned int offset, unsigned long value)
{
	*(unsigned long *)(base + offset) = value;
}

static void forceOpenStepTextBoot(unsigned char *config, long length)
{
	static const char key[] = "\"Boot Graphics\" = \"Yes\"";
	long i;

	for (i = 0; i + sizeof(key) - 1 <= length; i++) {
		if (memcmp(config + i, key, sizeof(key) - 1) == 0) {
			config[i + sizeof(key) - 5] = 'N';
			config[i + sizeof(key) - 4] = 'o';
			config[i + sizeof(key) - 3] = ' ';
			return;
		}
	}
}

bool isOpenStepBootVolume(BVRef volume)
{
#if CONFIG_OPENSTEP_HANDOFF
	return volume && strcmp(volume->type_name, "NeXT UFS") == 0;
#else
	(void)volume;
	return false;
#endif
}

void *prepareOpenStepBootStruct(entry_t kernelEntry,
                                unsigned long kernelAddress,
                                unsigned long kernelSize,
                                bool graphicsBoot)
{
	unsigned char *legacy = (unsigned char *)BOOTSTRUCT_ADDR;
	char commandLine[OPENSTEP_BOOT_MAGIC_OFFSET - OPENSTEP_BOOT_STRING_OFFSET];
	char bootFile[0x40];
	unsigned long convmem = bootInfo->convmem;
	unsigned long extmem = bootInfo->extmem;
	unsigned long biosdev = gBootVolume ? (unsigned long)gBootVolume->biosdev : 0x80U;
	long configLength;

	(void)kernelEntry;
	(void)kernelAddress;
	(void)kernelSize;

	/*
	 * Snapshot first: Chameleon's PrivateBootInfo also begins at 0x11000.
	 * Its stack is near 0x1fff0, so clearing the historical 60 KiB arena here
	 * would erase both live state and our return address.
	 */
	strlcpy(commandLine, bootArgs->CommandLine, sizeof(commandLine));
	strlcpy(bootFile, bootInfo->bootFile, sizeof(bootFile));
	configLength = LoadFile(OPENSTEP_SYSTEM_CONFIG);
	if (configLength <= 0 || configLength > OPENSTEP_CONFIG_LIMIT - 2) {
		printf("OPENSTEP handoff: cannot load %s\n", OPENSTEP_SYSTEM_CONFIG);
		configLength = 0;
	}
	if (configLength > 0 && !graphicsBoot)
		forceOpenStepTextBoot((unsigned char *)kLoadAddr, configLength);
	strlcpy((char *)legacy + OPENSTEP_BOOT_STRING_OFFSET,
	        commandLine,
	        OPENSTEP_BOOT_MAGIC_OFFSET - OPENSTEP_BOOT_STRING_OFFSET);
	put32(legacy, OPENSTEP_BOOT_MAGIC_OFFSET, OPENSTEP_BOOT_MAGIC);
	put32(legacy, OPENSTEP_BOOT_DEVICE_OFFSET, biosdev);
	put32(legacy, OPENSTEP_CONVMEM_OFFSET, convmem);
	put32(legacy, OPENSTEP_EXTMEM_OFFSET, extmem);
	strlcpy((char *)legacy + OPENSTEP_BOOT_FILE_OFFSET,
	        bootFile,
	        0x40);

	/*
	 * Native boot v40.13.1 places its low-memory allocation floor just
	 * beyond KERNBOOTSTRUCT/configuration storage.  BootE occupies the whole
	 * 0x11000-0x1ffff legacy arena, so the first page safe for the kernel is
	 * 0x20000.  A zero value allocates the initial page directory at address
	 * zero and causes the observed CR3=0 triple fault.
	 */
	put32(legacy, OPENSTEP_LOW_MEMORY_OFFSET, OPENSTEP_LOW_MEMORY_END);
	put32(legacy, OPENSTEP_DISPLAY_MODE_OFFSET, graphicsBoot ? 1 : 0);
	put32(legacy, OPENSTEP_BOOT_MODE_OFFSET, 0);
	put32(legacy, OPENSTEP_DRIVER_COUNT_OFFSET, 0);
	put32(legacy, OPENSTEP_CONFIG_END_OFFSET,
	      BOOTSTRUCT_ADDR + OPENSTEP_CONFIG_OFFSET + configLength);
	if (configLength > 0)
		bcopy((void *)kLoadAddr, legacy + OPENSTEP_CONFIG_OFFSET, configLength);
	legacy[OPENSTEP_CONFIG_OFFSET + configLength] = '\0';
	legacy[OPENSTEP_CONFIG_OFFSET + configLength + 1] = '\0';

	verbose("OPENSTEP handoff: KERNBOOTSTRUCT=0x%x lowmem=0x%x conv=%uKB ext=%uKB config=%d graphics=%d\n",
	        BOOTSTRUCT_ADDR, OPENSTEP_LOW_MEMORY_END,
	        convmem, extmem, configLength, graphicsBoot);
	return legacy;
}
