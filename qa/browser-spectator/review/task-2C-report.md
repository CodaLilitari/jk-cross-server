# Task 2C — browser decoder, WebGL renderer and optional view

Status: implementation and focused automated verification complete. Real-browser synthetic and live-world qualification remain the root agent's acceptance work. No visible-rendering or live-engine success is claimed by this report. No commits were made.

## Owned changes

- `manager/ui/spectator-geometry.js`: CommonJS/browser-compatible JKSG v1 decoder and small WebGL 2 renderer.
- `manager/ui/spectator.js`: explicit backend state, obsolete-request cancellation and generation checks, geometry polling, age enforcement, independent canvas input wiring and image fallback.
- `manager/ui/index.html`: decoder/renderer prerequisite script, explicit image/default versus experimental geometry selector, independent geometry canvas and accessible status.
- `manager/ui/style.css`: responsive backend selector and geometry canvas presentation.
- `tests/test_spectator_geometry_ui.js`: 17 decoder and mounted-controller behavior cases.
- `tests/spectator_fixture.js`: extracted and expanded reusable event/network/WebGL boundary test fixture.
- `tests/test_spectator_ui.js`: imports the extracted fixture; preserves its 9 baseline cases.
- `tests/test_panel_ui.js`: updates the prerequisite script-list expectation to include `spectator-geometry.js`.
- `tests/fixtures/spectator_geometry.jksg`, `.json`, `.html` and `spectator_geometry_harness.js`: original synthetic numeric fixture, provenance/expected samples and real-browser GPU readback harness.

No Python or native source was edited. Other workers' modifications remain separate.

## Frozen interfaces

Module export and browser global:

```js
const {decodeGeometry, createRenderer} = require('./manager/ui/spectator-geometry.js');
window.JKSGGeometry.decodeGeometry(buffer, epoch, after, elapsedMs = 0);
window.JKSGGeometry.createRenderer(canvas, {onContextLost = () => {}} = {});
```

`buffer` is a complete ArrayBuffer containing the exact 64-byte JKSG envelope header plus payload. `epoch` is `{world_epoch, control_epoch}`; `after` must be a uint32 cursor including zero. `elapsedMs` must be finite and nonnegative. Invalid input throws an Error before any GPU upload.

The returned decoded frame is:

```js
{
  width, height, world_epoch, control_epoch, sequence, age_ms,
  vertices, // Uint8Array view, 20 bytes per vertex: LE float32 x/y/z/w + RGBA8
  indices   // Uint32Array, explicitly decoded from little-endian wire indices
}
```

`age_ms` includes both the envelope's capture age and supplied fetch elapsed time. All protocol caps, counts, flags, reserved values, finite components, opaque alpha, index bounds, epochs and replay cursor constraints are checked. The inclusive 2000-ms boundary is accepted. Empty geometry is accepted only with both counts zero and clears the canvas.

`createRenderer` returns `{draw(decodedFrame), clear(), dispose()}`. It obtains the canvas's WebGL 2 context, compiles the real GLSL program, and owns a VAO, one vertex buffer and one index buffer. Positions are passed unchanged to `gl_Position`; RGBA8 colours use a normalized attribute. `draw` uses indexed `TRIANGLES` / `UNSIGNED_INT`, LESS depth testing with writes enabled, and blending/culling disabled. It clears colour and depth before every frame. No texture, image, video or external asset is involved. `dispose` releases the program, shaders, VAO and buffers. Context loss prevents further draws and invokes `onContextLost`; the UI selects the image view.

The UI consumes the agreed additive manager status:

```js
geometry: {
  available, frame_available, sequence, age_ms, reason,
  profile: 'flat-colour-v1'
}
```

Absent `geometry` means unavailable. Geometry requests use only the frozen authenticated GET route with `after`, `world_epoch` and `control_epoch`; no new camera command or status dependency was introduced.

## Presentation, controls and lifetime

Image view is the HTML default. Geometry is explicitly labelled experimental. Selection changes only presentation; it never PUTs camera configuration, obtains a new observer, or silently claims camera control. Both canvases use the existing input/drag semantics. Responsive touch movement buttons remain the same controls and ownership guards.

Each backend switch clears held movement/look and both outputs, resets the display sequence, aborts the obsolete presentation request, and advances a separate presentation generation. Geometry and image fetches check that generation plus current backend, camera revision, world/control epochs, server state and document visibility before drawing. The same checks reject late errors, preventing an obsolete request from changing the new view's state. An aborted request cannot keep the new backend's polling busy while its old body is delayed.

Raw request timeouts now cover receipt of the body as well as headers. The full fetch elapsed time is conservatively added to header capture age before decode. A geometry envelope older than the latest known geometry status sequence is discarded. Display freshness is based on capture age, with the geometry overlay stale threshold at 2000 ms. Hidden/inactive views stop geometry polling and invalidate pending output.

Unavailable WebGL, shader/buffer setup failure, context loss, unavailable geometry status and geometry channel/decode failures all leave the image presentation selectable and usable with an explanatory backend status. Geometry polling stops after fallback. Timeout/stale-epoch requests can be retried without changing ownership.

