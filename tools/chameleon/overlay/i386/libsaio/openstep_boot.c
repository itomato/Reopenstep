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
#include <mach-o/loader.h>
#include <mach/machine/thread_status.h>

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
#define OPENSTEP_KERNEL_ADDR_OFFSET    0x0000015cU
#define OPENSTEP_KERNEL_SIZE_OFFSET    0x00000160U
#define OPENSTEP_SARLD_ENTRY_OFFSET    0x00000164U
#define OPENSTEP_DRIVER_RECORD_OFFSET  0x00000168U
#define OPENSTEP_CONFIG_OFFSET         0x000024fcU
#define OPENSTEP_CONFIG_LIMIT          0x0000d000U
#ifdef CONFIG_OPENSTEP_SYSTEM_TABLE
#define OPENSTEP_SYSTEM_CONFIG         CONFIG_OPENSTEP_SYSTEM_TABLE
#else
#define OPENSTEP_SYSTEM_CONFIG         "/private/Drivers/i386/System.config/Default.table"
#endif
#define OPENSTEP_SARLD                  "/usr/standalone/i386/sarld"

#define OPENSTEP_BOOT_MAGIC            0xa7a7a7a7U
#define OPENSTEP_LOW_MEMORY_END        0x00020000U
#define OPENSTEP_SARLD_STAGE            0x03000000U
#define OPENSTEP_SARLD_STAGE_SIZE       0x00040000U
#define OPENSTEP_CONFIG_STAGE           0x02000000U
#define OPENSTEP_BOOTSTRUCT_STAGE       0x02100000U
#define OPENSTEP_SARLD_VM_MIN           0x00020000U
#define OPENSTEP_SARLD_VM_MAX           0x00060000U
#define OPENSTEP_SARLD_SAVED_SP         0x0005fff0U
#define OPENSTEP_SARLD_MALLOC           0x00500000U
#define OPENSTEP_SARLD_MALLOC_SIZE      0x00100000U
#define OPENSTEP_SARLD_STACK_TOP        0x00f00000U
#define OPENSTEP_BASEFILE_ADDR          0x01000000U
#define OPENSTEP_BASEFILE_LIMIT         0x01000000U
#define OPENSTEP_DRIVER_NAME_MAX        63U
#define OPENSTEP_DRIVER_LIMIT           64U

typedef int openstep_sa_rld_t(
	char *, struct mach_header *, char *, char *, unsigned long,
	char *, unsigned long *, char *, unsigned long, char *, unsigned long);

/*
 * Chameleon's boot2 stack lives just below 0x20000.  The OPENSTEP standalone
 * linker consumes more stack than that legacy arena provides.  Invoke it on
 * a private high-memory stack, above sarld's 5-6 MiB heap, while preserving
 * the cdecl argument order used by boot v40.13.1.
 */
static int callOpenStepSarld(openstep_sa_rld_t *entry,
	char *basefileName, struct mach_header *basefileAddress,
	char *objectName, char *objectAddress, unsigned long objectSize,
	char *workAddress, unsigned long *workSize,
	char *errorAddress, unsigned long errorSize,
	char *mallocAddress, unsigned long mallocSize)
{
	unsigned long arguments[11];
	int result;

	arguments[0] = (unsigned long)basefileName;
	arguments[1] = (unsigned long)basefileAddress;
	arguments[2] = (unsigned long)objectName;
	arguments[3] = (unsigned long)objectAddress;
	arguments[4] = objectSize;
	arguments[5] = (unsigned long)workAddress;
	arguments[6] = (unsigned long)workSize;
	arguments[7] = (unsigned long)errorAddress;
	arguments[8] = errorSize;
	arguments[9] = (unsigned long)mallocAddress;
	arguments[10] = mallocSize;
	__asm__ volatile (
		"movl %%esp, %0\n\t"
		"movl %3, %%esp\n\t"
		"pushl 40(%%ebx)\n\t"
		"pushl 36(%%ebx)\n\t"
		"pushl 32(%%ebx)\n\t"
		"pushl 28(%%ebx)\n\t"
		"pushl 24(%%ebx)\n\t"
		"pushl 20(%%ebx)\n\t"
		"pushl 16(%%ebx)\n\t"
		"pushl 12(%%ebx)\n\t"
		"pushl 8(%%ebx)\n\t"
		"pushl 4(%%ebx)\n\t"
		"pushl 0(%%ebx)\n\t"
		"call *%%edx\n\t"
		"movl %0, %%esp"
		: "+m" (*(unsigned long *)OPENSTEP_SARLD_SAVED_SP), "=a" (result)
		: "b" (arguments), "i" (OPENSTEP_SARLD_STACK_TOP), "d" (entry)
		: "ecx", "esi", "edi", "memory", "cc");
	return result;
}

