# Browser transport for JK Cross Server

This adapter connects the existing JKDF2Web client to the dedicated native
engine. The engine remains responsible for map simulation, COG execution,
player creation, checksums, scoring, and game messages. The adapter handles
the browser's current lobby protocol, WebSocket fallback, WebRTC data
channels, and existing custom-content transfer protocol. It does not patch a
client engine.

## Run through the supervisor

The project supervisor owns one `NativeIPC` connection and shares it between
the browser adapter and the DirectPlay broker. Do not start two independent
IPC clients against one native engine.

```python
from pathlib import Path
from aiohttp import web
from web_gateway.ipc import NativeIPC
from web_gateway.gateway import WebGateway
from web_gateway.assets import build_asset_provider

engine = NativeIPC(port=46000, token=private_token)
assets = await build_asset_provider(
    game_root=Path("prepared-game"), episode_name="MyEpisode", mode=0,
    mod_root=None, mod_name="", download_enabled=True,
)
gateway = WebGateway(engine, client_dir=Path("runtime/browser-client"), assets=assets)
runner = web.AppRunner(gateway.create_app())
await runner.setup()
await web.TCPSite(runner, "127.0.0.1", 8090).start()
await engine.start()
```

`await engine.wait_ready(timeout=10)` waits for authenticated native readiness.
`await engine.info()` returns `(mode, entry)` where mode is 0 for JK and 1 for
MotS and entry is the engine's packed 240-byte `jkMultiEntry`. The gateway lists
only that mode. JK and MotS are separate sessions, not mixed game rules in one
match.

The root supervisor should stop the gateway before closing the shared engine
connection. Close the aiohttp runner as well.

## Install an unchanged browser client

```bash
python -m web_gateway.fetch_client --destination runtime/browser-client
```

The fetcher downloads the published `cloudflare-38` HTML, JavaScript, and WASM
from immutable repository commit
`24dc3876f32eff57c8ca98ef657698d1a30170c7`. It verifies exact sizes and SHA-256
digests against the author's published manifest. No text, bytecode, or engine
binary is edited. The user's game data remains selected locally in the browser.

Open this server's URL. The unchanged client connects to same-origin `/relay`.
The already-deployed public JKDF2Web page connects to its own lobby and does
not have a native-IP entry field that points it at this server. Self-hosting
the unchanged build is therefore the supported route. This adapter does not
advertise games to the third-party public lobby.

On a fresh browser profile, create a player first, then choose **Multiplayer →
Multiplayer Characters → New**. For JK, make a character whose rank is no higher than the server's configured
Force rank, and save it; the default JK rank is 0. For normal MotS personality
sessions, select **Mysteries of the Sith (personalities)** and a class. Those
characters use rank 7, and the server must advertise rank 7 or higher for all
clients to accept them. Ranked Jedi MotS sessions can use a lower rank limit. Next choose **Join Game → OpenJKDF2 Relay**, select the advertised game,
and select that multiplayer character. A newly created player profile alone
does not create a multiplayer character; the unchanged game otherwise reports
that no valid characters meet the game's restrictions.

The folder picker needs the installed game files with the normal names. For
JK this includes `episode/JK1.gob`, `JK1CTF.gob`, `JK1MP.gob`,
`resource/Res1hi.gob`, and `Res2.gob`. The MotS picker lists the corresponding
`.goo` files if anything is missing. Some automated or minimal native server
installations use symlinks or rename `Res1hi.gob` to `res1.gob`; those layouts
may work for the native engine but do not satisfy the unchanged browser's
folder checks. Select a complete installation with regular files. The game
data is read locally by the page.

## Networking

The browser offers two reliable, ordered, negotiated RTC data channels:
`jk` with ID 0 and `jk-map` with ID 1. This adapter answers that offer as host
ID 1. WebSocket fallback remains available if ICE cannot connect. Native GNS,
retail DirectPlay, and browser player IDs are allocated by the common engine
and DirectPlay broker. The browser accepts canonical IDs in gameplay, but its
transport roster is a fixed synthetic 1..32. The adapter therefore rewrites
only DSS message 41 (the transport enumeration join gate) to name its single
transport peer, host ID 1. It preserves the message's reliability/sequence
header and every game-state message, including the real gameplay roster.

