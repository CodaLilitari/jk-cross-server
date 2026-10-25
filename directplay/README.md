# Original DirectPlay transport adapter

`gateway.exe` is a 32-bit server-side program. It hosts an ordinary DirectPlay 3
TCP/IP session and connects that session to the dedicated simulation through the
authenticated, loopback-only Python broker. The retail clients continue to use
their original executables and DirectPlay providers.

Build with `make` using `i686-w64-mingw32-gcc`, or an equivalent Windows C compiler
with the DirectPlay 3 headers and import libraries. The build uses strict compiler
warnings and replaces the executable atomically, so rebuilding does not truncate
a binary already running in a test session.

## Runtime

The supervisor supplies `JK_GATEWAY_TOKEN` and `JK_GATEWAY_PORT`. The adapter also
accepts:

```
gateway.exe --broker 127.0.0.1 --port 46001 --pool 7
```

Only IPv4 loopback is accepted for the broker connection. The token must contain
16–512 bytes and is never logged. Game traffic uses the DirectPlay provider;
the local broker port is an internal control/transport connection.

On Linux the adapter runs under Wine. DirectPlay is an external runtime
dependency. Our retail qualification fixture uses the original DirectPlay 5
modules from the JK retail disc in an isolated Wine prefix. The portable,
emulated Wine fixture additionally needs the original `DPLAYSVR.EXE` helper
started explicitly in that same prefix before the adapter. This is a runtime
setup detail, not a game-executable modification. Game media and Microsoft
runtime modules are not included in this project.

### Prepare a dedicated Wine prefix

The included helper accepts the original JK disc's `DIRECTX` directory. It
checks all four runtime-file hashes before making changes, registers the
original TCP/IP provider and COM class, and creates a `wine-dplay` launcher.
Use a separate prefix for the server. An unrelated existing prefix is refused.

```sh
python3 directplay/setup_wine.py \
  --wine /usr/bin/wine \
  --prefix "$HOME/.local/share/jk-cross-server/wine32" \
  --directx "/path/to/JK-disc1/DIRECTX"
```

Wine must support 32-bit Windows programs and a win32 prefix. On a host without
a display, run this setup command through `xvfb-run -a`. The supervisor supplies
virtual displays for the engine and Wine bridge during subsequent headless
starts. Use `--check-only` to verify the original files and print the setup plan
without creating a prefix.

For an existing portable Wine workflow, pass its launcher to `--wine` and add
`--base-prefix /path/to/clean-initialized-win32-prefix`. This clones that clean
base into the new server prefix, preserving its runtime links and normalizing
the clone's C: mapping. It does not change the base. Our emulated portable Wine
fixture needs this seeded-prefix route; fresh `wineboot` is not functional in
that reduced runtime. The ordinary installed-Wine recipe above uses `wineboot`;
it is not a claim that every Wine distribution has been qualified.

In the control panel, set **Wine executable** to the generated prefix's
`wine-dplay` file, **Wine prefix** to that prefix, and **DirectPlay bridge** to
the included `directplay/gateway.exe`. Enable Retail DirectPlay. The generated
launcher starts the original `DPLAYSVR.EXE` before the bridge, then terminates
the helper process it started when the bridge exits. Stop the server before
re-running setup on its prefix.

The helper intentionally accepts only the qualified original DirectPlay 5
hashes. Other runtime versions can be configured manually in their own prefix,
but need separate qualification. No client engine patch is involved in either
route.

## Session identity

The application GUIDs were recovered from the original retail executables:

| Mode | DirectPlay application GUID | Original executable SHA-256 |
| --- | --- | --- |
| JK | `bf0613c0-de79-11d0-99c9-00a02476ad4b` | `fc6d3e798da1ca940232afef217cd701d280b0f2f55907b398071e7807db548c` |
| MotS | `a4ff3960-3b4f-11d1-96cb-444553540000` | `23cd064217f904d36d896f52d3cdd17635bb85441a12e0415c0637504191d974` |

The JK GUID was independently read from the running original client at its
documented runtime field `0x8607f0`; its static source is `0x5221d8`. The MotS
static GUID is at `0x57a1f8`, referenced by its initialization at `0x421e10`
and copied to runtime field `0x941dd0`.

The session name is `name:episode:map`. DirectPlay user fields carry the
simulation's checksum seed, game flags, version/rank, and tick interval using
the original host layout. JK's reconstructed host routine is at `0x42fc90`;
the corresponding original MotS routine is at `0x433840`.

## Player identities and retail compatibility

Mixed sessions reserve real, local DirectPlay player objects for native and
browser peers. The dedicated engine uses those same 32-bit IDs as canonical
player identities. Actual retail clients retain their own DirectPlay IDs.
This lets an original retail client address a native or browser peer through
the same API it already uses for another retail player.