static void put32(unsigned char *base, unsigned int offset, unsigned long value)
{
	*(unsigned long *)(base + offset) = value;
}

static unsigned long roundPage(unsigned long value)
{
	return (value + 0xfffU) & ~0xfffU;
}

static bool isDriverNameCharacter(char value)
{
	return (value >= 'a' && value <= 'z') ||
	       (value >= 'A' && value <= 'Z') ||
	       (value >= '0' && value <= '9') || value == '_';
}

static unsigned long openStepKernelExtent(void *baseFileAddress,
	unsigned long kernelAddress, unsigned long fallback)
{
	struct mach_header *header = (struct mach_header *)baseFileAddress;
	struct load_command *command;
	unsigned long index;
	unsigned long end = kernelAddress;

	if (header->magic != MH_MAGIC || header->cputype != CPU_TYPE_I386 ||
	    header->filetype != MH_EXECUTE)
		return fallback;
	command = (struct load_command *)((unsigned char *)header + sizeof(*header));
	for (index = 0; index < header->ncmds; index++) {
		if (command->cmdsize < sizeof(*command))
			return fallback;
		if (command->cmd == LC_SEGMENT) {
			struct segment_command *segment = (struct segment_command *)command;
			unsigned long segmentEnd = segment->vmaddr + segment->vmsize;
			if (segment->vmaddr >= kernelAddress &&
			    segmentEnd <= OPENSTEP_SARLD_MALLOC && segmentEnd > end)
				end = segmentEnd;
		}
		command = (struct load_command *)((unsigned char *)command + command->cmdsize);
	}
	return end > kernelAddress ? roundPage(end - kernelAddress) : fallback;
}

static openstep_sa_rld_t *loadOpenStepSarld(void)
{
	unsigned char *image = (unsigned char *)OPENSTEP_SARLD_STAGE;
	struct mach_header *header;
	struct load_command *command;
	unsigned long length;
	unsigned long index;
	unsigned long entry = 0;

	length = ReadFileAtOffset(OPENSTEP_SARLD, image, 0, OPENSTEP_SARLD_STAGE_SIZE);
	if (length <= sizeof(struct mach_header)) {
		printf("OPENSTEP handoff: cannot load %s\n", OPENSTEP_SARLD);
		return NULL;
	}
	header = (struct mach_header *)image;
	if (header->magic != MH_MAGIC || header->cputype != CPU_TYPE_I386 ||
	    header->filetype != MH_PRELOAD ||
	    sizeof(*header) + header->sizeofcmds > length) {
		printf("OPENSTEP handoff: malformed sarld image\n");
		return NULL;
	}
	command = (struct load_command *)(image + sizeof(*header));
	for (index = 0; index < header->ncmds; index++) {
		if (command->cmdsize < sizeof(*command) ||
		    (unsigned char *)command + command->cmdsize > image + length) {
			printf("OPENSTEP handoff: malformed sarld load command\n");
			return NULL;
		}
		if (command->cmd == LC_SEGMENT) {
			struct segment_command *segment = (struct segment_command *)command;
			unsigned long end = segment->vmaddr + segment->vmsize;
			if (segment->vmaddr < OPENSTEP_SARLD_VM_MIN ||
			    end < segment->vmaddr || end > OPENSTEP_SARLD_VM_MAX ||
			    segment->fileoff + segment->filesize > length ||
			    segment->filesize > segment->vmsize) {
				printf("OPENSTEP handoff: unsafe sarld segment\n");
				return NULL;
			}
			bzero((void *)segment->vmaddr, segment->vmsize);
			bcopy(image + segment->fileoff, (void *)segment->vmaddr,
			      segment->filesize);
		} else if (command->cmd == LC_UNIXTHREAD && command->cmdsize >= 16 + sizeof(i386_thread_state_t)) {
			i386_thread_state_t *state =
				(i386_thread_state_t *)((unsigned char *)command + 16);
			entry = state->eip;
		}
		command = (struct load_command *)((unsigned char *)command + command->cmdsize);
	}
	if (entry < OPENSTEP_SARLD_VM_MIN || entry >= OPENSTEP_SARLD_VM_MAX) {
		printf("OPENSTEP handoff: invalid sarld entry 0x%x\n", entry);
		return NULL;
	}
	verbose("OPENSTEP handoff: sarld entry=0x%x size=%u\n", entry, length);
	return (openstep_sa_rld_t *)entry;
}

