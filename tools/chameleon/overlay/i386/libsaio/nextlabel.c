#include "libsaio.h"
#include "nextlabel.h"

#define NEXT_LABEL_SIZE       1024U
#define NEXT_CHECKSUM_OFFSET  0x22eU
#define NEXT_SECSIZE_OFFSET   0x05eU
#define NEXT_FRONT_OFFSET     0x070U
#define NEXT_ROOT_OFFSET      0x0bcU
#define NEXT_PART_OFFSET      0x0c0U
#define NEXT_PART_SIZE        0x040U
#define NEXT_PART_TYPE        0x023U

static unsigned int be16(const unsigned char *p)
{
    return ((unsigned int)p[0] << 8) | p[1];
}

static unsigned int be24(const unsigned char *p)
{
    return ((unsigned int)p[0] << 16) | ((unsigned int)p[1] << 8) | p[2];
}

static unsigned int be32(const unsigned char *p)
{
    return ((unsigned int)p[0] << 24) | ((unsigned int)p[1] << 16) |
           ((unsigned int)p[2] << 8) | p[3];
}

static unsigned int dlV3Checksum(const unsigned char *label)
{
    unsigned int offset;
    unsigned int sum = 0;

    for (offset = 0; offset < NEXT_CHECKSUM_OFFSET; offset += 2) {
        unsigned int word = be16(label + offset);
        if (offset == 4 || offset == 6)
            word = 0;
        sum += word;
        if (sum > 0xffffU)
            sum -= 0xffffU;
    }
    return sum;
}

int NeXTLabelUFSOffset(const unsigned char *label, unsigned int labelBytes,
                       unsigned int labelSector, unsigned int *ufsSectors)
{
    const unsigned char *part;
    unsigned int secsize;
    unsigned int front;
    unsigned int base;
    unsigned int size;
    unsigned int root;
    unsigned long long sectors;

    if (!label || !ufsSectors || labelBytes < NEXT_LABEL_SIZE)
        return -1;
    if (be32(label) != 0x646c5633U || be32(label + 4) != labelSector)
        return -1;
    if (be16(label + NEXT_CHECKSUM_OFFSET) != dlV3Checksum(label))
        return -1;
    if (label[NEXT_ROOT_OFFSET] < 'a' || label[NEXT_ROOT_OFFSET] > 'h')
        return -1;
    root = label[NEXT_ROOT_OFFSET] - 'a';
    part = label + NEXT_PART_OFFSET + root * NEXT_PART_SIZE;
    base = be24(part);
    size = be24(part + 3);
    if (base == 0xffffffU || size == 0 || size == 0xffffffU)
        return -1;
    if (memcmp(part + NEXT_PART_TYPE, "4.3BSD", 6) != 0)
        return -1;
    secsize = be16(label + NEXT_SECSIZE_OFFSET);
    front = be16(label + NEXT_FRONT_OFFSET);
    if (secsize == 0 || (secsize % BPS) != 0)
        return -1;
    sectors = ((unsigned long long)front + base) * (secsize / BPS);
    if (sectors > 0xffffffffULL)
        return -1;
    *ufsSectors = (unsigned int)sectors;
    return 0;
}