An actual test with the original DirectPlay 5 runtime showed that a
`DPSESSION_CLIENTSERVER` host can create the special server player with ID 1,
but cannot create an additional local surrogate: it returns
`DPERR_ACCESSDENIED`. The adapter therefore uses the original peer-session
flags `0xc0` and maps only the dedicated host's canonical ID 1 to its real
DirectPlay ID. Source-audited management packets 32, 33, 41 and 42 contain the
host-ID fields that need this translation. Object GUIDs, slot numbers, and
arbitrary COG payloads are not rewritten.

Original retail broadcasts only
to roster entries whose active bit is set. OpenJKDF2's dedicated host normally
clears that bit and relies on a client-side special case for slot zero. The
adapter advertises slot zero as a network recipient to retail clients while
leaving its spawn bit cleared and preserving its disabled world object.
This lets the original client send its final welcome, reliable acknowledgments,
movement, and other ordinary messages to the dedicated simulation.

The pure converter in `protocol.c` also translates two original field widths
that changed in OpenJKDF2. In both original JK and MotS, packet 32 stores the
kill count as one byte; OpenJKDF2 uses two. Packet 49 stores the final three
power-up flags as signed 16-bit values; OpenJKDF2 uses 32-bit values. Translation
adjusts the packet length, preserves the reliable sequence, and leaves other
fields intact. MotS packet 2 adds a 16-bit chat-recipient count before its list
of player slots. The adapter preserves broadcast and private-recipient scope
when converting that list to the canonical chat format, including receipt
acknowledgments for filtered private copies.

`make test` runs deterministic layout, truncation, capacity, signed-field,
high-bit identity, reliable-sequence, chat-scope-field and opaque-payload tests
without game data or Wine. The original binary addresses supporting the field
widths are recorded in `qa/directplay-protocol-tests.json`.

Mixed mode supports up to 15 human participants, plus the simulation host.
The DirectPlay session has 32 physical transport slots to accommodate reserved
surrogates and actual retail connections together. The original retail server
browser includes those reserved objects in its player count. The control panel
reports the human count separately. Native/browser sessions without the retail
adapter do not require Wine or the surrogate pool.

Normal peer departures are handled independently of the whole session. If a
queued send reaches DirectPlay after its retail destination has disappeared,
`DPERR_INVALIDPLAYER` removes that peer and drops the stale packet. Other send
failures still surface as adapter errors.

## Qualification

The adapter's startup log emits `ready` only after native DirectPlay session
creation, all requested local surrogate objects, and the simulation's ID-pool
acknowledgment have succeeded. This establishes transport readiness; it does
not by itself establish successful game synchronization or cross-client play.
See the project QA receipts for the completed, version-specific gameplay tests
and any remaining limitations.

The recorded three-client cohorts used stock `JK1MP/m2.jkl` in JK mode and
`JKM_MP/mdm02_freezer.jkl` in MotS personality mode at rank 7. Each included an
original retail executable, the unchanged pinned OpenJKDF2 client, and the
published JKDF2Web JS/WASM. MotS evidence includes actual pistol projectiles
instantiated in both original retail and native clients with matching object
GUIDs, and a normal native world death/respawn with matching original-retail
scoreboard values. See `qa/retail-jk-live.json` and `qa/retail-mots-live.json`.
These are specific interoperability tests, not exhaustive certification of
all maps, weapon/Force interactions, private-chat UI combinations, or Internet
NAT behavior. The emulated retail fixture was slow, and its first MotS attempt
timed out during initial rendering; the warmed rejoin sustained the cohort.

### Original JK roster statistics

The bot-prototype qualification exposed a pre-existing JK scoreboard mapping
error: an original retail client displayed a native player's four deaths as
four kills. Original JK's roster stores team as one unsigned byte, followed by
signed 16-bit kills, deaths, suicides and score. The native format instead puts
team after the three counts and uses 16 bits for every field. The adapter now
reorders those fields in both directions and narrows only team. This preserves
kill counts above 255 as well as signed scores.

The correction is limited to JK. The existing MotS roster conversion remains
unchanged until its field semantics can be checked against an original MotS
executable. Earlier gameplay receipts remain historical records and do not
qualify the new correction. See `qa/retail-jk-score-layout-audit.json` for the
original-executable evidence and `qa/retail-jk-scoreboard-regression.json` for
the corrected gateway's build, regression and live scoreboard checks.

Run `make -C directplay test` to exercise independent score-layout fixtures,
both conversion directions, roster bounds, signed values and the existing
management-message checks. Rebuild with `make -C directplay gateway.exe` using
the documented MinGW toolchain. Human game executables need no patch.