For HTTPS deployment, terminate TLS on the gateway origin and forward
WebSocket upgrades for `/relay`. Configure `web_ice_servers` in the saved
configuration or the panel's advanced STUN/TURN field if NAT traversal is needed.
It is an array of objects with `urls` and optional `username` and `credential`;
the supervisor passes it to the gateway's `ice_servers` option. No public
STUN or TURN service is contacted by default. RTC uses dynamically allocated
UDP sockets; TURN or suitable routing is needed behind restrictive NAT.

The upstream browser throttles certain player-position packets to one every
200 ms while using WebSocket fallback. A direct RTC connection avoids that
client-side throttle. This server cannot remove the throttle without changing
the client. Fallback is compatible but is not a claim of equal responsiveness.

The server verifies same-origin browser connections by default. Additional
origins require explicit `allowed_origins`. The native IPC endpoint stays on
loopback and requires a secret token. Game packets are stamped with the
sender's allocated seat ID before forwarding to the engine.

## Missing maps and active mods

The supervisor prepares the selected episode and configured mod folder before
starting the engine. **Send missing custom maps and mods to browser players**
controls delivery (`web_asset_downloads`, enabled by default). The control
panel shows the prepared fingerprints, transfer sizes, original-content
reference count, and session transfer counters. Changing content or the policy
requires stopping and restarting the session.

The gateway implements the published client's `JKMT` version 1 INFO and CHUNK
exchange for a custom `.gob` episode in JK or `.goo` episode in MotS. It sends
the selected content's SHA-256 and existing retail-reference metadata. A
browser missing that episode requests the stream, reconstructs any referenced
original content from its own installation, verifies the complete hash, and
installs it through its existing join flow. Named stock episodes and
retail-only archives are not distributed. Give a customized stock episode a
distinct archive name and select that episode on the host; the unchanged
browser skips downloads for the original stock episode names.

An active mod is packed deterministically using the published client's file
selection, path ordering, GOB layout, and SHA-256 rules. The gateway appends
the existing `JKMD` version 2 fingerprint/name tail to the browser session
listing and welcome. The native session structure remains unchanged. The
browser can use matching local or cached content, or download the mod using
kind 1 of the same transfer protocol. Its existing mod-switch flow restarts
the game. Follow its prompt to return to Multiplayer and rejoin the session
after that restart; the missing episode can then download during rejoin.
Browser storage and the ordinary client's prompts remain in control of
installation and restart.

| Content | Supported transfer behavior |
| --- | --- |
| Custom JK/MotS episode archive | Up to 100 MiB; only the selected episode is offered |
| Selected mod folder | Up to 250 MiB of file payload and 10,000 files for download; larger local-only mods can still be fingerprinted within the preparation limits of 1 GiB and 50,000 files |
| Original game content | Referenced by content hash where possible; players provide their own matching original files |
| `JKMRemasteredAssets.goo` | Advertised by its special-pack fingerprint; the matching pack must already exist locally and is never transferred |
| Retail and native clients | Continue to install matching custom content through their normal local workflow |

The selected episode archive and mod folder are the supported locations for
custom content. Additional engine-loaded resource overrides are rejected
during preparation, with guidance to put them in the configured mod folder.
The MotS Remastered pack belongs in its supported resource location, outside
the selected mod. This avoids advertising a mod that omits effective host
resources.

Disabling downloads prevents all asset chunks. Custom-map metadata remains
available because the unchanged browser checks that metadata before accepting
an already installed matching archive. The mod fingerprint also remains in
the session listing. A browser missing a custom map will follow its existing
download timeout when chunks are disabled; the server cannot add a different
client prompt without changing that client.

Asset traffic uses the existing WebSocket or negotiated `jk-map` channel.
Each peer has a separate bounded asset queue; requests select only immutable
prepared hashes, never filesystem paths. Responses obey the published 16 KiB
RTC / 48 KiB WebSocket chunk sizes, apply backpressure, and are cancelled when
the peer leaves. Asset packets do not enter the game simulation. The public
health response and local administration status expose aggregate transfer
counters, not host filesystem paths.

## Verification

Run from the project root:

```bash
python -m unittest web_gateway.test_gateway web_gateway.test_admin web_gateway.test_assets -v
```