static long appendOpenStepDriverTables(unsigned char *config, long length,
	const char *names)
{
	const char *cursor = names;

	if (!names)
		return length;
	while (*cursor) {
		char driver[OPENSTEP_DRIVER_NAME_MAX + 1];
		char path[192];
		unsigned long index = 0;
		long tableLength;
		const char *preferredTable = "Default";
		const char *bundle = driver;

		while (*cursor == ' ' || *cursor == '\t')
			cursor++;
		while (*cursor && *cursor != ' ' && *cursor != '\t') {
			char value = *cursor++;
			if (!isDriverNameCharacter(value) || index == OPENSTEP_DRIVER_NAME_MAX) {
				printf("OPENSTEP handoff: invalid driver table name\n");
				return length;
			}
			driver[index++] = value;
		}
		if (index == 0)
			break;
		driver[index] = '\0';
		#if CONFIG_OPENSTEP_AMD_ALIAS
		if (strcmp(driver, "AMDPCSCSIDriver") == 0)
			bundle = "AMD";
		#endif
		/* Select the modern Socket 370/QEMU hardware instances. The generic
		 * EIDE table exposes only the primary channel; the beta driver's
		 * EIDE_PIIX profile publishes both channels and matches PIIX3/PIIX4. */
		if (strcmp(driver, "EIDE") == 0)
#ifdef CONFIG_OPENSTEP_EIDE_TABLE
			preferredTable = CONFIG_OPENSTEP_EIDE_TABLE;
#else
			preferredTable = "EIDE_PIIX";
#endif
		else if (strcmp(driver, "MatroxMGA2064WDisplayDriver") == 0)
			preferredTable = "PCI8MB";
		if (length + 2 >= OPENSTEP_CONFIG_LIMIT) {
			printf("OPENSTEP handoff: configuration table area exhausted\n");
			return length;
		}
		config[length++] = '\0';
		/* Prefer the selected hardware profile, then the driver's named table,
		 * and finally the generic Default.table used by bus bundles. */
		snprintf(path, sizeof(path),
		         "/private/Drivers/i386/%s.config/%s.table", bundle,
		         preferredTable);
		tableLength = ReadFileAtOffset(path, config + length, 0,
		                                   OPENSTEP_CONFIG_LIMIT - length - 2);
		if (tableLength <= 0 && strcmp(preferredTable, driver) != 0) {
			snprintf(path, sizeof(path),
			         "/private/Drivers/i386/%s.config/%s.table", bundle,
			         driver);
			tableLength = ReadFileAtOffset(path, config + length, 0,
			                                   OPENSTEP_CONFIG_LIMIT - length - 2);
		}
		if (tableLength <= 0) {
			snprintf(path, sizeof(path),
			         "/private/Drivers/i386/%s.config/Default.table", bundle);
			tableLength = ReadFileAtOffset(path, config + length, 0,
			                                   OPENSTEP_CONFIG_LIMIT - length - 2);
		}
		/* The PS/2 table is tiny and stable across the 4.2 driver drops. Keep
		 * a copy in BootE so a damaged/odd UFS directory cannot strand the
		 * keyboard before the installer gets control. */
		if (tableLength <= 0 && strcmp(driver, "PS2Keyboard") == 0) {
			static const char keyboardTable[] =
				"\"Title\" = \"PS2Keyboard\";\n"
				"\"Family\" = \"Keyboard\";\n"
				"\"Version\" = \"4.01\";\n"
				"\"Location\" = \"\";\n"
				"\"Instance\" = \"0\";\n"
				"\"Driver Name\" = \"PS2Keyboard\";\n"
				"\"Class Names\" = \"PS2Controller PS2Keyboard\";\n"
				"\"IRQ Levels\" = \"1\";\n"
				"\"Valid IRQ Levels\" = \"1\";\n"
				"\"I/O Ports\" = \"0x60-0x65\";\n"
				"\"Memory Maps\" = \"\";\n"
				"\"DMA Channels\" = \"\";\n"
				"\"Boot Driver\";\n"
				"\"Interface\" = \"3\";\n"
				"\"Handler ID\" = \"0\";\n"
				"\"Server Name\" = \"PS2Keyboard\";\n"
				"\"Driver Version\" = \"PROGRAM:PS2Keyboard PROJECT:drvPS2Keyboard-7\";\n";
			tableLength = sizeof(keyboardTable) - 1;
			bcopy(keyboardTable, config + length, tableLength);
		}
		if (tableLength <= 0 && strcmp(driver, "PS2Mouse") == 0) {
			static const char mouseTable[] =
				"\"Title\" = \"PS2Mouse\";\n"
				"\"Family\" = \"Pointing Device\";\n"
				"\"Version\" = \"4.00\";\n"
				"\"Location\" = \"\";\n"
				"\"Instance\" = \"0\";\n"
				"\"Driver Name\" = \"PS2Mouse\";\n"
				"\"Class Names\" = \"PS2Mouse\";\n"
				"\"IRQ Levels\" = \"12\";\n"
				"\"Valid IRQ Levels\" = \"12\";\n"
				"\"I/O Ports\" = \"\";\n"
				"\"Inverted\" = \"No\";\n"
				"\"Resolution\" = \"150\";\n"
				"\"Force Detection\" = \"No\";\n"
				"\"Server Name\" = \"PS2Mouse\";\n";
			tableLength = sizeof(mouseTable) - 1;
			bcopy(mouseTable, config + length, tableLength);
		}
		if (tableLength <= 0 || tableLength > OPENSTEP_CONFIG_LIMIT - length - 2) {
			printf("OPENSTEP handoff: cannot load driver table %s\n", driver);
			length--;
			continue;
		}
		length += tableLength;
	}
	return length;
}

