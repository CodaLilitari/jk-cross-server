# Player bot prototype: recovery and qualification

> Historical report for the recovered prototype and the exact hashes below.
> Current controls, Force support, stock-map navigation and CTF work are described
> in [BOTS_BEHAVIOR.md](BOTS_BEHAVIOR.md). A newer build does not inherit the
> runtime qualifications recorded here.

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
player ID allocation. Human clients and the dedicated engine are unchanged.
Two separate changes to the existing DirectPlay adapter are described below:
a JK retail-scoreboard correction and verified handling of obsolete sends
during JK retail departure. Both arose during compatibility testing.

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

The 14 tests in `tests/test_bots.py` cover launcher ownership, original-profile
preservation, join failures/timeouts, process-group cleanup and display startup.
The five strict compiled regression groups in `native/tests/test_bot_driver.c`
cover remote-player eligibility after respawn, waypoint retention, input axes
and press edges, horizontal progress, and low-ceiling clearance. These use
controlled structs and collision stubs; live gameplay has separate receipts.

The low-ceiling regression reproduces the dimensions of stock map sector 110.
The previous graph elevated its body sweep and floor probes above a passage
that fits a normal player. The corrected graph tests the actual body center,
checks both endpoints before a raised step fallback, and keeps support rays
inside the passage. The regression fails against the previous source and
passes against the corrected source. See `qa/bots-low-ceiling-regression.json`.

`qa/bots-recovery-native-smoke.json` records the first reconstructed executable.
Both bots joined the unchanged server, navigated the stock map, sent chat,
acquired opponents and experienced health changes. That run did not establish
kills, respawns, retail or browser qualification. Its hash differs from later
fixes; consult each receipt's exact hash.

The subsequent `f545c0b3...` executable has stronger live evidence:

| Receipt | Established behavior |
|---|---|
| `qa/bots-recovery-live-gameplay.json` | Four real player bots; ordinary projectiles, ammunition consumption and gains, weapon changes, scores, and 12 observed death/respawn cycles. |
| `qa/bots-recovery-respawn-targeting.json` | Trooper fires real projectiles at a respawned Jan whose remote health remains zero; Jan's own simultaneous read shows positive health and a live player. |
| `qa/bots-recovery-native-human.json` | An unchanged native human client sees the four stock skins, movement, projectiles and chat, dies to a bot, and respawns through normal input. |
| `qa/bots-recovery-jkweb.json` | The unchanged published browser client shares the match, takes damage, dies, respawns through Space, receives themed chat, and is killed again after respawn. |

The native and browser humans were present together with four bots. Their
rendered UI and read-only observations corroborate the bot-side samples. Reads
are bounded and non-atomic; no observer writes game state. Remote health is not
treated as authoritative. Projectile samples are lower bounds, and position
changes can include normal respawns.

### Final packaged executable

The packaged executable is
`8af6a4e7b1feedc23cff230e8894c73edc1b52acc019d85bc1c6a35493b44b4e`.
Its mixed gameplay test used the existing retail, native and browser adapters
together, before the two adapter corrections described below. Four bots and
three unchanged human clients enter the same stock
world: original retail JK 1.00, native OpenJKDF2 at the pinned base, and the
published JKWeb build. Real DirectPlay identities come from the existing
adapter pool before joins; the bot implementation does not allocate them.

Jan naturally respawns in sector 110 and walks into sector 63 with the same
death count and full health. The two observer samples are about half a second
apart. Subsequent movement traverses the low passages again. This gives live
evidence for the clearance correction as well as its compiled regression.

| Receipt | Final-build coverage |
|---|---|
| `qa/bots-final-live-gameplay.json` | Bot-side movement, combat, natural respawn, low-tunnel traversal and the combined seven-player roster. |
| `qa/bots-final-native-retail.json` | Independent original retail and native client observations, with ordinary UI actions and exact executable hashes. |
| `qa/bots-final-jkweb.json` | Unchanged browser joins the mixed session, sees the combined roster, dies to Kyle, respawns normally and receives themed chat. |
| `qa/bots-final-human-fire.json` | Fifteen distinct normal native-human projectile identities propagate into the bot clients; damage from those shots is not established. |

The final main observer captured 1,884 samples over about four minutes with no
read errors, including 10 complete bot death/respawn cycles. The separate
30-second human-firing check has observation gaps documented in its receipt.
Human-to-bot damage attribution remains unverified: the observed bot health
losses overlap bot-versus-bot combat, and the human recorded no kill. Normal
human projectile propagation is established without claiming a confirmed hit.

The final original-retail leave screen exposed a separate baseline adapter
defect: deaths appear in the kills column. Original JK's roster begins its
statistics with an unsigned-byte team field, followed by signed-16 kills,
deaths, suicides and score; the existing adapter treated the byte as kills.
The bot executable supplies normal native statistics. Its baseline retail
receipt therefore qualifies gameplay while explicitly failing retail
scoreboard parity. The accompanying narrow adapter correction translates the
team byte and all four signed fields in their original JK order. It preserves
16-bit kill counts and is gated to JK; the existing MotS conversion remains
unchanged pending verification against an original MotS executable. Independent
wire fixtures reproduce the observed failure and fail against the previous
converter. The source audit and live retest are recorded separately from the
frozen bot executable in `qa/retail-jk-score-layout-audit.json` and
`qa/retail-jk-scoreboard-regression.json`.

The retail test uses the original executable and original DirectPlay files in
an isolated Wine runtime. Its launcher/provider paths were repaired to use
the qualified original DLLs after Wine initialization replaced the system32
copies. These are test-runtime settings. The dedicated server executable,
native and browser protocols, and browser bundle remain unchanged. The original
mixed gameplay receipts retain the baseline gateway hash and its scoreboard
failure. The score-only gateway retest establishes matching statistics, but
also records a later adapter failure during ordinary retail departure.

The packaged gateway additionally checks JK sends that fail with
`E_INVALIDARG` or `DPERR_INVALIDPLAYER`. It discards a frame only after fresh
DirectPlay queries establish an owned local sender and a complete player list
in which the destination is absent, or a broadcast has no remote recipients.
Present destinations, live-remote broadcasts, invalid senders, incomplete
queries and other errors still fail. Packets are neither changed nor retried;
MotS retains its previous handling. The 15 compiled policy assertions and
independent source review are recorded with the separate live departure test
in `qa/retail-jk-departure-regression.json`.

With the packaged gateway (`73158f1d...`), the original retail client completed
join, leave, rejoin and leave while the same dedicated engine, gateway and four
bot processes continued running. No `send_departure_check` event occurred in
that test. It therefore establishes ordinary departure/rejoin continuity for
that bounded run, but does not exercise the new failure-reconciliation branch
against the real provider or establish the cause of the earlier failure. That
branch's decision boundaries are covered by the compiled policy tests.

Each receipt names its exact binary hash; predecessor results are retained as
predecessor evidence. The scope is one stock map and local transport. Physical
Windows installations, other retail patches, every OpenJKDF2 version, WebRTC,
Internet NAT traversal and MotS are not established by these tests. A running
gateway or an advertised session alone is insufficient.

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
