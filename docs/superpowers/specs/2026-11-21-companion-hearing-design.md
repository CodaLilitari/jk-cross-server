# JKDF2 companion bridge and hearing

## Intent and authorization

Andrei authorized implementation of the external companion, necessary game hooks,
auditory awareness and continued competitive work, prioritizing JKWeb. He also
authorized a future private, hardware-rendered two-minute third-person demo of
Darth Lilitari in a four-bot FF Guns match on Canyon Oasis. The supplied character
ZIP has been inspected. A separately staged cosmetic GOB excludes its optional
dance COG; all 91 overlapping stock keyframe animations retain their original
frame counts, frame rates and event markers. Actual multiplayer loading and
hardware capture remain separate runtime checks.

The inherited design is `2026-11-21-competitive-bots-design.md`. Local game AI
owns movement, aim, Force and survival on every frame. An external companion
observes, speaks through normal game chat and adjusts strategic priorities.
No language-model call, HTTP request or blocked consumer may stall a frame.

## Chosen implementation

The user subsequently selected current JKWeb and explicitly authorized privileged
engine knowledge while prohibiting altered movement, damage or other physical
game rules. This supersedes the initial preference for unchanged browser clients.
The primary implementation now ports the ordinary bot input driver into current
JKWeb `web-mp` commit `7a6f95c9a3399e59acbf019dc6b25f9981d29dff`.
Four browser players create/join a private local room using the upstream netcode-2
relay, pinned at `642afa116f392e5734bad742bfd77c65119a0c52`. Upstream packet
handling, shared starts and synchronized joins remain in charge.

The native companion is retained as a secondary path. Both transports use the
same bounded binary records: a native nonblocking datagram socket or a browser
callback/inbox. The scoped Python hub exposes HTTP and CLI control. The browser
host translates clock origins conservatively, charges transport delay against
command expiry, and never blocks the game loop on HTTP. A custom bot browser
build is explicitly allowed. This does not establish a tested public-lobby join.

Current upstream netcode 2 is incompatible with the legacy Cross Server netcode-0
gateway. The legacy gateway rejects explicit incompatible versions before
upgrade instead of admitting a misleading partial connection.

## Native ABI, version 1

One datagram is one record, at most 512 bytes. All integers and IEEE-754 floats
are explicitly little endian; C structure packing is not the wire format.
Header is Python `struct.Struct('<4sBBHIII')`, 20 bytes:

| Offset | Field |
| --- | --- |
| 0 | four bytes `JKCP` |
| 4 | uint8 version, exactly 1 |
| 5 | uint8 kind |
| 6 | uint16 payload length, exact datagram remainder |
| 8 | uint32 world epoch |
| 12 | uint32 life epoch |
| 16 | uint32 sequence, command IDs are nonzero |

Engine event kinds: STATE=1, ACK=2, CHAT=3, SOUND=4. Commands: STRATEGY=16,
SAY=17, RELEASE=18. Unrecognized versions, malformed or oversized records
have no effect. Process-specific socket ownership fences runs; a random run
identifier also fences public HTTP requests. World epoch increments on join or
world replacement, and life epoch on death/respawn identity change. Reset
strategies and sensory memory on these boundaries. Reject mismatched command
epochs before executing an action. Sequence IDs are deduplicated in a fixed
cache so a retried SAY is never spoken twice.

STRATEGY payload is `<dBBHffII` (28 bytes): absolute monotonic expiration
seconds, mode, preferred weapon, preferred resource bin, preferred range,
risk tolerance, focus network ID, focus thing GUID. Modes are autonomous=0,
pressure=1, resource=2, recover=3. Weapon 0 means automatic; 1..10 are stock
preferences still bounded by availability and rules. Resource 0 means automatic;
otherwise it is an explicitly supported stock pickup bin. Range 0 means the
local default; otherwise 0.2..12 world units. Risk is 0..1. Both focus fields
must be zero or identify a target accepted by the version-1 companion sighting
contract. That contract remains narrower than the elite controller's internal
engine knowledge; team/peace rules and stale identity checks always apply.
Supported resource bins are 0,11,12,14,15,40,60,62,63,64,65,66. Expiration
must be finite, in the future, and at most 30 seconds ahead. A
duplicate never extends its original expiration.