static long setOpenStepBootDrivers(unsigned char *config, long length,
	const char *names)
{
	static const char key[] = "\"Boot Drivers\" = \"";
	long i;
	long oldLength;
	long newLength;
	long delta;
	long tail;

	if (!names)
		return length;
	newLength = strlen(names);
	for (i = 0; i + sizeof(key) - 1 < length; i++) {
		long start;
		long end;
		long j;

		if (memcmp(config + i, key, sizeof(key) - 1) != 0)
			continue;
		start = i + sizeof(key) - 1;
		end = start;
		while (end < length && config[end] != '"')
			end++;
		if (end == length)
			break;
		oldLength = end - start;
		delta = newLength - oldLength;
		if (length + delta + 2 >= OPENSTEP_CONFIG_LIMIT) {
			printf("OPENSTEP handoff: Boot Drivers list is too large\n");
			return length;
		}
		tail = length - end;
		if (delta > 0) {
			for (j = tail - 1; j >= 0; j--)
				config[end + delta + j] = config[end + j];
		} else if (delta < 0) {
			for (j = 0; j < tail; j++)
				config[end + delta + j] = config[end + j];
		}
		bcopy(names, config + start, newLength);
		return length + delta;
	}
	printf("OPENSTEP handoff: Boot Drivers key not found\n");
	return length;
}

