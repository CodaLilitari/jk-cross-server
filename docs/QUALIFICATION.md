# Qualification record

This report accompanies a development build of JK Cross Server. It distinguishes actual game-client behavior from transport fixtures and records the particular clients used. A compatibility result for one pinned build does not automatically qualify every release or mod.

## Host spectator refresh — 2026-10-28

This section records fresh verification of the recovered development checkout.
The dedicated core was built from source in a new build directory, including
all 206 application translation units and enabled pinned bundled dependencies.
No application or bundled dependency objects were reused from the lost
environment. The current core SHA-256 is
`af0d99d232da3d77a3bbd87dde917bd824775815df9ec420411452701f29e572`.
The [native build receipt](../qa/native-observer-build.json) records the source,
dependency, patch and artifact identities. The
[manager recovery receipt](../qa/host-spectator-manager-recovery.json)
distinguishes the exact recovered observer controller from reconstructed
manager and test sources; the results below were rerun against this checkout.

### Fresh automated and packaging checks

| Check | Observed result and scope | Evidence |
| --- | --- | --- |
| Manager and feature Python discovery | 159 passed, including current-descriptor readiness, separate core/Wine display handling, observer authentication, bounded frames, lifecycle cleanup and the lost-enable-reply lease regression. | [Manager and transport test receipt](../qa/host-spectator-tests.json) |
| Web gateway discovery | 27 passed with both unchanged published-JavaScript transport and asset-reconstruction oracles enabled; no skips. These oracles exercise client functions without starting the full game. | [Manager and transport test receipt](../qa/host-spectator-tests.json) |
| Panel and spectator JavaScript | 16 named cases passed. The recorded command uses `--test-isolation=none` so the result includes each named case. | [Manager and transport test receipt](../qa/host-spectator-tests.json) |
| Existing DirectPlay C programs | All 3 programs passed: protocol layouts, departure policy and surrogate-pool lifecycle. | [Manager and transport test receipt](../qa/host-spectator-tests.json) |
| Native server, bot and observer fixtures | All 8 existing native runners and 12 observer behavior groups passed. These use actual patched translation units, controlled fixtures and isolated local socketpairs. | [Native regressions](../qa/native-observer-regressions.json) |
| Native packaging | 2 focused packager tests passed; all 218 archived object/library inputs were verified. Supplied-object relinking reproduced the packaged core byte for byte. | [Packaging verification](../qa/native-observer-packaging.json) |

The final recorded suites have no failures, errors or skips. Automated fixtures
and packaging checks are distinct from the live game observations below.
The [final verification receipt](../qa/host-spectator-final-verification.json)
records the later complete rerun, its 14 commands and 69 source/test hashes;
the recorded inputs remained unchanged during that run.

The [real display startup receipt](../qa/host-spectator-display-live.json)
records two additional isolated starts of the final packaged core on stock JK:
`auto` selected offscreen with ambient display variables absent, and explicit
`xvfb` started its own Xvfb process. Each started with the view closed, reported
a ready zero-player session, and produced a nonconstant 640 × 360 RGBA frame
after opening the free camera. Closing each manager cleared its session,
connection and tasks, with no owned process left running. The Xvfb wrapper's
exited engine/Xvfb remained as zombie entries awaiting PID 1's reaper; this
environment-specific cleanup observation is retained in the receipt. These
checks used no game clients, bots, retail bridge or browser HTTP server.

### Actual JK session and host camera

The fresh local session used stock `JK1MP/m2.jkl`, the unchanged native client,
the unchanged published JKWeb client, and two actual packaged player bots in
the same running match while the host observer was active. The native client
joined through its normal menus, displayed the world/HUD, moved while followed,
and departed through the ordinary in-game Abort/Yes flow. Its original-source
identity is recorded in the [native client provenance](../qa/native-client-observer-provenance.json),
and its live observations are in the
[native client receipt](../qa/host-spectator-native-client.json).