A final ownership review found that the baseline could retain local ownership across a session-readiness interruption if PID and epochs were reused. A failing regression reproduced this. Inactive sessions now revoke local ownership, requiring explicit Take camera control after readiness resumes. Ordinary display switches preserve ownership, as required.

## RED / GREEN evidence

Initial behavior tests were written before implementation. Command:

```sh
node tests/test_spectator_geometry_ui.js
```

Initial RED: 12 tests, 0 passed, 12 failed. Failures included missing decoder behavior, no geometry request after explicit selection, no release on selection, no geometry canvas input, no unavailable/lost-context fallback and no indexed draws. The late-response cases explicitly asserted that the geometry request had actually begun before checking rejection, so absence of the new path could not produce a false passing race test.

After minimal decoder/renderer/UI implementation, 11/12 passed. The remaining test required respecting the baseline's 95-ms input rate limiter; its test now waits one input cadence before checking subsequent movement. Initial GREEN: all 12 passed; all 9 baseline spectator cases also passed.

Further independent failure cases were written and run before their fixes:

- Delayed geometry body blocked image polling after context loss: RED 12 passed / 2 failed in the expanded 14-case suite (the second failure was sequence supersession). Fixed request cancellation, full-body timeout lifetime, per-request ownership of busy state and current-sequence check; GREEN 14/14.
- Invalid replay cursors bypassed comparison: RED 15 passed / 1 failed. Added cursor validation; GREEN 16/16.
- Reused PID/epochs restored camera ownership after readiness interruption: RED 16 passed / 1 failed. Revoked local ownership when session becomes inactive; GREEN 17/17.

The original fixture decode test was also added, checking its independent literal counts, indices and w=4 coordinates.

Final direct commands, all exit 0:

```sh
node tests/test_spectator_geometry_ui.js  # 17 passed
node tests/test_spectator_ui.js           # 9 passed
node tests/test_panel_ui.js               # 7 passed
node --test --test-reporter=tap tests/test_panel_ui.js tests/test_spectator_ui.js tests/test_spectator_geometry_ui.js
node --check manager/ui/spectator-geometry.js
node --check manager/ui/spectator.js
node --check tests/fixtures/spectator_geometry_harness.js
git diff --check -- manager/ui/spectator.js manager/ui/index.html manager/ui/style.css tests/test_spectator_ui.js tests/test_panel_ui.js
```

The combined Node run checks the three files; the individual runs show 33 named cases. The static panel test initially failed because its exact script-list expectation omitted the newly required decoder/renderer script. Updating that expectation restored all 7 panel cases.

A full repository run was attempted with `python3 -m unittest discover -s tests`. It immediately encountered repeated `PermissionError: [Errno 1] Operation not permitted` while existing tests attempted to create local sockets under the default sandbox. It subsequently waited in tests relying on that unavailable capability. The environment-blocked run was terminated (exit 143) instead of leaving it active. It did not produce a complete named failure summary, and no Python suite pass is claimed. Root/manager integration verification with working local sockets remains required; no Python test failure was hidden or fixed as part of this browser task.

## Real-browser fixture and root acceptance handoff

Serve the repository root using an approved local static server, then open:

```text
/tests/fixtures/spectator_geometry.html
```

The page loads the production `manager/ui/spectator-geometry.js`, the 656-byte original JKSG fixture and metadata. Its 23 vertices and 33 indices contain:

- A near orange rectangle submitted before an overlapping farther blue rectangle, proving depth ordering when the later far surface does not replace orange.
- Green, magenta and yellow square corner markers and a cyan triangle for orientation/colour checks.
- Opposite triangle windings in each rectangle, proving culling is disabled.
- Independently tabulated clip coordinates with w=1, 2 and 4, including coordinates outside [-1,1] which must divide by w correctly.
- 60 × 60 native-pixel square markers at 640 × 360 to inspect aspect preservation.

The JSON lists synthetic source projected XYZ values, pretabulated clip coordinates, colours, indices and eight expected pixels. It does not execute or claim to test native projection/capture code. There are no retail assets or downloaded dependencies.

After drawing, the harness reads eight actual GPU pixels immediately in the same task, reports PASS/FAIL per pixel and checks `gl.getError()`. It exposes `window.fixtureResult`, `window.fixtureFrame` and `window.fixtureRenderer` for browser automation. The Context loss button uses the optional `WEBGL_lose_context` extension. This isolated harness explains that production UI must fall back; the production fallback itself still needs root's real-panel exercise.

Fixture SHA-256:

```text
f0e1e2757ceb87e936e2cad31cae8c47825aac72244b51176fbd9768af762b41  tests/fixtures/spectator_geometry.jksg
```

Required remaining acceptance: actual synthetic screenshot/readback, production panel unsupported/lost-WebGL fallback, live geometry changes with moving player, free/follow behavior, player/actor isolation and native backpressure/lease evidence. Mocked Node WebGL boundary calls are not presented as visible-rendering proof. The implementation remains the approved flat-colour experimental milestone; textures, transparency/effect parity, graphics-free startup and performance advantages are not claimed.
