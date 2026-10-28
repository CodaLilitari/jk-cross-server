# Browser Geometry Spectator Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Independent native, manager and browser portions of Task 2 run in parallel with disjoint ownership; root integrates and owns commits and publication.

**Goal:** Add an optional live flat-colour WebGL spectator while preserving the existing image observer and gameplay isolation.

**Architecture:** Capture the current private observer's projected draw lists into a bounded JKSG envelope. An independent inherited socket carries geometry to the authenticated manager, which serves the latest current frame to a WebGL 2 canvas.

**Tech Stack:** C native engine, Python asyncio/aiohttp manager, plain JavaScript/WebGL 2; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-28-browser-spectator-design.md`; exact shared contract: `docs/SPECTATOR_GEOMETRY_PROTOCOL.md`.

## Global Constraints

- The image view remains the default and available as fallback.
- No player slot, world actor or gameplay peer is created; current free/follow controls, epochs and render isolation remain authoritative.
- No game-media downloads or retail assets in commits.
- Geometry uses the independent `OPENJKDF2_SPECTATOR_GEOMETRY_FD` and the exact JKSG contract above.
- Maximum vertices 65536, indices 196608, payload 2097152 bytes; native captures at the existing <=5 fps cadence.
- Geometry work is opt-in via supervisor operation 3 and expires after 5000ms without renewal.
- Keep all HTTP access under the existing loopback/same-origin/Bearer guard.
- No claim of texture parity, graphics-free startup or performance improvement in this milestone.
- Baseline source d7009dcebe259db98003bfc668e2ca98909cf20f; published baseline d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2 has the identical tree.

## Review Focus

- A frame partially sent when epochs change must not corrupt the reused stream: native channel test.
- A geometry-specific failure must leave RGBA and gameplay working: manager socket/HTTP regression.
- A delayed fetch from the old backend/session must not draw or reclaim control: browser UI race regression.
- Native depth conventions differ from ordinary world-space projection: literal fixture plus real WebGL pixel evidence.
- A disabled, missing or lost WebGL context must preserve usable image controls: browser fallback regression.

## Task 1: Baseline and fixed interfaces

Files: this plan, the approved design, `docs/SPECTATOR_GEOMETRY_PROTOCOL.md`, development ledger.

- [x] Create isolated project and native worktrees; preserve original sources/build.
- [x] Read current observer, manager, panel and native projection boundaries.
- [x] Complete baseline Python/Node/native observer runs: 159 Python, 16 Node cases, and 12 native observer checks passed; commands/results retained in the development ledger.
- [x] Commit the approved design and exact protocol; publish a GitLab checkpoint.

## Task 2A: Native geometry capture and independent delivery

Files: reconstructed engine `src/Main/jkObserver.c/.h`, new `src/Main/jkObserverGeometry.c/.h` if useful, `src/Raster/rdCache.c`; project `native/tests/test_spectator_geometry.c`, runner updates and regenerated `native/crossplay-dedicated.patch`.
Consumes: exact operation 3 and JKSG wire profile.
Produces: capability 16, opt-in 5-second geometry lease, matching-sequence clip-space frames; geometry failures independent from RGBA.

- [x] Write and run failing native cases for hand-derived projection/colour/index rebasing, malformed/oversized batches and independent socket lifetime.
- [x] Implement capture inside the existing read-only render scope, with fixed bounds and exact wire encoding.
- [x] Implement operation 3, independent nonblocking FD validation, partial-send completion and lease/epoch reset.
- [x] Run geometry cases and existing native observer suite; retain RED/GREEN output.
- [x] Rebuild changed native units into an isolated binary using local compile/link inputs.
- [x] Report exact changed files, tests and build commands; root regenerates/packages the source diff if needed.

## Task 2B: Manager validation, lifecycle and authenticated route

Files: new `manager/spectator_geometry.py`, `manager/spectator.py`, `manager/runtime.py`, `manager/admin.py`, `web_gateway/ipc.py`; tests `tests/test_spectator_geometry.py`, relevant fixture/IPC tests.
Consumes: exact JKSG and operation 3; baseline image controller.
Produces: additive geometry status and async `spectator_geometry(**query)` serving full envelopes via `/api/spectator/geometry`.

- [x] Write and run failing tests using real local sockets/HTTP for geometry framing, lease renewal, authorization, epoch/age rejection and fallback independence.
- [x] Add typed operation 3 without changing ordinary gameplay framing.
- [x] Prepare and close the independent geometry FD alongside the image FD; retain only the latest fully validated frame.
- [x] Enforce shared bounds, finite attributes, index limits, current epochs and capture age through HTTP delivery.
- [x] Add allowlisted `spectator-geometry.js` asset and route with the existing guard.
- [x] Run focused manager/IPC regressions and record RED/GREEN evidence; root runs full suite after integration.

## Task 2C: Browser decoder, renderer and optional panel view

Files: new `manager/ui/spectator-geometry.js`, `manager/ui/spectator.js`, `manager/ui/index.html`, `manager/ui/style.css`; `tests/test_spectator_geometry_ui.js` and fixture updates.
Consumes: exact JKSG body, geometry status, unchanged camera controls.
Produces: CommonJS-testable decoder and browser renderer, explicit image/experimental-geometry selector and separate canvas.

- [x] Write and run failing decoder cases for literal clip-space fixture, lengths/counts/index/finite/epoch/age boundaries.
- [x] Implement `decodeGeometry(buffer, epoch, after, elapsedMs=0)` and a small WebGL 2 renderer drawing indexed opaque triangles.
- [x] Add explicit geometry selection; preserve camera-control ownership and wire events to either canvas.
- [x] Reject obsolete fetch completions after selector/epoch/session changes; release held input on switches.
- [x] Handle unsupported/lost WebGL with usable image fallback; no geometry polling after fallback.
- [x] Run focused Node/UI tests; provide a deterministic original synthetic fixture for root's real browser verification.

## Task 3: Integration, qualification and packaging

Files: native binary/relink/provenance/checksums, `qa/browser-spectator-geometry-*.json`, original synthetic fixture and selected screenshots, docs updates.

- [x] Review each component diff for spec compliance and quality, resolving important findings before acceptance.
- [x] Run full manager Python, gateway tests, Node UI suite and applicable native regressions on the integrated code.
- [x] Run real WebGL synthetic scene and inspect readback/screenshot for depth, orientation, colour, aspect and winding.
- [x] Launch the isolated rebuilt engine with the existing local stock map and a moving client; prove live geometry, free/follow and unchanged identity/player count.
- [x] Exercise channel failure/slow viewer and verify the image path/game process survive.
- [x] Package the rebuilt binary and relink archive with exact source/build hashes; record any remaining qualification limits.

## Task 4: Review and durable publication

- [x] Obtain a fresh whole-branch review with test evidence and full diff.
- [x] Commit implementation and qualification artifacts; publish the development branch to GitLab.
- [x] Retry GitHub only with legitimate available write authentication; record any persistent provider blocker.
- [ ] Verify remote file tree and update the checkpoint Page with exact identities and test results.
- [ ] Provide human-readable and machine-readable delivery records, then report completed behavior and limits.


Finalization note: the GitLab code/native-artifact checkpoint is verified; the final small fix/evidence commit, Page links and external human/machine delivery receipt are tracked separately to avoid embedding a self-referential final commit hash. GitHub write authentication remains blocked (fresh403, 28October2026).
