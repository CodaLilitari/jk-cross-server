# Task 2A independent native review

## Verdicts

**Specification: changes requested for the missing native capture-rejection diagnostic.** The exact JKSG v1 serializer, operation 3, lease/epoch behavior, independent socket handling and capture boundary otherwise match the native task contract on the reconstructed Linux build.

**Code quality: changes requested for a concrete conditional-build regression.** No Critical findings. One Important specification finding and one Minor portability finding follow. No product files were edited, no tests/builds were rerun, and no commits were made. Reported GREEN/build evidence was read, not independently reproduced. Full/live qualification and packaging remain root-owned.

## Important — native rejected captures have no diagnostic reason

Location: `/workspace/scratch/55e850edc256/jk-native-browser-spectator/src/Main/jkObserver.c:190` (invalid label), with silent discard at line 200 and reset at line 155.

Trigger: a capture exceeds the aggregate vertex/index/payload bounds, contains a nonfinite projection/zero denominator, or includes an invalid index. These are actual supported rejection paths; the new native test exercises several of them at `native/tests/test_spectator_geometry.c:37`.

Impact: the entire geometry frame is correctly discarded, but the rejection is neither logged nor retained with a reason. The next capture resets the only invalid bit. A repeatedly oversized live scene therefore yields no new geometry with no diagnostic distinguishing size limits from bad projected coordinates or indices. This misses the approved design's explicit requirement: “Oversized or invalid frames are discarded as whole units, with a reason visible in diagnostics.” The exact wire protocol does not provide a field for this, so no protocol extension is required.

Fix: record a small native rejection reason at each failing validation branch and expose it through bounded/rate-limited native logging (or another existing diagnostic facility). Preserve independent image/control status. Verify at least oversized and malformed cases produce distinguishable diagnostics without unbounded output at capture cadence.

## Minor — unconditional triangle type breaks the existing n-gon build profile

Location: `/workspace/scratch/55e850edc256/jk-native-browser-spectator/src/Main/jkObserverGeometry.h:5` and `/workspace/scratch/55e850edc256/jk-native-browser-spectator/src/Main/jkObserver.c:158`.

Trigger: compile the existing TARGET_TWL configuration. `src/engine_config.h:395` enables RDCACHE_RENDER_NGONS for that target, and `src/types.h:708` defines rdTri only when RDCACHE_RENDER_NGONS is absent. The new header is included unconditionally by rdCache.c, and its function declaration references the absent type. The function definition also references it outside the JK_OBSERVER_SUPPORTED body guard.

Impact: this previously valid configuration fails compilation with an unknown rdTri type even though geometry observation is unavailable there. The current Linux milestone build is unaffected; this is a conditional-build regression, not a claim that TWL geometry support is required.

Fix: guard the triangle-specific public declaration and complete function definition with `#ifndef RDCACHE_RENDER_NGONS`, matching the existing guard around the rdCache capture call. A focused compile/preprocessor check is sufficient; no alternate-platform runtime qualification is needed.

## Reviewed behavior with no further findings

- The serializer follows the specified projection exactly, checks all four serialized float32 coordinates for finiteness, extracts numeric RGB, forces alpha 255, writes little-endian fields explicitly, and rebases each batch's indices against accumulated vertices. Counts constrain arithmetic before payload writes; malformed input discards the whole capture. Empty captures emit the legal 64-byte envelope.
- The geometry channel validates connected AF_UNIX/SOCK_STREAM descriptors, rejects the image FD, sets nonblocking/CLOEXEC, uses bounded MSG_DONTWAIT/MSG_NOSIGNAL sends, and owns fixed buffers. Geometry failure closes only geometry state. A pending geometry frame suppresses geometry capture without gating the RGBA path.
- Disable, control/world transitions and supervisor disconnect stop new captures. Unstarted frames may be dropped; partial frames remain intact until completion or channel closure. Poll expires the five-second lease even without rendering. Initial send updates capture age; partial sends do not rewrite an already transmitted header.
- Operation 3 validates its exact 20-byte shape, epochs and boolean; enabling requires a ready active observer/channel; the 92-byte response has no roster and does not change input/control epochs. Capability 16 reflects prepared geometry-channel state.
- Capture starts inside the existing read-only observer scope, and the sink additionally checks observer.renderPass. Input arrays are read through const pointers. The added hook does not create gameplay identities or alter the existing renderer snapshot/restore behavior. End-of-capture uses the next RGBA sequence, and readback failure discards geometry too.
- The added tests cover hand-derived projection/colour/index rebasing, invalid batches, epoch/operation validation, lease expiry, congestion, partial-frame preservation and independent failure. They do not establish live geometry appearance or gameplay isolation; the implementation report accurately leaves those to integration qualification.

## Intentional tradeoffs, not defects

The image remains the default, native scene preparation and GL rendering remain active, and geometry shares the observer cadence and successful RGBA capture sequence. Opaque flat colours, ignored textures/blending/culling/special depth flags, and approximate sky are approved first-profile limitations. No graphics-free or performance advantage is inferred. Finishing a stale partial envelope across epoch changes is explicitly required for stream framing; downstream epoch/age validation must discard stale output.

## Scoped re-review — fix round 1

Reviewed `task-2A-fix-1.diff` and the appended fix-round report only. No product edits, builds or test reruns. The evidence below distinguishes source review from reported execution.

**Important native rejection diagnostics: ADDRESSED.** The invalid marker now records one of four finite reasons: size limit, missing data, nonfinite projection or invalid index. Capture end logs the selected reason; fixed per-reason timestamps and a bitmask suppress repeats for 5000 ms across capture/lease transitions. The validation paths retain whole-frame rejection and do not modify image/control state. The regression test captures actual stderr, checks all four categories, suppresses a 100-capture burst, verifies the 4999/5000 ms boundary, then confirms a valid frame recovers and image/control state remains byte-for-byte unchanged. The report supplies the expected RED assertion and 19 GREEN PASS results.

**Escaped linker RUNPATH correction: ADDRESSED.** The helper normalizes escaped dollar signs only within `-Wl,-rpath,` arguments before passing the argument vector directly to subprocess. This fixes the identified literal backslash without introducing shell evaluation or changing unrelated arguments. The supplied rebuilt-artifact evidence reports RUNPATH `[$ORIGIN]` and records the corrected linker argument. That evidence was read, not independently rerun.

**Fix-round specification verdict: PASS. Fix-round code-quality verdict: PASS.** No new Critical or Important breakage found in this fix. The earlier Minor n-gon portability finding remains explicitly deferred to final branch review; it was neither reopened nor marked resolved here. Root retains responsibility for final corrected-binary packaging and full/live qualification.
