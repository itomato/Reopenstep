ARCHS = i386
CC = cc
CFLAGS = -O2 -Wall $(foreach arch,$(ARCHS),-arch $(arch))
FRAMEWORKS = -framework Foundation

all: RSFarmController RSFarmWorker rsfarm

RSFarmController: RSFarmController.m RSFarmProtocol.h
	$(CC) $(CFLAGS) -o $@ RSFarmController.m $(FRAMEWORKS)

RSFarmWorker: RSFarmWorker.m RSFarmProtocol.h
	$(CC) $(CFLAGS) -o $@ RSFarmWorker.m $(FRAMEWORKS)

rsfarm: rsfarm.m RSFarmProtocol.h
	$(CC) $(CFLAGS) -o $@ rsfarm.m $(FRAMEWORKS)

clean:
	rm -f RSFarmController RSFarmWorker rsfarm
