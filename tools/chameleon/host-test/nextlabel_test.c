#include <stdio.h>
#include <string.h>

#include "nextlabel.h"

#define CHECKSUM_OFFSET 0x22e

static void put16(unsigned char *p, unsigned int value)
{
    p[0] = value >> 8;
    p[1] = value;
}

static void put24(unsigned char *p, unsigned int value)
{
    p[0] = value >> 16;
    p[1] = value >> 8;
    p[2] = value;
}

static void put32(unsigned char *p, unsigned int value)
{
    p[0] = value >> 24;
    p[1] = value >> 16;
    p[2] = value >> 8;
    p[3] = value;
}

static unsigned int checksum(const unsigned char *label)
{
    unsigned int offset;
    unsigned int sum = 0;

    for (offset = 0; offset < CHECKSUM_OFFSET; offset += 2) {
        unsigned int word = ((unsigned int)label[offset] << 8) | label[offset + 1];
        if (offset == 4 || offset == 6)
            word = 0;
        sum += word;
        if (sum > 0xffff)
            sum -= 0xffff;
    }
    return sum;
}

int main(int argc, char **argv)
{
    unsigned char label[1024];
    unsigned int sectors = 0;

    memset(label, 0, sizeof(label));
    memcpy(label, "dlV3", 4);
    put32(label + 4, 15);
    put16(label + 0x5e, 1024);
    put16(label + 0x70, 160);
    label[0xbc] = 'a';
    put24(label + 0xc0, 0);
    put24(label + 0xc3, 515936);
    memcpy(label + 0xc0 + 0x23, "4.3BSD", 6);
    put16(label + CHECKSUM_OFFSET, checksum(label));

    if (NeXTLabelUFSOffset(label, sizeof(label), 15, &sectors) != 0 || sectors != 320) {
        fprintf(stderr, "whole-disk root offset: got %u sectors\n", sectors);
        return 1;
    }
    put24(label + 0xc0, 4);
    put16(label + CHECKSUM_OFFSET, 0);
    put16(label + CHECKSUM_OFFSET, checksum(label));
    if (NeXTLabelUFSOffset(label, sizeof(label), 15, &sectors) != 0 || sectors != 328) {
        fprintf(stderr, "partition-relative root offset: got %u sectors\n", sectors);
        return 1;
    }
    label[100] ^= 1;
    if (NeXTLabelUFSOffset(label, sizeof(label), 15, &sectors) == 0) {
        fputs("invalid checksum was accepted\n", stderr);
        return 1;
    }
    if (argc > 1) {
        static const unsigned int copies[] = { 0, 15, 30, 45 };
        FILE *disk = fopen(argv[1], "rb");
        unsigned int i;
        int found = 0;
        if (!disk) {
            perror(argv[1]);
            return 1;
        }
        for (i = 0; i < sizeof(copies) / sizeof(copies[0]); i++) {
            if (fseek(disk, copies[i] * 512L, SEEK_SET) != 0 ||
                fread(label, 1, sizeof(label), disk) != sizeof(label))
                continue;
            if (NeXTLabelUFSOffset(label, sizeof(label), copies[i], &sectors) == 0) {
                printf("%s: root UFS sector %u (byte %u)\n", argv[1], sectors, sectors * 512);
                found = 1;
                break;
            }
        }
        fclose(disk);
        if (!found) {
            fprintf(stderr, "%s: no valid dlV3 root label\n", argv[1]);
            return 1;
        }
    }
    puts("NeXT dlV3 parser: ok");
    return 0;
}
