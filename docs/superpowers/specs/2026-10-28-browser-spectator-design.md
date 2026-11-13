# Browser spectator continuation — approved design

Prepared 28 October 2026 by Lilitari (Lily) for Andrei.

**Status:** approved for implementation by Andrei's “Proceed” on 28 October 2026, following the reviewed design and explicit approval question. The historical publication and reconnaissance statements below describe the pre-implementation checkpoint; they do not claim that this new milestone is complete.

## 1. Preserve the recovered baseline

The completed host spectator is recovered source commit `d7009dcebe259db98003bfc668e2ca98909cf20f`, tree `7cea55eb9c8aed7dcfba6e9068840f6e592112d9`. GitLab branch [feature/host-spectator](https://gitlab.com/codalilitari/jk-cross-server/-/tree/feature/host-spectator) publishes the exact same tree at `d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2`. Its 294 files and seven executable modes were verified independently. The original merge history is retained in the saved recovery bundle.

The existing observer has an independent camera, free flight and follow, no player slot or actor, world/control epochs, input expiry, viewer expiry and an isolated render pass. The host currently renders with native OpenGL, reads RGBA pixels, and sends them to a Canvas 2D browser view. That implementation is real; it is different from a browser that rasterizes geometry.

The earlier three-way comparison remains an assessment of its pinned older builds. Its results must not be silently applied to this newer source.

## 2. Intent and first milestone

Move actual rasterization into the browser while preserving the current spectator's lack of gameplay identity. The first milestone is **an optional WebGL geometry viewer fed by the existing observer's native draw lists**.

The server continues camera selection, culling and animation preparation. The browser draws the resulting indexed geometry. The precise description is therefore **browser GPU rendering with native scene preparation**.

The first deliverable is a live, flat-colour geometry view. It is intentionally a development milestone. It must not be described as a finished textured renderer, a fully autonomous browser scene engine, a higher-performance implementation, or a graphics-free server.

## 3. Approaches considered

| Approach | Benefit | Cost and limitation | Decision |
| --- | --- | --- | --- |
| Native draw commands to WebGL | Reuses observer isolation, free/follow camera, native culling and animation; adds no gameplay peer | Needs a bounded geometry protocol and a browser backend; camera changes still need host scene preparation | Recommended first |
| Renderer-only WASM engine | Could reuse more engine visual behavior and move scene preparation into the browser | Requires a separate lifecycle, authoritative state ingestion, asset handling and reproducible WASM toolchain | Possible later direction |
| New JavaScript world renderer | Can eventually own a browser-local camera and scene | Must recreate world, materials, models, animation and portal behavior; largest visual-divergence risk | Defer |

The cached JKWeb artifact is a full player client. Its normal relay join obtains a gameplay identity, so embedding it and hiding the HUD would not preserve the current spectator contract. The cached artifact is also built from a different engine source pin. No compatible renderer-only WASM implementation was found.

## 4. Proposed architecture

The path is: the existing private observer camera enters its isolated native render pass; a capture sink receives the generated draw lists; the manager validates and retains the latest complete geometry frame; an authenticated browser view decodes it and makes indexed WebGL draws.

### Capture boundary and isolation

`rdCache_DrawRenderList()` already passes vertex and triangle lists into the native graphics backend. Add a sink active only inside the existing observer render scope. It must not capture ordinary player-client or menu rendering.

Retain the snapshot/restore protection around animation caches and render state. Preserve the controls' connection-generation and epoch checks. Capture must never create a player, actor, network peer, inventory, collision body, or gameplay event.

The first milestone may retain the native OpenGL context and run alongside the existing image capture. Removing native rasterization or graphics initialization is a later change with separate acceptance evidence. This choice avoids claiming that the initial geometry path resolves every part of the original GUI/dependency question.

### Proposed wire contract

Use a distinct versioned geometry envelope and an independent inherited frame channel. Do not add geometry to the ordinary 64 KiB control/game IPC and do not reinterpret the existing `JKSV` RGBA payload.

The envelope carries a magic identifier, protocol version, total length, world epoch, control epoch, frame sequence, dimensions, capture age, geometry counts and supported render flags. Every field has an explicit fixed-width little-endian representation. Arrays contain only numeric attributes and indices.

The proposed first profile uses clip-space four-component float32 positions and RGBA8 vertex colours, plus uint32 triangle indices. The native adapter must derive clip-space coordinates from the same projection/depth conventions as the current backend. Existing projected vertex fields must not be mistaken for world-space XYZ.

Never serialize native structs directly: `rdTri` contains a texture pointer, and `D3DVERTEX` layouts vary by build. The first profile carries no textures or resource pointers. Unsupported visual effects are documented as omissions, not silently claimed as equivalent.

Bound the complete capture, all array counts and every allocation. The implementing engineer may choose the exact byte/count caps after inspecting the existing buffer limits, but the protocol and native/manager/browser validators must share those constants. Oversized or invalid frames are discarded as whole units, with a reason visible in diagnostics.

### Delivery, age and backpressure

The native sender remains nonblocking with at most one pending complete capture. The manager retains only the latest valid geometry frame. A slow viewer cannot create an unbounded queue or stall the simulation. Capture age includes time spent waiting for the channel; finishing a delayed transfer does not make old geometry fresh.

Keep world/control epoch validation and the five-second viewer lease. Mode changes, world changes, target departure and channel loss invalidate stale output. Existing input expiry remains 250 ms. Controls and geometry requests use the same authenticated local management boundary as the current spectator.

### Browser behavior

Use a separate canvas and a small direct WebGL backend rather than adding a full scene engine dependency. A WebGL 2 context is the proposed starting point. This is an implementation choice, not a browser-compatibility claim. If context creation fails or the context is lost, show a clear unavailable state and keep the existing image spectator accessible.

The existing image view stays the default. Add an explicit experimental geometry selection; switching display backend must not spawn a second observer or transfer control silently. Retain the existing explicit camera-control ownership behavior.

For the first profile, draw opaque flat-colour triangles with depth testing. Textures, transparency parity, effects, audio and HUD are outside this milestone. Use the same captured camera cadence initially; any higher rate requires measurement and its own decision.

## 5. Evidence required before this milestone is complete

All items below are future checks. None is reported as passed.

| Area | Acceptance evidence |
| --- | --- |
| Actual rendering | Browser makes indexed WebGL draws from numeric geometry; no pixel image is relabeled as geometry |
| Synthetic correctness | Original fixture proves projection, orientation, aspect ratio, depth ordering, winding, colour and index bounds |
| Live world | Existing local stock map and a moving player produce changing geometry at the browser, with frame/epoch evidence |
| Free/follow controls | Free flight works; following survives respawn and returns to free when the selected connection leaves |
| Gameplay isolation | Same game process and player count; no new peer or actor; relevant gameplay state remains unchanged by observation |
| Bounded failure | Malformed lengths, overflow, nonfinite attributes, invalid indices, stale epochs and oversized frames fail cleanly |
| Backpressure and expiry | Slow/disconnected readers cannot stall the engine; memory remains bounded; viewer/input expiry still works |
| Fallback | Unsupported/lost WebGL and geometry-channel failure leave the image spectator usable |
| Publication | Source commit, build provenance, protocol fixture, visual evidence and limitations are saved before completion is claimed |

Unit tests should target protocol boundaries and observable invariants. A live run is still required: mocked browser calls alone cannot prove the geometry appeared or that the engine remained stable.

Use synthetic original geometry in repository fixtures. Reuse the local owned game fixture for live qualification. Do not download an ISO and do not copy retail assets into a public branch.

## 6. Later milestones and honest comparison

Once the first slice is demonstrated, consider texture/material transfer with epoch-scoped resource identities, transparency/effect parity, measurements of frame age/CPU/bytes, and removing native rasterization from the geometry path.

A separate graphics-free startup milestone must demonstrate a live observer with no native GL context and no display server. The first geometry milestone does not meet that criterion.

The current raw image cap represents `640 × 360 × 4 × 5 = 4,608,000` pixel bytes per second before headers. That is a calculation from the current protocol limits, not a measured bandwidth result. Geometry traffic could be smaller or larger depending on the scene. No speed, bandwidth or resource-use advantage is claimed without a matched measurement.

## 7. Work order and decisions left to the builder

A suitable future branch is `feature/browser-spectator-renderer`, based on the recovered source tree. Preserve the published `feature/host-spectator` baseline.

1. Finalize the explicit binary profile, bounds and synthetic fixture.
2. Implement native capture, manager validation and browser rendering as one opt-in vertical slice.
3. Verify projection and isolation with targeted tests, then qualify a live map.
4. Save the evidence and publish a checkpoint before further visual features.

The builder may choose module names, exact field ordering, integer caps, buffer reuse and fixture layout, provided the invariants above hold. Changes to spectator identity, authentication exposure, default rendering mode, inclusion of retail assets, or claims of graphics-free operation are outside those implementation choices.

## 8. Evidence and source map

The project sources below are pinned to GitLab publication commit `d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2`:

- [Spectator protocol](https://gitlab.com/codalilitari/jk-cross-server/-/blob/d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2/docs/SPECTATOR_PROTOCOL.md): current controls, epochs, 640×360/5 fps image framing and isolation.
- [Browser spectator](https://gitlab.com/codalilitari/jk-cross-server/-/blob/d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2/manager/ui/spectator.js): Canvas 2D presentation and polling.
- [Manager spectator](https://gitlab.com/codalilitari/jk-cross-server/-/blob/d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2/manager/spectator.py): independent socket and validation.
- [Native build provenance](https://gitlab.com/codalilitari/jk-cross-server/-/blob/d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2/native/BUILD.json) and [patch](https://gitlab.com/codalilitari/jk-cross-server/-/blob/d62b6b5e6b4cca0cccbf91c1cbe4cc40804336f2/native/crossplay-dedicated.patch): engine base `74e4657c4f1751d09af9ad9e056acb8f41997acb` and observer modifications.
- Inspected local reconstructed engine: `src/Main/jkObserver.c` (`jkObserver_RenderFrame`), `src/Raster/rdCache.c` (`rdCache_DrawRenderList`), `src/Platform/GL/std3D.c` (`std3D_DrawRenderList`, `std3D_AddRenderListVertices`), and `src/types.h` (`rdTri`).
- Cached browser provenance: `runtime/browser-client/client-provenance.json`, release `cloudflare-38`, artifact commit `24dc3876f32eff57c8ca98ef657698d1a30170c7`, engine source `a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c`.
- [Khronos WebGL 2 specification](https://registry.khronos.org/webgl/specs/2.0.0/), inspected 28 October 2026. The served document labels itself an editor's draft; it is an API reference, not a promise of this project's browser compatibility.

No external source supplies the proposed product design. The proposal is an engineering inference from the inspected code and the user's request.

## 9. Planning review

An independent builder check reported no important unanswered questions needed to plan this milestone. This is a review of planning completeness only; it is not implementation evidence, runtime verification, or user approval of the proposed design.