The published browser client also entered the rendered world through its
normal menus, moved and turned, and completed a normal death/respawn while the
observer continued following the same peer and connection generation. It then
departed through Escape → Abort → Yes. The
[browser client receipt](../qa/host-spectator-browser-client.json) records the
unchanged published JavaScript/WASM hashes and the observed camera poses.
For both clients, departure returned the observer to free-camera mode and an
attempt to follow the departed identity returned HTTP 409. The same core
process, PID 22478, remained running as the joined-player count changed from
4 to 3 to 2, leaving the two bots in the match. These observations do not add a
fresh original-retail participant to the session.
The [shared-cohort receipt](../qa/host-spectator-shared-cohort.json) records the
four joined identities and the active observer in that same match.

The [live panel receipt](../qa/host-spectator-live-panel.json) separately records
authenticated view opening/closing, a full-height 640 × 360 frame, free-camera
travel through the floor, released input stopping movement, following a current
player, control reacquisition after reload, and correct horizontal look
direction. The engine process and player count remained unchanged by camera
controls. Layout checks passed at 1440, 390 and 320 pixels with no page errors.

The [live lease receipt](../qa/host-spectator-lease-live.json) records 5,764
authenticated frame responses over 1,243.36 seconds. After frame requests
stopped, the observer was off at the 6.5-second check, while the same core and
two bots remained in the match. Subsequent server shutdown cleared the session,
connection and process status and released the owned core, bot, panel and
browser processes. This is a bounded local observation, not a long-duration
soak result.

The initial host view uses the packaged Linux server and a Unix inherited frame
channel, with 640 × 360 RGBA frames capped at 5 fps. The observer is a separate
camera with no game actor, joined identity or additional player slot. Its frame
stream and typed controls remain on the private supervisor boundary; the game
continues when the view closes. The game-facing browser gateway, published
client assets, packaged bot components, and DirectPlay adapter code/binary
remain unchanged as recorded in the
[component preservation receipt](../qa/host-spectator-component-preservation.json).

### Retail attempt and qualification limits

The fresh original-retail attempt was blocked before either the game or the
DirectPlay bridge launched. Wine 9 i386 child execution was unavailable on the
host kernel, and the QEMU-assisted prefix bootstrap failed to load
`kernel32.dll` with status `c0000135`. The original Windows files were rechecked
unchanged. The [retail attempt receipt](../qa/host-spectator-retail-attempt.json)
records the failed setup stage, bounded diagnostics and cleanup. The preserved
adapter and passing C regressions do not establish a fresh retail gameplay pass.

No fresh acceptance is claimed here for original-retail gameplay, MotS, CTF,
NAT traversal, public Internet conditions or a long-duration soak. The JK
movement, respawn and observer cases do not establish exhaustive weapon,
force-power, damage or mod parity. Historical receipts below retain their
original dates, binaries, scope and limitations; they are not new tests of this
checkout.

## Original JK adapter corrections — 2026-10-25

The historical main-branch adapter checkpoint used DirectPlay gateway SHA-256
`73158f1dda3782ab9ab80b175fcf9d08ba576c36db24687bfbb9fbfb29af3c95`.
That checkpoint imported the adapter's JK score-layout correction,
verified-departure policy, binary, tests and supporting documentation without
the bot prototype. This feature branch retains those corrections and its
later bot/admin, reconnect and DirectPlay surrogate lifecycle behavior.
The current artifact identities are recorded in `SHA256SUMS`; the hashes below
identify historical test binaries, not a new qualification of this checkout.

| Check | Observed result and limit | Evidence |
| --- | --- | --- |
| Original JK roster field semantics | Original executable sender, receiver and death handling establish team U8 followed by kills/deaths/suicides/score S16. Native conversion preserves full counts and signed values. MotS semantics were not newly verified. | [Original layout audit](../qa/retail-jk-score-layout-audit.json) |
| Corrected score display on intermediate gateway `4ee4d6ab…` | Paired native/retail tables agree, including the human death count. The same run later failed during normal retail departure with Send `0x80070057`; that failure remains recorded. | [Scoreboard regression](../qa/retail-jk-scoreboard-regression.json) |
| Final gateway `73158f1d…` | Original retail joined, left, rediscovered, rejoined and left the same running session. Engine, gateway and four fixture-client processes remained unchanged. No failed Send or `send_departure_check` occurred, so live execution of the reconciliation branch remains unverified. | [Departure regression](../qa/retail-jk-departure-regression.json) |
| Deterministic adapter checks | Independent score fixtures, both conversion directions, complete-prefix truncation/capacity checks and 15 departure-policy assertions pass. The policy rejects live destinations/remotes, invalid or absent sources, and incomplete/overflow snapshots. | `make -C directplay test`; build/test metadata in the departure receipt |

