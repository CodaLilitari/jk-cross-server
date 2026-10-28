# Browser geometry spectator protocol — version 1

This is the optional flat-colour WebGL profile approved for implementation on 28 October 2026. The existing JKSV image protocol remains unchanged and the image view remains the default.

## Control and lifetime

Use private authenticated supervisor IPC type 11, source zero. Add operation 3, a 20-byte little-endian `<5I` request: version=1, operation=3, expected world epoch, expected control epoch, geometry_enabled (0 or 1). Reply with the existing 92-byte spectator reply, operation=3, no roster. Existing result codes retain their meanings. Enabling requires an active ready observer; stale epochs are rejected. Geometry activation does not change the camera, player list, input sequence or control epoch.

Capability bit 16 means a valid independent geometry channel is prepared. Existing capability bits retain their meanings. Enabled requests renew a native 5000-ms geometry lease. Disabled requests stop new captures. World/control changes, observer off and supervisor disconnect stop new geometry capture. An already partially transmitted envelope must finish (or its channel must close), never be truncated on an otherwise reused stream.

The manager invokes operation 3 only for authenticated geometry fetches, at most once per second for the same world/control epochs. Fetches renew the existing five-second viewer lease. Status/input calls renew neither viewer lease. A selected image viewer does not activate geometry capture. Geometry failures must not set the image observer's control/frame error or disconnect game IPC.

## Independent data channel

Manager passes a nonblocking connected AF_UNIX/SOCK_STREAM FD as `OPENJKDF2_SPECTATOR_GEOMETRY_FD`, separate from `OPENJKDF2_SPECTATOR_FD`. Missing/invalid geometry FD disables only geometry. Use CLOEXEC and nonblocking sends with SIGPIPE suppression. Native retains at most one pending complete geometry frame and skips new geometry capture while it is pending. This must not block the RGBA capture path or game simulation.

Every envelope has a 64-byte `<4s15I` header. Offsets are bytes:

| Offset | Field |
| --- | --- |
| 0 | ASCII JKSG |
| 4 | Version = 1 |
| 8, 12 | Width, height (1..640 and 1..360) |
| 16, 20 | Nonzero world epoch, control epoch |
| 24 | Nonzero sequence, matching the RGBA capture sequence for this observer pass |
| 28 | Payload byte length |
| 32 | Flags = 0, the fixed flat-colour profile |
| 36 | Capture age in milliseconds, updated before the first send and increased by the manager before HTTP delivery |
| 40 | Vertex count, 0..65536 |
| 44 | Index count, 0..196608 and divisible by 3 |
| 48, 52, 56, 60 | Reserved = 0 |

Payload contains all vertices followed by all indices. Each vertex is exactly 20 bytes: four little-endian float32 clip coordinates x,y,z,w, then four RGBA8 bytes. All coordinates must be finite; alpha must be 255. Each index is a little-endian uint32 less than vertex count. Payload length must equal `20*vertices + 4*indices` and may not exceed 2,097,152 bytes. Empty geometry requires both counts zero and renders a cleared frame. Reject nonempty unreferenced vertices with zero indices. Header plus payload is at most 2,097,216 bytes.

Do not send pointers, native structs, textures, retail resource files or arbitrary GPU commands. Validate bounds before allocation, then validate all attributes and indices. An invalid or oversized native capture is discarded as a whole. An invalid incoming envelope retires only the geometry channel and preserves the image observer.

## Projection and fixed drawing state

For cached native D3D vertex (x,y,z), width W and height H:

```text
w = 1 / (1 - z)
clip = ((2*x/W - 1)*w, (1 - 2*y/H)*w, (z - 1)*w, w)
```

Reject zero denominator and any nonfinite result. Do not remap native depth to 2*z-1. Extract numeric RGB from packed native colour as (colour>>16)&255, (colour>>8)&255, colour&255; force alpha 255.

The first browser profile uses WebGL 2 indexed TRIANGLES, LESS depth testing, depth writes on, blending off and culling off. Draw every captured solid/normal triangle as opaque. Native sky, transparency and special depth/culling flags are intentionally approximated in this experimental profile; textures and visual parity are not claimed.

## Manager and HTTP boundary

Add `GET /api/spectator/geometry?after=N&world_epoch=W&control_epoch=C`. Query names must be unique and restricted to those three; require both epochs. Reuse existing loopback, same-origin and Bearer authentication. Return 204 if no newer valid capture, 200 with the full JKSG envelope as application/octet-stream, and existing structured error responses for unavailable/stale requests.

Expose additive `geometry` status as `{available:boolean, frame_available:boolean, sequence:uint32, age_ms:number|null, reason:string, profile:"flat-colour-v1"}`. Sequence is zero before a valid frame. Include the same shape in inactive status; older engines are unavailable. Preserve existing status fields and image routes. Freshness requires current epochs, active observer, ready session, valid current state, no geometry error, capture age <=2000ms and no superseding native frame sequence. Include transfer elapsed time and native capture age when the sequence matches; receiving delayed bytes must never make old geometry fresh. Recompute header age when serving. UI also accounts conservatively for elapsed fetch time and rejects stale replies after backend/epoch/session changes.

Use a separate WebGL canvas. Geometry selection is explicit and experimental; switching views preserves camera ownership, clears stale motion/output and does not reconfigure camera mode. On missing/lost WebGL, return to the existing image presentation with an explanatory message. Stop geometry polling when hidden/inactive or after fallback. The image view remains selectable after any geometry failure.

