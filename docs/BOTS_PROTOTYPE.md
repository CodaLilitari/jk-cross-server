# Player bot prototype: recovery and qualification

This work reconstructs the prototype after its unpushed local checkout was
lost. It is not a byte-for-byte recovery. The new source, executable hashes and
test receipts describe the reconstruction. Earlier gameplay does not qualify a
new executable automatically.

## Architecture and scope

One native OpenJKDF2 client process controls one real local player. The AI
supplies ordinary control axes and button presses. Existing player COGs and
engine code handle movement, pickups, ammunition, projectiles, damage, scoring,
death and respawn. The driver does not spawn actor substitutes, assign network
identities, grant ammunition, or write player positions.

The bot executable uses engine commit
`74e4657c4f1751d09af9ad9e056acb8f41997acb` plus `native/bot-client.patch`.
It does not contain the dedicated-server patch. Its native connection joins the
existing server, which retains its ordinary retail/native/browser adapters and
player ID allocation. Human clients and the server are unchanged by this work.

Current scope is Linux x86-64, stock JK1MP, rank zero, free-for-all, with one to
four distinct personas per launcher invocation. Automatic navigation uses
existing geometry, spawns and pickups, with collision/floor checks, ordinary
door activation and jump recovery. Combat uses line of sight, reaction delay,
limited turning, weapon selection, primary fire and movement. Respawn uses
ordinary press/release input. Remote targeting uses synchronized player/death
flags, not stale remote health values.

Eight stock skin/sound identities have 128 original scripted chat lines. No LLM
or model service is used during play. Chat is limited to once per 90–150 seconds
per bot, with at least 35 seconds between bots in one invocation and staggered
initial messages. Use `--no-taunts` to disable it.

The launcher checks that its bot count is less than the configured maximum.
This is a static allowance, not a live human-slot reservation. Separate launcher
invocations do not coordinate personas or occupancy. A full server can reject
the join normally.

Navigation is a prototype, not a complete authored route set for every map.
Lifts, advanced jumps, hazards, vertical combat and every spawn/item layout have
not been exhaustively qualified. Force powers, alternate-fire tactics, teams,
CTF objectives, MotS, passwords and mods are outside the launcher scope.

## Evidence

`qa/bots-recovery-build.json` checks that the patch applies to the exact base and
produces the compiled source, verifies every packaged link input, and relinks a
byte-identical executable. `native/BOT_BUILD.json` records its artifact hashes.

The recovery binary recompiles all changed client units and all four original
dedicated-server-modified units, reusing the published unchanged application
objects and static dependencies. A complete source-build recipe is provided;
a fresh full dependency rebuild was not executed for the recovery receipt.

`tests/test_bots.py` covers launcher ownership, original-profile preservation,
join failures/timeouts, process-group cleanup and display startup.
`native/tests/test_bot_driver.c` covers concrete targeting, waypoint, input and
progress-timer regressions using controlled structs and collision stubs. These
are not live network or gameplay parity tests.

`qa/bots-recovery-native-smoke.json` records the first reconstructed executable.
Both bots joined the unchanged server, navigated the stock map, sent chat,
acquired opponents and experienced health changes. That run did not establish
kills, respawns, retail or browser qualification. Its hash differs from later
fixes; consult each receipt's exact hash.

Further live qualification is recorded separately. A running gateway or an
advertised session does not prove a client entered the world or observed bot
gameplay. A WebSocket test does not qualify WebRTC or Internet NAT traversal.

## Building and distribution

Use `bash native/build_bots.sh` for a full build on the intended host; the
dependency list in `native/README.md` applies. It installs only the separate
bot client. The engine still creates an initial graphics context, so a host
without a display needs Xvfb and software GL. Each bot is a complete engine
process with its own CPU/memory cost.

`native/bot-relink-linux-x86_64.tar.gz` supplies exact application objects,
static libraries and LGPL libsmacker source. Extract into an empty directory,
modify that source and run `python3 relink.py` to rebuild the library and relink
the bot on a matching Linux environment. The existing engine/dependency notices
under `licenses/native/` apply; original Python/persona code uses project MIT.

This is a prototype branch, not an auto-update release. Game archives, original
executables, ISOs, Wine prefixes, credentials and local player profiles are not
included in deliverables.