These three receipts were produced in the separate prototype worktree at
commit [`e7e1ed64128e95d0a091d169673b34194e80ea03`](https://gitlab.com/codalilitari/jk-cross-server/-/commit/e7e1ed64128e95d0a091d169673b34194e80ea03).
Their test sessions used four bot clients as external fixture participants;
the recorded bot names, binary hashes and process IDs are retained as test
provenance. This feature branch includes the bot implementation. Adjacent
provenance fields locate the baseline bot receipt at that immutable
source commit. Raw evidence inventories retain filenames and digests, rather
than packaging the original screenshots, observations and runtime logs.
Importing these receipts does not represent a fresh live test of the merged feature checkout.

The original failure's root cause was not established. The final natural
departure test verifies continuity, and the compiled policy tests verify its
acceptance/rejection decisions; neither establishes that every provider timing
race is fixed. No new MotS or Windows-hardware qualification is claimed.
Historical receipts below retain their original builds and conclusions.
In particular, `qa/directplay-protocol-tests.json` records the earlier converter
whose tests did not detect the JK score-field error; it is not the current JK
layout specification.

## Sources and unchanged clients

The pins in this section describe the retained baseline qualification. The
three adapter receipts above identify their own exact test binaries separately.

| Component | Exact source or identity |
| --- | --- |
| Server core | `https://gitlab.com/codalilitari/OpenJKDF2-MotS-Fixes`, base `74e4657c4f1751d09af9ad9e056acb8f41997acb`, plus the included server-only patch |
| Native client | The same base commit with no server changes; executable SHA-256 `f3dad60ab0e4c387da4e13920b1930b18cb61e430f28036056da673d31737085` |
| Retail JK | Original US JK executable; SHA-256 `fc6d3e798da1ca940232afef217cd701d280b0f2f55907b398071e7807db548c` |
| Retail MotS | Original US JKM executable; SHA-256 `23cd064217f904d36d896f52d3cdd17635bb85441a12e0415c0637504191d974` |
| Browser client | Published `cloudflare-38` assets, repository `tristamus/jkdf2mp-bb-server`, commit `24dc3876f32eff57c8ca98ef657698d1a30170c7` |
| Browser engine source | `tristamus/OpenJKDF2`, commit `a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c`, identified by the published build's provenance |
| Browser JavaScript | SHA-256 `4ae0de474cc2ae817c6162fe21a6ac4b73c573d311884253cf002aedc6a46bb0` |
| Browser WebAssembly | SHA-256 `5f40d53acb6c92d11fb87342a9d06b5457f533603329bc59349298f6edfe28b6` |

The native test client was rebuilt from the exact base versions of all four changed translation units and linked with unchanged base objects and dependencies. Its provenance is in `qa/native-client-provenance.json`. Browser HTML/JS/WASM are downloaded and checked against exact published digests; the client files are not edited. Original retail executable hashes are checked independently of the adapter.

Retail qualification uses an isolated original DirectPlay 5 runtime under Wine. Game tests run inside a private network namespace with loopback connectivity and no external route. This is a controlled interoperability test, not a public Internet deployment or a test of every Windows release.

## Release updater acceptance in 0.3

The original 0.3 updater change added release management to the Python control
panel. At that checkpoint, the native engine, DirectPlay bridge, browser
transport, asset-delivery implementations and dependency lists retained their
0.2 contents. Those component-preservation results are historical and do not
describe the later adapter correction above. No new live game-client session
was claimed for the updater change itself.

| Check | Result | Evidence |
| --- | --- | --- |
| Updater, scheduling, package builder, real panel restart, and existing controller/browser regression suite | 67 passed; no failures, errors, or skips | `qa/update-tests.json` |
| GitLab release discovery | Anonymous request to the real public project succeeded; the development worktree correctly recognized the then-published 0.2 release as older | `qa/update-gitlab-check.json` |
| Actual browser panel with simulated release/session state | Desktop 1280 px and mobile 390 px, persisted preferences, readable errors, restart controls, installation disabled during a match, and Stop usable while an update check waits | `qa/update-admin-layout.json` |
| Unchanged game-facing components | Hash comparison against the 0.2 release | `qa/update-component-preservation.json` |

The updater tests install fixture packages, preserve configured and unmanaged
data, remove obsolete managed files, preserve executable modes, and reject
altered checksums, local edits, unsupported dependencies, invalid archives and
insufficient space. A subprocess exits after its first installed replacement;
a new updater instance restores every original managed file from the journal.
Separate tests cover rollback after a write failure, shared session locks,
deferred automatic installation, and shutdown waiting for installation work.

The launcher check starts the actual Python panel without a game, requests a
restart through its authenticated API, observes a new control token, and
confirms that the session remains stopped. Browser UI checks use simulated
release metadata; they do not constitute a public release installation or an
additional multiplayer compatibility test.

The following engineering and game-client records are retained from 0.1 and
0.2. Their original scope and limitations still apply.

## Verified engineering checks

| Check | Result | Evidence |
| --- | --- | --- |
| Python controller, broker, administration, browser transport and asset transfer, unchanged published JavaScript transport and asset modules | 34 passed; no failures, errors, or skips | `qa/python-tests.json` |
| Native source patch | Applies to the pinned original source and reconstructs the built source files | `qa/native-patch-verified.json` |
| Native IPC parser | AddressSanitizer and UndefinedBehaviorSanitizer checks passed for fragmented/coalesced frames, authentication, bounds, and disconnects | Source test and commands in `native/README.md` |
| Bundled native relinking materials | Rebuild from a clean extracted relink kit succeeded | `qa/native-relink-verified.json` |
| Supervisor with actual JK content | Loaded the dedicated `JK1MP/m2.jkl` world, exposed real session metadata, opened the browser gateway, and stopped cleanly | `qa/controller_smoke.json` |
| Headless engine and prepared Wine runtime | Started the packaged engine, original DirectPlay helper, real DirectPlay host and identity pool with no inherited display; stopped the owned session | `qa/wine-setup-headless-lifecycle.json` |
| Historical retail packet conversion | The earlier deterministic suite passed but did not detect the JK score-field mapping error; current JK correction and tests are described above | `qa/directplay-protocol-tests.json` |
| Actual browser administration UI | Form, running-state controls, status and logs rendered without clipping or page errors | `qa/admin-browser-layout.json` |
| Live browser-download panel in 0.2 | Offered episode/mod hashes, enabled policy and actual transfer counters rendered at 1280 px and 390 px without script errors or horizontal overflow | `qa/browser-asset-admin-layout.json` |
| JK synthetic game peer | Actual engine world load, full synchronization, WELCOME, human count 0 → 1 → 0 | `qa/native-jk-synthetic.json` |
| MotS synthetic game peer | Actual engine world load, full synchronization, WELCOME, human count 0 → 1 → 0 | `qa/native-mots-synthetic.json` |

The Python WebRTC tests establish negotiated game and asset channel behavior. The optional published-JavaScript tests exercise the author's unchanged transport, asset download, reconstruction and mod fingerprint functions under Node. Neither starts the full browser game. The two synthetic peer checks exercise the real engine but are also not substitutes for original-client gameplay.

## Actual game-client acceptance

The stock-session receipts below are the 0.1.0-dev baseline. Version 0.2 keeps
the same native engine and DirectPlay bridge binaries and extends the Python
browser adapter with content delivery. The new rendered-browser asset cases
are recorded in their own section below; the stock three-client cases were
not rerun as new custom-mod sessions.

| Mode and stock world | Actual clients and observed behavior | Receipts |
| --- | --- | --- |
| JK: `JK1MP/m2.jkl`, Nar Shaddaa Loading Terminal | Original retail, unchanged native and published browser clients joined simultaneously. The engine reported three fully joined humans. Each client's normal movement was observed by another client; native and original-retail chat reached the browser. | `qa/native-jk-live.json`, `qa/retail-jk-live.json`, `qa/published-wasm-jk-three-client.json` |
| MotS: `JKM_MP/mdm02_freezer.jkl`, Carbon-freeze Chamber | All three unchanged clients joined simultaneously and exchanged movement/chat. Actual native and retail pistol projectiles were instantiated across transports with matching GUIDs; the browser also observed native projectiles. A normal world death and respawn propagated to original retail and browser, including deaths 1, suicides 1, score -1 and restored health 100. | `qa/native-mots-live.json`, `qa/retail-mots-live.json`, `qa/retail-mots-projectiles.json`, `qa/published-wasm-mots-three-client.json` |
| MotS: ordinary retail departure on the final gateway build | Original retail left through Escape → Abort → Yes. The joined human count changed from three to two; the engine and adapter processes continued, and native/browser players remained active in the same world. | `qa/retail-mots-disconnect.json`, `qa/native-final-disconnect-continuity.json`, `qa/published-wasm-mots-retail-leave.json` |

The observations use normal menus, keyboard/mouse input, and bounded read-only state inspection. No process memory, retail executable, client engine source, or published browser asset was patched. The independent single-browser JK/MotS full-game checks are also retained under `qa/`.

Position snapshots show stable coordinate differences between client simulations. The MotS native-versus-retail respawn sample differs by approximately 0.105607 world units. Exact convergence is not claimed. Thresholded smoothing exists in the inspected clients, but it has not been isolated as the cause of the measured differences.

The MotS death was caused by ordinary map movement and the world, not a qualified player-versus-player kill. Projectile creation, death/respawn and score propagation are verified; exhaustive damage, weapon and force-power parity is not.

The first original MotS attempt completed its welcome but took about 40 seconds to initialize the software renderer under the contended emulation fixture, exceeding the game's activity timeout. A warmed rejoin sustained the three-client session. That first timeout is retained as a fixture limitation rather than counted as a sustained pass. Original media checks used the actual JK Disc 2 followed by the MotS disc with a correctly configured virtual CD-ROM. The executable and media markers were unchanged.

The portable QEMU/Wine setup emits X-connection and signal diagnostics when its virtual display/background services end. The headless lifecycle receipt records these messages and the controlled stopped state. This fixture is separate from a normal installed x86 Wine environment.

## Browser missing-content acceptance in 0.2

These checks start the unchanged published HTML, JavaScript and WebAssembly in
Chromium with original game content but without the selected custom episode or
mod. They use the normal folder picker and multiplayer menus. The test
episodes retain stock worlds/scripts and add an authored manifest and original
green/white materials. The selected test mod replaces those materials with
magenta/yellow stripes and includes an original-game reference. Visible
materials distinguish the loaded content from a successful byte transfer alone.

| Game and starting content | Observed result | Evidence |
| --- | --- | --- |
| JK, selected custom episode absent | Downloaded and installed `QAAssetJK.gob`, entered rendered `m2.jkl`, showed the authored green/white materials, and responded to normal movement. The engine reported one fully joined browser player. | `qa/browser-asset-jk-missing-map.json` |
| JK, selected episode and active mod absent | Downloaded the five-file `MarkerMod-jk` pack, verified its fingerprint, and restarted through the client's normal mod flow. Following the ordinary Multiplayer rejoin prompt downloaded the episode and entered the world with the mod's magenta/yellow materials visible. Every installed mod file matched the host. | `qa/browser-asset-jk-mod-restart.json` |
| MotS, selected custom episode absent | Downloaded and installed `QAAssetMotS.goo`, entered rendered `mdm02_freezer.jkl`, showed the authored green/white materials, and responded to normal movement. The engine reported one fully joined browser player. | `qa/browser-asset-mots-missing-map.json` |
| MotS, selected episode and active mod absent | Downloaded the five-file `MarkerMod-mots` pack, restarted through the ordinary client flow, and downloaded the episode on normal rejoin. The rendered world showed the mod's magenta/yellow material; movement/chat worked, one browser human was fully joined, and all installed mod files matched the host. | `qa/browser-asset-mots-mod-restart.json` |

For the JK episode case, the complete archive was 3,362,331 bytes. The actual
captured transfer stream was 29,328 bytes; 21 content references reconstructed
3,333,847 bytes from the browser player's original archives. An independent
validator reconstructed the captured stream and compared the resulting archive
byte for byte with the host's selected file. The installed browser archive
also had the same SHA-256. Actual served HTML/JS/WASM hashes matched the pinned
publication, and the client files were unchanged after the run.

The JK mod stream was 25,828 bytes with one original-content reference. Its
captured stream also reconstructed exactly. The client displayed its existing
restart notice; returning through Multiplayer and rejoining was a normal
manual menu action, with the room already selected. Automatic entry into the
world immediately after restart is not claimed.

The MotS episode was 14,834,653 bytes. Its captured 40,605-byte stream used 85
references to reconstruct 14,797,452 original-content bytes locally. Both the
independent reconstruction and the installed browser archive matched the host
exactly. The published MotS engine rendered the custom material and maintained
an active joined player through normal movement input.

In the final MotS mod case, the episode and mod streams totaled 66,435 bytes:
40,605 for the episode and 25,830 for the five-file mod. The mod's additional
original-content reference reconstructed 87,180 bytes locally. The captured
mod stream rebuilt the exact 112,966-byte host pack, and the running browser's
mod fingerprint and installed file hashes matched. The same live session
supplied the administration panel's real content and transfer-counter data
for desktop/mobile layout inspection.

These rendered-game asset cases use the published WebSocket fallback in a
private local network. The separate automated suite exercises actual WebRTC
asset channels, retry and chunk rules, peer departure, backpressure,
disabled-download behavior and interleaved game traffic. It also executes the
exact published JavaScript download/reconstruction and mod-packing functions
under Node. The new asset acceptance cases concern browser delivery; the
preceding three-family gameplay receipts concern the stock sessions.

## Limits of this build

Mixed sessions support up to 15 configured slots; native/browser sessions with the retail adapter disabled can configure up to 31. These totals include the dedicated host, leaving at most 14 or 30 playing clients respectively, shared by humans and bots. Stock maps can impose lower practical spawn limits. Real DirectPlay surrogate objects can inflate the count shown by the original retail session browser. The administration count uses the simulation's fully joined players.

The default MotS native wire profile targets the pinned native client's 16-bit absolute-CreateThing sector reader. A corrected 32-bit native reader requires the documented server environment option. Both profiles cannot be inferred automatically from the client's connection.

The browser's existing WebSocket fallback throttles some movement updates to 200 ms. A full-game result over fallback is recorded as fallback; an independent successful WebRTC test is not presented as proof that the same full-game session used WebRTC.

Browser map and mod delivery use the published client's existing protocol in this build. The asset checks are separate from the preceding stock three-client acceptance runs. They do not certify broad mod gameplay parity, every force power and item combination, match rotation, extended multiplayer modes, all client versions, long-duration stability, adverse network conditions, NAT traversal, or public deployment. Keep matching game content on all participants; native and retail clients install custom content locally.

Server startup still needs an initial X/OpenGL context; the supervisor supplies Xvfb when no display is configured. The bundled native executable targets the recorded Ubuntu 24.04 x86-64 environment. Rebuilding is the supported route for a different system ABI.

## Reproduce the software tests

After installing the pinned Python dependencies from the project root:

```sh
python -m unittest discover -s tests -p 'test_manager.py' -v
python -m unittest web_gateway.test_gateway web_gateway.test_admin -v
python -m web_gateway.fetch_client --destination runtime/browser-client
JKDF2WEB_CLIENT_DIR=runtime/browser-client python -m unittest web_gateway.test_published_client web_gateway.test_assets -v
```

The last test requires Node 24 or newer. Tests use local sockets and require ordinary local networking permissions. Native parser test commands and native rebuild/relink instructions are in `native/README.md`; DirectPlay setup and bridge compilation are in `directplay/README.md`.

Actual game-client checks additionally require the user's original installed data and executables. Media source records and content hashes are retained as evidence. Game archives, original executables, ISOs, and Microsoft runtime files are excluded from the distribution.