SAY payload is an expiration double followed by 1..110 printable ASCII bytes,
without a terminator. RELEASE payload is an expiration double. Outgoing chat
is limited to one line per bot per five seconds in both layers, rejects control
bytes and the reserved `admin` command token (case-insensitive after trimming).
SAY acknowledgment means submitted to the ordinary client chat path, not proof
of delivery to another participant.

ACK payload is `<BBH`: status, original command kind, reason. Status 0 means
applied, 1 rejected, 2 expired, 3 stale, 4 rate-limited. Reason 0 means success;
Reason codes are invalid=1, unavailable/dead=2, stale=3, reserved chat=4,
rate-limited=5 and expired=6. A source/read-only interface
cannot falsely advertise these hooks as active before a native round trip.

STATE payload is 144 bytes, emitted no faster than five times per second:

| Offset | Value |
| --- | --- |
| 0..15 | self slot, network ID, thing GUID, thing signature (four uint32) |
| 16 | game time float |
| 20..31 | own position, three floats |
| 32..43 | own health, shields, mana, three floats |
| 44..67 | weapon, kills, deaths, strategy mode (uint32); goal node (int32); flags (uint32) |
| 68..83 | currently visible target slot, network ID, GUID, signature (four uint32) |
| 84..95 | currently visible target position, three floats |
| 96 | target observation age float |
| 100 | heard category uint32 |
| 104..115 | perceived auditory anchor, three floats |
| 116,120 | auditory age and strength, two floats |
| 124..139 | own energy, power, explosives, rail ammo, four floats |
| 140 | own active Force bins 21..34 bit mask, uint32 |

Flags: dead=1, blind=2, joined=4, visible target=8, hearing cue=16,
strategy active=32. Absent target slot is UINT32_MAX and all other target
fields are zero. Absent hearing fields are zero. This compact version-1 STATE
message does not yet expose map-wide players or inventories. That is an API
limitation, not a restriction on the user-authorized elite knowledge policy.

CHAT payload is sender slot int32, sender network ID uint32, then at most
110 printable ASCII bytes. Only validated, broadcast, player-attributed chat
delivered to this bot is exported. Anonymous/system, directed and reserved
administration messages are excluded. Text is inert data, never an action.
SOUND payload is `<Ifffff`: category, perceived x/y/z, strength, uncertainty.
It names no enemy identity. Sound categories are movement=1, weapon=2,
projectile/explosion=3, ambiguous Force/arrival=4. Bounded event drops are
allowed and counted; they must not block play.

## Companion hub and client

The launcher enables the bridge explicitly with `--companion-port` (0 selects
an unused loopback port). It writes a private credential file, reports only its
path and public URL, passes socket descriptors explicitly, and closes all owned
descriptors/listeners/threads on failure or shutdown. Outgoing chat additionally
requires the explicit `--companion-chat` option. No secret goes into logs,
game chat, URLs, model observations, public receipts or native process arguments.
The runner continues to function without the companion option.

Every API request validates loopback peer, expected Host, same-origin browser
requests, and a Bearer token scoped to the one bot. Body limits, exact types,
finite numbers and known fields are enforced. One bot has one controller lease
at a time (30 seconds, renewable); other controllers receive a conflict.
Lease loss clears strategy through RELEASE, with native expiration as fallback.
Bounded event history exposes cursor gaps rather than silently pretending to
be complete. Command idempotency applies to the full payload and current run,
world, life and controller; conflicting reuse is rejected. A missing native ACK
is unconfirmed, never reported as proof an action did not execute.