static unsigned long linkOpenStepDrivers(unsigned char *legacy,
	void *baseFileAddress, unsigned long kernelAddress,
	unsigned long kernelSize, const char *names)
{
	openstep_sa_rld_t *sa_rld;
	unsigned long output = roundPage(kernelAddress + kernelSize);
	unsigned long count = 0;
	const char *cursor = names;

	if (!names || !*names || !baseFileAddress)
		return kernelSize;
	sa_rld = loadOpenStepSarld();
	if (!sa_rld)
		return kernelSize;
	put32(legacy, OPENSTEP_SARLD_ENTRY_OFFSET, (unsigned long)sa_rld);
	while (*cursor && count < OPENSTEP_DRIVER_LIMIT) {
		char driver[OPENSTEP_DRIVER_NAME_MAX + 1];
		char path[192];
		char errors[256];
		unsigned long length;
		unsigned long workSize;
		unsigned long index = 0;
		unsigned long *record;
		const char *bundle;
		const char *reloc;
		int status;

		while (*cursor == ' ' || *cursor == '\t')
			cursor++;
		while (*cursor && *cursor != ' ' && *cursor != '\t') {
			char value = *cursor++;
			if (!isDriverNameCharacter(value) || index == OPENSTEP_DRIVER_NAME_MAX) {
				printf("OPENSTEP handoff: invalid standalone driver name\n");
				return output - kernelAddress;
			}
			driver[index++] = value;
		}
		if (index == 0)
			break;
		driver[index] = '\0';
		bundle = driver;
		reloc = driver;
		#if CONFIG_OPENSTEP_AMD_ALIAS
		if (strcmp(driver, "AMDPCSCSIDriver") == 0) {
			bundle = "AMD";
			reloc = "AMD";
		}
		#endif
		snprintf(path, sizeof(path),
		         "/private/Drivers/i386/%s.config/%s_reloc", bundle, reloc);
		length = ReadFileAtOffset(path, (void *)OPENSTEP_SARLD_STAGE, 0,
		                          OPENSTEP_SARLD_STAGE_SIZE);
		if (length <= 0 || length == OPENSTEP_SARLD_STAGE_SIZE) {
			printf("OPENSTEP handoff: cannot load standalone driver %s\n", driver);
			return output - kernelAddress;
		}
		if (output >= OPENSTEP_SARLD_MALLOC) {
			printf("OPENSTEP handoff: standalone driver area exhausted\n");
			return output - kernelAddress;
		}
		workSize = OPENSTEP_SARLD_MALLOC - output;
		errors[0] = '\0';
		status = callOpenStepSarld(sa_rld,
			"mach_kernel", (struct mach_header *)baseFileAddress,
			driver, (char *)OPENSTEP_SARLD_STAGE, length,
			(char *)output, &workSize, errors, sizeof(errors),
			(char *)OPENSTEP_SARLD_MALLOC, OPENSTEP_SARLD_MALLOC_SIZE);
		if (status != 1 || workSize == 0 || output + workSize > OPENSTEP_SARLD_MALLOC) {
			printf("OPENSTEP handoff: sarld failed for %s: %s\n", driver, errors);
			return output - kernelAddress;
		}
		record = (unsigned long *)(legacy + OPENSTEP_DRIVER_RECORD_OFFSET + count * 8);
		record[0] = output;
		record[1] = workSize;
		count++;
		put32(legacy, OPENSTEP_DRIVER_COUNT_OFFSET, count);
		output += workSize;
		put32(legacy, OPENSTEP_KERNEL_SIZE_OFFSET, output - kernelAddress);
		verbose("OPENSTEP handoff: linked %s at 0x%x size=0x%x\n",
		        driver, record[0], record[1]);
	}
	return output - kernelAddress;
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

static void forceOpenStepSafeEIDE(unsigned char *config, long length)
{
	static const char key[] = "\"Multiple Sectors\" = \"Yes\"";
	long i;

	for (i = 0; i + sizeof(key) - 1 <= length; i++) {
		if (memcmp(config + i, key, sizeof(key) - 1) == 0) {
			config[i + sizeof(key) - 5] = 'N';
			config[i + sizeof(key) - 4] = 'o';
			config[i + sizeof(key) - 3] = '"';
			config[i + sizeof(key) - 2] = ' ';
		}
	}
}

static long forceOpenStepPrimaryEIDE(unsigned char *config, long length)
{
	static const char ports[] = "\"I/O Ports\" = \"0x1f0-0x1f7 0x170-0x177\"";
	static const char primaryPorts[] = "\"I/O Ports\" = \"0x1f0-0x1f7\"";
	long i;

	for (i = 0; i + sizeof(ports) - 1 <= length; i++) {
		if (memcmp(config + i, ports, sizeof(ports) - 1) == 0) {
			long oldLength = sizeof(ports) - 1;
			long newLength = sizeof(primaryPorts) - 1;
			long tail = length - i - oldLength;
			bcopy(config + i + oldLength, config + i + newLength, tail);
			bcopy(primaryPorts, config + i, newLength);
			length -= oldLength - newLength;
			break;
		}
	}
	return length;
}

static long forceOpenStepATAPISlave(unsigned char *config, long length)
{
	static const char key[] = "\"ATAPI Device\" = \"\";";
	static const char value[] = "Slave";
	long i;
	long j;
	long insertion = sizeof(key) - 3;

	for (i = 0; i + sizeof(key) - 1 <= length; i++) {
		if (memcmp(config + i, key, sizeof(key) - 1) != 0)
			continue;
		if (length + sizeof(value) - 1 >= OPENSTEP_CONFIG_LIMIT) {
			printf("OPENSTEP handoff: cannot force ATAPI slave; table area exhausted\n");
			return length;
		}
		for (j = length - 1; j >= i + insertion; j--)
			config[j + sizeof(value) - 1] = config[j];
		bcopy(value, config + i + insertion, sizeof(value) - 1);
		return length + sizeof(value) - 1;
	}
	printf("OPENSTEP handoff: ATAPI Device key not found\n");
	return length;
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

void *preserveOpenStepBaseFile(void *binary)
{
	void *thin = binary;
	struct mach_header *header;
	struct load_command *command;
	unsigned long length = 0;
	unsigned long index;
	long fatResult;

	fatResult = ThinFatFile(&thin, &length);
	header = (struct mach_header *)thin;
	if (fatResult != 0) {
		/* LoadThinFatFile has already reduced universal kernels to a thin
		 * image.  Recover that image's length from its segment file ranges. */
		if (header->magic != MH_MAGIC || header->cputype != CPU_TYPE_I386 ||
		    header->filetype != MH_EXECUTE)
			length = 0;
		else {
			length = sizeof(*header) + header->sizeofcmds;
			command = (struct load_command *)((unsigned char *)header + sizeof(*header));
			for (index = 0; index < header->ncmds; index++) {
				if (command->cmdsize < sizeof(*command)) {
					length = 0;
					break;
				}
				if (command->cmd == LC_SEGMENT) {
					struct segment_command *segment = (struct segment_command *)command;
					unsigned long fileEnd = segment->fileoff + segment->filesize;
					if (fileEnd < segment->fileoff) {
						length = 0;
						break;
					}
					if (fileEnd > length)
						length = fileEnd;
				}
				command = (struct load_command *)((unsigned char *)command +
				                                  command->cmdsize);
			}
		}
	}
	if (length == 0 || length > OPENSTEP_BASEFILE_LIMIT) {
		printf("OPENSTEP handoff: cannot preserve thin kernel basefile\n");
		return NULL;
	}
	bcopy(thin, (void *)OPENSTEP_BASEFILE_ADDR, length);
	header = (struct mach_header *)OPENSTEP_BASEFILE_ADDR;
	if (header->magic != MH_MAGIC ||
	    sizeof(*header) + header->sizeofcmds > length)
		return NULL;
	command = (struct load_command *)((unsigned char *)header + sizeof(*header));
	for (index = 0; index < header->ncmds; index++) {
		if (command->cmdsize < sizeof(*command) ||
		    (unsigned char *)command + command->cmdsize >
		        (unsigned char *)header + length)
			return NULL;
		if (command->cmd == LC_SEGMENT) {
			struct segment_command *segment = (struct segment_command *)command;
			if (memcmp(segment->segname, SEG_LINKEDIT,
			           sizeof(SEG_LINKEDIT) - 1) == 0) {
				if (segment->fileoff + segment->filesize > length)
					return NULL;
				segment->vmaddr = OPENSTEP_BASEFILE_ADDR + segment->fileoff;
				segment->vmsize = segment->filesize;
			}
		}
		command = (struct load_command *)((unsigned char *)command +
		                                  command->cmdsize);
	}
	return (void *)OPENSTEP_BASEFILE_ADDR;
}

void *prepareOpenStepBootStruct(entry_t kernelEntry,
                                void *baseFileAddress,
                                unsigned long kernelAddress,
                                unsigned long kernelSize,
                                bool graphicsBoot,
                                const char *driverNames)
{
	unsigned char *legacy = (unsigned char *)BOOTSTRUCT_ADDR;
	unsigned char *config = (unsigned char *)OPENSTEP_CONFIG_STAGE;
	unsigned char *stagedBootStruct = (unsigned char *)OPENSTEP_BOOTSTRUCT_STAGE;
	char commandLine[OPENSTEP_BOOT_MAGIC_OFFSET - OPENSTEP_BOOT_STRING_OFFSET];
	char bootFile[0x40];
	unsigned long convmem = bootInfo->convmem;
	unsigned long extmem = bootInfo->extmem;
	unsigned long biosdev = gBootVolume ? (unsigned long)gBootVolume->biosdev : 0x80U;
	long configLength;

	(void)kernelEntry;
	kernelSize = openStepKernelExtent(baseFileAddress, kernelAddress, kernelSize);

	/*
	 * Snapshot first: Chameleon's PrivateBootInfo also begins at 0x11000.
	 * Its stack is near 0x1fff0, so clearing the historical 60 KiB arena here
	 * would erase both live state and our return address.
	 */
#ifdef CONFIG_OPENSTEP_KERNEL_FLAGS
	strlcpy(commandLine, CONFIG_OPENSTEP_KERNEL_FLAGS, sizeof(commandLine));
#else
	strlcpy(commandLine, bootArgs->CommandLine, sizeof(commandLine));
#endif
	strlcpy(bootFile, bootInfo->bootFile, sizeof(bootFile));
	configLength = ReadFileAtOffset(
		OPENSTEP_SYSTEM_CONFIG, config, 0,
		OPENSTEP_CONFIG_LIMIT - 2);
	if (configLength <= 0 || configLength > OPENSTEP_CONFIG_LIMIT - 2) {
		printf("OPENSTEP handoff: cannot load %s\n", OPENSTEP_SYSTEM_CONFIG);
		configLength = 0;
	}
	configLength = setOpenStepBootDrivers(
		config, configLength, driverNames);
	configLength = appendOpenStepDriverTables(
		config, configLength, driverNames);
#if CONFIG_OPENSTEP_ATAPI_SLAVE
	configLength = forceOpenStepATAPISlave(
		config, configLength);
#endif
#if CONFIG_OPENSTEP_EIDE_SAFE
	forceOpenStepSafeEIDE(config, configLength);
#endif
#if CONFIG_OPENSTEP_EIDE_PRIMARY_ONLY
	configLength = forceOpenStepPrimaryEIDE(config, configLength);
#endif
	if (configLength > 0 && !graphicsBoot)
		forceOpenStepTextBoot(config, configLength);
	bzero(stagedBootStruct, OPENSTEP_DRIVER_RECORD_OFFSET +
	      OPENSTEP_DRIVER_LIMIT * 2 * sizeof(unsigned long));
	kernelSize = linkOpenStepDrivers(
		stagedBootStruct, baseFileAddress, kernelAddress, kernelSize, driverNames);

	/* Do not touch Chameleon's live 0x11000 PrivateBootInfo until every UFS
	 * read and standalone link has completed. */
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
	put32(legacy, OPENSTEP_DRIVER_COUNT_OFFSET,
	      *(unsigned long *)(stagedBootStruct + OPENSTEP_DRIVER_COUNT_OFFSET));
	put32(legacy, OPENSTEP_KERNEL_ADDR_OFFSET, kernelAddress);
	put32(legacy, OPENSTEP_KERNEL_SIZE_OFFSET, kernelSize);
	put32(legacy, OPENSTEP_SARLD_ENTRY_OFFSET,
	      *(unsigned long *)(stagedBootStruct + OPENSTEP_SARLD_ENTRY_OFFSET));
	put32(legacy, OPENSTEP_CONFIG_END_OFFSET,
	      BOOTSTRUCT_ADDR + OPENSTEP_CONFIG_OFFSET + configLength);
	bcopy(stagedBootStruct + OPENSTEP_DRIVER_RECORD_OFFSET,
	      legacy + OPENSTEP_DRIVER_RECORD_OFFSET,
	      *(unsigned long *)(stagedBootStruct + OPENSTEP_DRIVER_COUNT_OFFSET) *
	      2 * sizeof(unsigned long));
	/* Chameleon's PrivateBootInfo also occupies 0x11000 while the loader is
	 * active.  Publish the completed native tables only after the final UFS
	 * access and standalone link, immediately before kernel handoff. */
	bcopy(config, legacy + OPENSTEP_CONFIG_OFFSET, configLength);
	legacy[OPENSTEP_CONFIG_OFFSET + configLength] = '\0';
	legacy[OPENSTEP_CONFIG_OFFSET + configLength + 1] = '\0';

	verbose("OPENSTEP handoff: KERNBOOTSTRUCT=0x%x lowmem=0x%x conv=%uKB ext=%uKB config=%d graphics=%d drivers=%u extent=0x%x\n",
	        BOOTSTRUCT_ADDR, OPENSTEP_LOW_MEMORY_END,
	        convmem, extmem, configLength, graphicsBoot,
	        *(unsigned long *)(legacy + OPENSTEP_DRIVER_COUNT_OFFSET), kernelSize);
	return legacy;
}
