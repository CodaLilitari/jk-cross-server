# Task 2C independent review

## Verdicts

**Spec compliance: PASS for the browser implementation under review.** No concrete departure from the approved optional flat-colour geometry profile was found. Completion of the overall milestone still depends on the real-GPU fixture, production-panel fallback, live-world qualification and integration/regression acceptance owned by root. This review does not claim those checks passed.

**Code quality: PASS.** No Critical, Important or Minor actionable defect was identified in the reviewed changes and focused surrounding code. No speculative refactoring or style requests are raised.

## Findings

- Critical: none.
- Important: none.
- Minor: none.

## Review scope and evidence

Read the Task 2C brief, implementation report and supplied review diff, the frozen `docs/SPECTATOR_GEOMETRY_PROTOCOL.md` contract, and the approved browser-spectator design. Inspected the complete production decoder/renderer and mounted spectator controller, relevant HTML/CSS, focused decoder/controller tests, reusable mocked boundary fixture, synthetic GPU harness and asset-serving allowlist. This was a fresh read-only review of product code; no product edits, broad test runs, sub-agents or commits were made. The review file is the only reviewer-authored artifact.

### Decoder and real WebGL state

`manager/ui/spectator-geometry.js:11–43` validates the complete envelope, cursor and transfer-age argument, magic/version, dimensions, nonzero epochs/sequence, flags/reserved fields, replay/epoch/age constraints, count caps, exact length and empty-frame rule. Float components, opaque alpha and every index are checked before index-array allocation and GPU exposure. Arithmetic is bounded and safely within JavaScript's exact integer range. The inclusive 2000-ms boundary matches the contract. Indices are explicitly decoded little-endian rather than viewing arbitrary incoming storage as native integers.

`manager/ui/spectator-geometry.js:48–101` creates a WebGL 2 context and actual GLSL ES 3.00 shaders. The vertex shader passes all four clip coordinates to `gl_Position`; colour bytes are normalized with the correct 20-byte stride and 16-byte colour offset. Indexed draws use `TRIANGLES` and `UNSIGNED_INT`. Each draw explicitly establishes LESS depth testing, depth writes, disabled blending and disabled culling, then clears colour/depth. Empty geometry clears without a draw. Program/shader and buffer/VAO allocation failures release created resources. Disposal is idempotent and removes the context-loss listener. The dedicated canvas keeps this state independent of image rendering.

A considered shader-interface concern was rejected: the different inherited vertex-output and fragment-input float precisions are permitted by GLSL ES 3.00 section 4.3.10. The authoritative specification explicitly says the precisions need not match: https://registry.khronos.org/OpenGL/specs/es/3.0/GLSL_ES_Specification_3.00.pdf . This is not a portability finding for the required WebGL 2 target.

### Asynchronous lifetime, freshness and fallback

`manager/ui/spectator.js:79–105, 204–239` separates presentation generations from camera revisions. Clearing presentation aborts and detaches the obsolete request immediately; its eventual `finally` cannot clear a replacement request. Completions and errors require the selected backend, presentation generation, camera revision, epochs, active server/observer and visible document still to match. This covers switching away and back as well as epoch/session changes. The body is received inside the request timeout's lifetime (`106–120`). Fetch elapsed time is conservatively included in geometry age and geometry older than the latest known geometry sequence is discarded before drawing (`217–225`).

Unavailable geometry, missing WebGL, setup failure, context loss and non-retryable channel/decode errors select image presentation with an explanatory status. Image requests do not wait for the obsolete geometry body. The selected backend gates further geometry polling. Hidden/inactive states invalidate pending output and stop frame requests. Retryable timeouts and stale-epoch HTTP responses do not silently reconfigure the camera.

### Ownership, releases, compatibility and cleanup

`manager/ui/spectator.js:87–105, 194–203, 240–289` clears held keys/look and pointer state through the existing release path on backend changes, retains free-camera ownership across ordinary presentation switches and does not issue a camera configuration request from backend selection. Both canvases share the guarded input wiring. Existing pending input has a release follow-up. Inactive-session transitions revoke local ownership even when a resumed process reuses PID/epochs; old requests are invalidated by revision changes.

`manager/ui/index.html:9–11, 35–39` loads the helper before the controller, keeps image explicitly selected by default and uses a separate accessible geometry canvas. Missing geometry status from older engines is treated as unavailable; existing image decoder/route and explicit ownership behavior remain intact. `manager/admin.py:67` permits serving the new static helper. Renderer retention across image/geometry switches is bounded to one renderer and allows reuse; allocation-failure and context-loss paths dispose it. No new unbounded resource or per-switch listener accumulation was found.

### Verification boundaries and intentional tradeoffs

The reported focused Node cases meaningfully cover decoder rejection, backend selection, release/ownership, stale completions, delayed bodies, sequence supersession, fallback and readiness interruption. The WebGL mock cannot prove compilation, rasterization or pixels; the separate synthetic harness calls production code, performs actual GPU pixel readback and checks GL error, providing the right root-owned next check. This review did not rerun Node cases or qualify the actual browser/GPU.

Opaque flat-colour rendering, approximated sky/transparency/special native flags, WebGL 2 as a prerequisite, and continued native scene preparation are approved protocol/design choices. Textures, native visual parity, graphics-free startup and performance advantages are outside this task and are not defects or claimed outcomes. Conservative addition of the whole fetch duration to capture age is also explicitly required by the frozen protocol.
