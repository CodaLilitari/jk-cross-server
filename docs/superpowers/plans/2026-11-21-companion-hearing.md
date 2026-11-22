# Companion bridge and hearing implementation plan

> **For agentic workers:** Use the parallel implementation boundaries below,
> with meaningful RED/GREEN checks and a fresh final review.

**Goal:** Run an authenticated companion beside ordinary JKDF2 bots and give
the bots spatial hearing without interrupting local gameplay.

**Architecture:** Scoped Python HTTP/CLI control over inherited nonblocking
native datagram channels. Actual sound requests feed a bounded native auditory
memory. Current JKWeb bot builds host/join a private netcode-2 browser room; native
Cross Server support is a separate compatibility path.

**Tech Stack:** Python standard library, existing Python project dependencies,
C native OpenJKDF2 input driver, Unix socketpair, current packaged engine inputs.

**Spec:** `docs/superpowers/specs/2026-11-21-companion-hearing-design.md`.

## Global constraints

- JKDF2 only; preserve ordinary game protocol and game authority.
- No frame-loop network waits; maximum datagram 512 bytes, header `<4sBBHIII`.
- World/life/run fencing, finite expiry at most 30 seconds, one scoped controller.
- No private original game assets, credentials or personal paths in public git.
- No new claims of human strength or unmeasured browser compatibility.
- Existing feature branch and PR publication authorization remain in effect.

## Review focus

- A slow/crashed companion must leave gameplay and autonomous fallback running.
- A reused player slot or world must never inherit an old command/target.
- A duplicate or dropped acknowledgment must not duplicate chat or report false success.
- Auditory events must remain actual sound observations; the separately authorized elite policy may read synchronized player positions. Audio playback gates must not suppress hearing.
- Browser transport compatibility and actual native/client hook execution must be proven separately from fixture tests.

## Task 1: Scoped hub, CLI and launcher

Files: new `bots/companion.py`, `bots/companion_cli.py`,
`tests/test_companion.py`; edit `bots/run.py`, `tests/test_bots.py`.
Consumes the spec's native ABI. Produces channel descriptor creation, bounded
polling, private credential file, documented HTTP/CLI endpoints and clean shutdown.

- [ ] Add and run failing protocol/auth/lease/idempotency/queue tests.
- [ ] Implement codecs, hub and local HTTP server; no external model dependency.
- [ ] Integrate optional launcher flag and owned descriptor lifecycle.
- [ ] Verify meaningful isolated socketpair round trips and existing launcher tests.
- [ ] Commit component and record evidence.

## Task 2: Native companion and actual strategic effects

Files: engine `src/AI/jkBotCompanion.inc`, `jkBot.h`, `jkBot.c`,
`jkBotNavigation.inc`, `jkBotCombat.inc`, `src/Dss/sithMulti.c`;
repo `native/tests/test_bot_companion.c` and runner.
Consumes ABI and `jkBot_GetHearing`. Produces scoped observations, command ACKs,
safe public chat receipt/submission and expiring strategic movement/goal changes.

- [ ] Add and run failing frame/fence/dedup/strategy tests against real driver.
- [ ] Implement bounded nonblocking C transport with lifecycle reset.
- [ ] Validate delivered chat before exporting public messages only.
- [ ] Apply legal policy biases to target, resource, weapon and engagement decisions.
- [ ] Verify no-bridge behavior, expiry, stale identity and backpressure controls.

## Task 3: Native hearing

Files: engine `src/AI/jkBotHearing.inc`, `jkBot.h`, `jkBot.c`,
`src/Devices/sithSoundMixer.c/.h`, `src/World/sithSoundClass.c`,
`src/World/sithWeapon.c`; repo hearing driver tests.
Consumes actual audio metadata and collision/sector graph. Produces the hearing
callback and `jkBot_GetHearing` summary plus turn/investigation behavior.

- [ ] Establish failing audible rear-step versus silent negative-control tests.
- [ ] Preserve emitter/class metadata before audio rendering gates.
- [ ] Implement bounded acoustic path, attenuation, coarse memory and expiry.
- [ ] Integrate auditory attention, elite 360-degree awareness and privileged route pursuit while preserving physical shot checks.
- [ ] Verify closed portals, own sounds, ambiguous arrivals and lifecycle reset.

## Task 4: Integrate, build and qualify

Files: complete native patch/package/provenance, `docs/COMPANION.md`, QA harness
and numeric receipts. Root owns integration; native agents work in separate
engine trees to avoid simultaneous edits. Rebuild all changed C units, not just
the previously rebuilt bot/GUI pair.

- [ ] Merge engine deltas and run native plus Python regression suites.
- [ ] Add the smallest ordinary visible-bot/third-person hook needed for demo.
- [ ] Package verified native inputs; run private game observation, strategy ACK,
      expiry and independent chat-receipt checks on the user's authorized PC.
- [ ] Qualify current JKWeb custom clients through the current upstream private relay; document any blocker.
- [ ] If assets and hardware/render path are ready, capture and inspect requested
      120-second Canyon Oasis four-bot demo; otherwise report exact missing part.
- [ ] Fresh independent review, fixes, manifest refresh, commit and publish PR update.

## Progress

Tasks 1–3 implemented in separate ownership areas and integrated. Native hearing,
companion and 32 driver fixture groups pass. The current JKWeb WASM build compiles
with Emscripten 6.0.12; 220 Python tests pass (two existing skips). A private
netcode-2 relay handshake has been exercised. These are not live-game or
human-strength results. The user's subsequent current-JKWeb/privileged-knowledge
instruction supersedes the initial pinned-browser-only architecture. Runtime
qualification and demo capture remain task 4.
