# Private live spectator protocol (version 1)

The dedicated host and its authenticated manager use this interface. It creates
no game player and adds no packet to a client game transport. All integers and
float32 values are little endian. Requests use private IPC type **11**, source
zero and nonzero destination correlation; replies use **114**, source zero and
the same correlation.

| Operation | Struct format | Fields |
|---|---|---|
| Status | `<II` (8 bytes) | version=1, operation=0 |
| Configure | `<7I` (28 bytes) | version=1, operation=1, expected world epoch, expected control epoch, mode, target peer, target generation |
| Input | `<5I5f` (40 bytes) | version=1, operation=2, expected world epoch, expected control epoch, sequence, forward, right, up, yaw delta, pitch delta |

Modes: 0=off, 1=free, 2=follow. Off/free require zero target fields. Follow
requires a fully joined nonhost peer and current connection generation.
Configure requires current epochs, increments control epoch, and clears input.
World open/close increments both epochs. Input requires free mode, current
epochs, increasing nonzero sequence, finite axes in [-1,1], and finite look
deltas in [-pi,pi] radians. Held motion expires after 250 ms without fresh input.

The reply header is `<16I6fi` (92 bytes), in this exact order:

1. version, result, operation, capabilities
2. mode, state flags, world epoch, control epoch
3. target peer, target generation, width, height
4. frame age in milliseconds, reason, roster count, frame sequence
5. x, y, z, yaw, pitch, roll (six float32 values; angles in radians)
6. sector index (signed int32; -1 when unavailable/outside the world)

Roster entries are `<III64s` (76 bytes): canonical peer, connection generation,
player slot, zero-padded UTF-16LE name (32 code units). At most 31 fully joined
nonhost players are returned, excluding provisional transports/reservations.
Only status replies carry roster entries. Configure/input replies have a zero
roster count and exactly the 92-byte header; the manager retains its query roster.

Result: 0=ok, 1=malformed, 2=stale epoch, 3=target unavailable, 4=unavailable,
5=wrong mode. Capability bits: 1=context, 2=frame channel, 4=free, 8=follow.
State bits: 1=world ready, 2=frame ready, 4=frame pending, 8=outside world,
16=target lost, 32=active, 64=render error.
Reason: 0=none, 1=unavailable, 2=world not ready, 3=target lost,
4=outside world, 5=channel closed, 6=render error, 7=disabled.
Frame age is UINT32_MAX until a current-epoch frame is published. Departure
returns follow to free at the last pose and increments control epoch. Respawn
under the same identity is followed through a fresh roster lookup.
Frame age measures elapsed time since capture, including time spent waiting for
frame-channel capacity; completion of a delayed send does not reset its age.

## Independent frame channel

The manager inherits an AF_UNIX stream socket through
`OPENJKDF2_SPECTATOR_FD`. Missing/invalid FD keeps the original headless path.
Only an explicit dedicated/headless launch enables the capability; it does not
modify the isolated capture authorization path. The observer initially is off.

Every frame has a 36-byte `<4s8I` header: `JKSV`, version=1, width, height,
world epoch, control epoch, frame sequence, payload bytes, flags=0. Payload is
tightly packed top-down RGBA8, exactly width*height*4 bytes. Maximum dimensions
are 640x360 and maximum rate is 5 fps. The sender is nonblocking, retains one
pending complete frame, finishes it before another and drops frames under
backpressure. Image bytes never enter the 64 KiB game/control IPC. The manager
keeps only the latest valid frame and serves it through authenticated routes.
Frame sequence is uint32 increasing within the process. Every frame carries its
epochs, allowing stale images to be discarded. Supervisor disconnect disables
the observer and clears input. The manager additionally disables after its
viewer lease expires; status/input requests do not renew that viewer lease.

## Simulation isolation

The private camera has no thing, player slot, inventory, health or collision.
Host actor and world focus/local-player pointers remain unchanged. Observer
rendering suppresses sighting COGs, AI wakeups, gameplay-visible flags/stamps,
host palette writes, explosion consumption and the stateful extra weapon hook.
Shared animation caches and render stamps are restored before simulation
resumes. Extra weapon/saber cosmetic meshes are omitted in the initial view.
Game resources, templates, checksums and ordinary client packets are unchanged.