Public paths are `/v1/bots/{id}/capabilities`, `/observation`, `/events`,
`/attach`, `/renew`, `/strategy`, `/say`, `/release`, and `/commands/{request_id}`.
GET reads and POST mutations use JSON. The CLI reads the private credential file
and supports these operations without requiring an OpenAI or other provider key.
The protocol documentation must show exact request/response fields and a
working observe/attach/strategy/say/release session. General model-driven
autonomous chatting is not silently activated by connecting an observer.

## Strategy effects

Pressure increases pursuit of recently observed opponents and engagement
closing while preserving route/collision/splash constraints. Resource control
raises reachable useful pickup priorities, especially the requested resource.
Recover raises health/shield/resource priorities and opens engagement spacing.
Autonomous returns to the default local policy. Range and risk modify actual
movement/goal scoring; weapon preference is a bounded bias, never a grant of
inventory. Known focus identity biases legal target selection only. Policies
must not directly write health, mana, ammo, COG targets or game positions.

## Hearing and reaction

Hook actual 3D sound requests before audio-device, camera or channel-allocation
gates, so offscreen or muted bots retain hearing. Preserve emitter provenance
through sound-class absolute-position playback. Hook ordinary muzzle sounds
only when a sound was really requested. No 2D UI/global ambience creates a
spatial enemy cue. Silent projectiles and hidden replicated positions do not
create hearing.

Callback is `jkBot_ObserveSound(SithThing *emitter, SithSector *sector,
const rdVector3 *position, const sithSound *sound, flex_t volume,
flex_t minRadius, flex_t maxRadius, int flags, int soundClass)`.
Export `jkBot_GetHearing(jkBotHearing *out)` for the bridge, containing kind,
perceived position, age, strength and uncertainty, with no hidden identity.

Use mixer distance/volume semantics and bounded traversal through sound-allowed
adjoins. Around corners, report a coarse portal/region bearing with increased
uncertainty. Keep at most 24 sensory observations, coalesce repeated/looped
cues, expire old cues, clear on lifecycle changes and invalidate reused source
identities. Hearing can turn and investigate; independently, the elite controller may use
replicated positions for pursuit and awareness. Collision and shot-safety checks
still govern firing. Loud nearby cues preempt idle scanning quickly. Distinguish urgent danger
from distant cues so a noise cannot make the bot abandon a confirmed close fight.

The hearing channel has a silent negative control, but elite target acquisition
is deliberately 360 degrees. An elite bot may route toward a silent occluded
opponent using synchronized engine position. That route destination is separate
from the combat target, so it does not cause an impossible shot through a wall. Stock ForceThrow01.WAV is ambiguous between Force Throw
and respawn; do not invent a specific respawn notification from that sample.

## Verification and demo boundary

Meaningful tests cover malformed frames, stale/dead/rejoined identities,
idempotent chat, auth scope/Host/Origin, lease loss, queue limits and actual
strategy effects. Hearing tests include rear movement vs silent controls,
closed/open acoustic paths, occluded sound with no blind fire, expiry and
audio-device-independent delivery. Rebuild every changed native translation
unit, package with provenance, and run a private real-game bridge round trip.
Qualify the current browser-hosted runtime through the pinned netcode-2 relay
and report the exact path used. Native and legacy mixed-client claims require
their own build-specific evidence.

The optional visible bot/camera hook must retain ordinary joining and inputs,
enable third-person rendering, and permit actual hardware OpenGL. A demo is
ready only after its asset loads, four clients join, GPU renderer is verified,
the controlled bot is visibly active, and a 120-second capture can be inspected.
Software rendering, a five-fps administrative view or a different stock skin
does not meet the requested character-video deliverable.

The user goal is extreme competitive strength. This increment establishes
companion control and sensory behavior; it is not a claim of top-player strength.
Supergrip is source-confirmed as a binding-dependent stock behavior; a separate
controlled measurement and explicit rules profile precede enabling the exploit.
