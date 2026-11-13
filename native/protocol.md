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
`bIsTeams`. Set `bIsDedicated` to true before startup. `maxPlayers` includes the
dedicated host slot; humans and bots share the remaining slots. Use 100 ms tick intervals
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
Use at most 15 configured slots, including the host, for this mixed configuration. The original retail
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
| 9 | ADMIN_REQUEST: src=actor transport ID, dst=request ID; payload uint32 generation, uint32 operation, then up to 127 printable ASCII bytes | 110, actor/request echoed; payload uint32 generation, uint32 status (0 success), then bounded ASCII summary |
| 10 | REPLACE_POOL_ID: src=retired surrogate ID, dst=nonzero request correlation; payload uint32 fresh DirectPlay ID | 112, old ID/correlation echoed; payload uint32 accepted new ID |

Errors use type 199, src=request type, dst=error code, payload UTF-8 reason.
Without a DirectPlay pool, automatic external IDs begin at 65536 and native
GNS IDs begin at 2. New connections receive previously unused identities within
that transport session. ID 1 is always the
engine host; a DirectPlay gateway must acquire the server-player ID 1 or
translate the host identity consistently.

### Player identities across reconnects

An ordinary client remembers recent reliable messages by sender ID and sequence
number. Reusing a departed sender's ID for a restarted client can cause new
messages to be acknowledged as duplicates without reaching the game handler.
Player slots may be reused; transport identities must identify a new connection.

The engine immediately retires a surrogate identity exposed to game traffic
when its actual native or external connection ends, including an administrative
kick. Type 113 is an
unsolicited retirement event with `src=old ID`, zero `dst`, and no payload.
The broker forwards it only to the adapter that registered the DirectPlay pool.
The old identity remains unavailable while replacement is pending.

There is one native discovery exception. A pool-backed native connection starts
with a pristine reservation so the stock server browser can read its initial
descriptor and disconnect without spending a player identity on every refresh.
The first incoming payload commits that identity before validation or forwarding;
any ordinary outbound Sith packet commits it before sending. Only a reservation
that has carried neither inbound nor outbound game traffic may return to the
unused pool on close, without event 113 or a queued player-loss event. Old
connection handles cannot affect a later reservation. Used or uncertain
connections are retired normally. Browser/retail registrations and native
connections without a pool are committed immediately.

The adapter uses ordinary DirectPlay `DestroyPlayer` and `CreatePlayer` calls
to obtain a fresh ID for that reserved pool entry, then submits request 10.
The engine accepts replacement only for an inactive, retired pool entry and
a previously unused valid ID. Duplicate matching replacements and retirement
notifications are idempotent. A conflicting acknowledgement or failed replacement
ends the adapter session instead of recycling an old identity. Other slots are
not rewritten.

The adapter serializes a bounded retirement queue while continuing normal game,
metadata, and departure processing. The broker preserves retirement notices
that arrive alongside a registration or replacement acknowledgement. Delayed
packets and DirectPlay notifications for retired identities cannot recreate a
retail player or remove a replacement player.

Identity history survives ordinary map changes. Brief browser connection
resumptions that retain the same game connection also retain its ID. A new
transport session clears history. The engine and broker bound the session
history to 65,536 canonical identities, including the canonical host; the
adapter independently tracks its physical DirectPlay host and issued IDs with
the same limit. Exhaustion requires a session restart rather than ID reuse.

Deploy the matching engine, manager, and DirectPlay adapter together. This
protocol extension changes server-side membership management; human client
executables and Sith packet formats remain unchanged.

### Private administrator events and actions

Type 9 exists only on the dedicated engine's authenticated supervisor socket.
The public adapter broker rejects it. Operations are 1 (private chat reply),
2 (private current player list), 3 (kick by `#slot` or exact unambiguous name),
and 4 (ordinary next authored level). List/next-level take no argument. There
is no arbitrary console or script operation. The engine rechecks a fully joined
actor's transport identity and nonzero connection generation before execution.

Type 109 is a verified host-directed admin chat event: src is the actual
transport ID, dst its generation, and payload is at most 127 printable ASCII
characters. It is emitted after ordinary message deduplication. A player name
or speaker field inside chat does not identify the actor. Type 111, with zero
src/dst and no payload, clears manager grants when the map or IPC context resets.
Generations change on reconnect/reset. A bounded recent-request cache also
rejects accidental duplicate supervisor actions.

The manager verifies persistent credentials outside the game and authorizes
typed requests; the engine executes normal host actions. A kick sends the
ordinary quit packet and retires transport membership. An unsolicited 104
event instructs the relevant adapter to retire its corresponding seat. Late
packets from that retired seat do not affect other players in the shared
DirectPlay adapter. A level change uses stock end-level/tally messages and
requires episode progression. Updated INFO descriptors keep browser and
DirectPlay discovery synchronized with the actual map.

See [Chat administration](../docs/CHAT_ADMIN.md) for issuance, the inert key-file
container, offline proof workflow, and the limits of a human-pasted challenge
on unchanged clients. No credential is loaded into world COG bytecode.

### Sith packet representation

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
