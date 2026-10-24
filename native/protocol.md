# Dedicated-server transport gateway

Server-only integration based on `codalilitari/OpenJKDF2-MotS-Fixes` commit
`74e4657c4f1751d09af9ad9e056acb8f41997acb`. The original engine and contributor
licenses continue to apply. The added bridge is original code for this project.

## Running

Start the compiled engine in a separate writable instance directory containing
`resource/`, `episode/`, and `registry.json`. The dedicated path requires
`resource/jk_.cd` and does not select a global interactive install. Original
game assets are not distributed with this source.

```
openjkdf2 -dedicatedServer -headless -episode JK1MP -map m2.jkl
```

For Mysteries of the Sith, add `-motsCompat` and give the installed MotS episode
and level names explicitly. Dedicated mode still briefly creates an SDL/OpenGL
bootstrap context, so Linux servers without a display need Xvfb/Mesa.

The existing registry options are plain JSON: `gameName`, `serverPassword`,
`portNum`, `maxPlayers`, `maxRank`, `tickRate`, `scoreLimit`, `timeLimit`,
`bIsDedicated`, `bUseScoreLimit`, `bUseTimeLimit`, `bIsSingleLevel`, and
`bIsTeams`. Set `bIsDedicated` to true before startup. `maxPlayers` is the human
limit; the engine reserves one additional host slot. Use 100 ms tick intervals
for the original retail default (the retail interface supports 100–300 ms).

## Transports

Native OpenJKDF2 retains its Valve GameNetworkingSockets endpoint, normally
UDP 27020. The bridge accepts one authenticated local supervisor over TCP.
That supervisor provides the browser relay and original DirectPlay endpoint.
No engine changes are installed on clients.

Enable the local bridge with `OPENJKDF2_GATEWAY_PORT` and
`OPENJKDF2_GATEWAY_TOKEN` (16–256 UTF-8 bytes). The listener binds only
127.0.0.1. The token must be supplied through the launch environment and must
not be logged. Public authentication, TLS, and process supervision belong to
the outer application.

Set `OPENJKDF2_REQUIRE_DP_POOL=1` for a retail-enabled instance. The DirectPlay
gateway creates real surrogate players and supplies their IDs before native
or browser clients may join. Browser and GNS canonical IDs then equal real
DirectPlay IDs. This preserves IDs embedded inside game packets and allows
unmodified retail clients to address those peers. A pool of at most 15 IDs,
15 real retail players and a host fit within DirectPlay's 32 physical slots.
Use at most 15 human slots for this mixed configuration. The original retail
session browser may count unused surrogate transport slots; the control panel
should display the engine's actual player count.

## Local protocol version 1

Every frame is a little-endian uint32 body length, followed by uint32 `type`,
`src`, `dst`, then payload. Body lengths must be 12–65536. Socket writes may
split or combine frames. Game payloads are at most 2052 bytes. The first frame
must be HELLO within five seconds. A disconnected supervisor removes its
external peers; the engine does not continue accepting new GNS peers while a
required retail gateway is disconnected.

| Request | Meaning | Reply |
|---|---|---|
| 1 | HELLO: payload is the exact token | 101, payload uint32 version=1 |
| 2 | INFO | 102, payload uint32 mode (0 JK, 1 MotS), then exact 240-byte `jkMultiEntry` |
| 3 | ADD_PEER: src=desired ID or 0 for automatic; dst=request correlation | 103, src=canonical ID, dst echoed, payload uint32 status=0 |
| 4 | REMOVE_PEER: src=canonical ID | 104, src and dst echoed |
| 5 | DATA: src=registered peer, dst=recipient (0 or 1 means engine host) | Game output uses type 105 with canonical src/dst |
| 7 | PING: payload up to 256 bytes | 107, payload echoed |
| 8 | SET_ID_POOL: payload 1–15 unique uint32 DirectPlay IDs; before clients join | 108, payload uint32 ID count |

Errors use type 199, src=request type, dst=error code, payload UTF-8 reason.
Without a DirectPlay pool, automatic external IDs begin at 65536 and native
GNS IDs retain their ordinary small-number allocation. ID 1 is always the
engine host; a DirectPlay gateway must acquire the server-player ID 1 or
translate the host identity consistently.

The Sith packet header is uint16 message type plus uint16 reliability sequence;
it is not a uint32 message type. Player enumeration is message 41, with body
uint8 count followed by count uint32 IDs. Unmodified GNS clients keep a
synthetic native player list, so the server supplies a host-only enumeration
gate to those clients. Their subsequent game-state packets retain every
canonical peer ID. A browser gateway must supply an equivalent valid
enumeration or keep its roster complete.

The inspected native 0.9.9 source has an asymmetric MotS absolute CreateThing
packet: its sender writes a 32-bit sector, but its receiver consumes 16 bits.
The server therefore narrows this field only when sending to a native GNS
client, preserving the header, reliability sequence, coordinates and object
ID. Retail/browser packets retain the 32-bit representation. Set the server
environment variable `OPENJKDF2_GNS_MOTS_SECTOR_BITS=32` only if every native
client in that session has the corrected 32-bit reader. The native transport
does not advertise the client commit, so the server cannot automatically
distinguish both reader versions on a single GNS endpoint.

## Changes beyond transport

* Dedicated startup remains in its isolated working directory.
* Redirected headless stdin is supported without repeated prompt output,
  uninitialized terminal state, or overrunning the command buffer.
* State-update light is serialized as float32, matching its existing reader.
* MotS CreateThing's sector is read as int32, matching its existing sender.
  The matching corrections are also present in the inspected JKDF2Web fork.

## Validation boundaries

`src/Tests/gateway_bridge_test.cpp` exercises fragmented authentication,
coalesced messages, replies, frame limits, wrong-token rejection and disconnect
callbacks with AddressSanitizer and UndefinedBehaviorSanitizer. This is
transport validation; it does not by itself prove a retail, browser or native
client has completed a game join. Runtime and multi-client observations must
be recorded separately, with the exact engine and asset identities.