The transport integration tests start actual local IPC, HTTP, WebSocket, and
WebRTC sockets. They check session bytes, concurrent allocations, DirectPlay
ID pools, game-mode filtering, rejection of the wrong mode, unchanged payload
delivery, sender stamping, seat recovery, origin enforcement, and negotiated
RTC channels, plus the browser's transport-roster join gate and a MotS-mode
descriptor/join fixture. The engine fixture only echoes payloads. Those checks establish
transport behavior and do not establish in-game retail/browser parity.

The additional optional test below executes the exact transport function
from the hash-verified published JavaScript bundle under Node's native
WebSocket API. It verifies the published lobby, seat, welcome, sender, and
receiver code. It does not start the full game or a rendered browser.

```bash
JKDF2WEB_CLIENT_DIR=runtime/browser-client python -m unittest web_gateway.test_published_client web_gateway.test_assets -v
```

The asset tests independently reconstruct maps and deterministic mod packs,
check original-content references and disabled-download behavior, and transfer
content over actual WebSocket and WebRTC channels while gameplay remains
separate. With `JKDF2WEB_CLIENT_DIR` set, the published-JavaScript asset oracle
also runs the exact hash-verified client download and reconstruction functions
under Node. That oracle is separate from the rendered browser acceptance
receipts described in `docs/QUALIFICATION.md`.

`qa/published-wasm-jk-full-game.json` records a separate full-game test using
the hash-verified published HTML/JS/WASM in Chromium. The real engine confirmed
the browser player joined `JK1MP/m2.jkl`, and received that player's chat.
The client rendered the map and responded to movement input. This full-game
run used the unchanged WebSocket fallback; the private test network did not
give Chromium local ICE candidates. The RTC socket tests above remain
transport tests, and are not described as a full-game WebRTC qualification.

`qa/published-wasm-jk-three-client.json` adds the simultaneous original retail,
unmodified native, and published browser JK run. The engine reported three
fully joined humans. Read-only browser memory snapshots show all three active
players and a native player moving; the browser received both native and retail
chat. Separate original-retail snapshots show the browser player moving. This
is a functional local smoke test, not a combat, endurance, or public-Internet
qualification.

`qa/published-wasm-mots-three-client.json` records the corresponding stock
`JKM_MP/mdm02_freezer.jkl` MotS session with all three client families and
rank 7. It includes browser/native/retail movement observations, native and
retail chat received by the browser, and browser chat received by native and
the original MotS client's retained HUD buffer.
Read-only entity observations identified six native pistol projectile GUIDs
in the browser and five browser projectile GUIDs in native. The browser and
original retail also observed a native environmental death, the resulting
death/suicide/score values, and the native player's respawn at health 100.
The receipt distinguishes these checks from player-to-player damage, which
was not demonstrated across the map's obstructing geometry. Full-game MotS
also used the published WebSocket fallback. See the receipt's explicit
limits, including the original MotS software renderer's slow test performance.

## Primary source pins

- [Browser engine used by the tested published build, commit a7c0211](https://github.com/tristamus/OpenJKDF2/tree/a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c).
- [WSRelay protocol and client implementation](https://github.com/tristamus/OpenJKDF2/blob/a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c/src/Platform/Networking/WSRelay/stdComm_WSRelay.c).
- [Packed session structure](https://github.com/tristamus/OpenJKDF2/blob/a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c/src/types.h).
- [Custom map checking and fallback](https://github.com/tristamus/OpenJKDF2/blob/a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c/packaging/wasm/maps.js).
- [Mod fingerprinting, packing and transfer](https://github.com/tristamus/OpenJKDF2/blob/a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c/packaging/wasm/mods.js).
- [Original relay, commit 959bf95](https://github.com/tristamus/jkdf2mp-bb-server/tree/959bf95e155e838addfb0d2c78dc07c90e8b2255).
- [Pinned client build and manifest](https://github.com/tristamus/jkdf2mp-bb-server/tree/24dc3876f32eff57c8ca98ef657698d1a30170c7/cloudflare-38).
- [aiortc API](https://aiortc.readthedocs.io/en/latest/api.html).

Original OpenJKDF2 and JKDF2Web contributors retain their credits and existing
licenses. This directory's adapter code is new project code. The third-party
client is fetched separately; its existing license and notices still apply.
