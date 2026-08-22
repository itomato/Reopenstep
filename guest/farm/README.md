# Reopenstep native build farm

Build this directory on the MS4 builder with `make ARCHS=i386`. Run the
controller on the NetInfo/NFS master and one worker per cloned builder node.

The controller registers the Distributed Objects name
`ReopenstepFarmController`. Workers advertise all four cross-build
architectures, heartbeat every five seconds, and request one architecture-slice
job at a time. The controller persists its queue atomically, marks a worker
offline after 45 seconds, and retries an infrastructure failure once.

The farm is intended only for a routed-off trusted build LAN. Put its machines
in the `reopenstep-builders` NetInfo netgroup, mount the buildmaster export at
`/Net/buildmaster/ReopenstepFarm`, and run all three programs as the dedicated
`build` user.

Build specifications are OpenStep property lists. Fields are `snapshot`,
`project`, `target`, `profile`, `architectures`, `toolchain_sha256`, and
`output`. The controller accepts conservative identifier characters and the
worker invokes `/usr/bin/make` with an argument array, never a shell command.
