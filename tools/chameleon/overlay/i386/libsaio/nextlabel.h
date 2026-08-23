#ifndef __LIBSAIO_NEXTLABEL_H
#define __LIBSAIO_NEXTLABEL_H

/* Decode a NeXT dlV3 label copy and return its root UFS offset in 512-byte sectors. */
int NeXTLabelUFSOffset(const unsigned char *label, unsigned int labelBytes,
                       unsigned int labelSector, unsigned int *ufsSectors);

#endif
