# Task 2B independent review

## Verdicts

- **Specification compliance: changes required.** The implementation meets the reviewed authorization, bounded envelope, finite attribute, transport separation, backward compatibility and ordinary freshness requirements, but a normal stale-epoch operation-3 reply can permanently disable geometry for the newly current control epoch.
- **Code quality: changes required.** One Important state-transition defect was confirmed. No Critical or Minor findings were identified in this focused review.

## Important finding

### I1 — Stale activation rejection poisons the newly current epoch

**Location:** `manager/spectator.py:360–364` (interaction with epoch-reset logic at lines 192–197 and the availability gate at lines 343–344).

**Trigger:** A geometry fetch passes the manager's initial epoch check, then the native observer changes control epoch before processing operation 3. A follow-target departure, for example, can legitimately move the observer into free mode with a new control epoch. The native reply returns result 2 and reports that new current epoch.

**Behavior and impact:** `_apply(reply)` correctly installs the new epoch and clears obsolete geometry failure state. Immediately afterward, the generic nonzero-result branch sets `_geometry_control_error = "Geometry activation was rejected."` against that newly installed epoch. The request returns 409, but a subsequent authenticated fetch with the correct new epoch fails the availability gate with 503 before sending operation 3. Status also reports geometry unavailable. Ordinary status refreshes for the same epoch cannot clear this error; another camera/epoch change or session restart is needed. This turns an expected stale-control race into a persistent geometry outage and can force the browser into fallback unnecessarily. Image availability is preserved.

**Evidence:** A narrow in-memory controller probe used an initially active `(world=1, control=1)` observer and a typed operation-3 reply with `result=2`, `control_epoch=2`, otherwise valid active state. The first request returned 409. A second request for `(1,2)` returned 503, activation call count remained 1, current control epoch was 2, and image availability remained true. No product files were modified by the probe and no broad tests were run.

**Fix:** Handle result 2 as a retryable epoch conflict after applying the authoritative reply, without persisting a geometry control failure on the newly current epoch. Keep obsolete geometry invalidated and return 409. Preserve persistent diagnostics for actual unsupported/malformed/denied geometry operations as appropriate. Add a focused behavior regression in which operation 3 observes a control transition and a subsequent request using the new epochs successfully attempts activation.

## Reviewed boundaries

The HTTP route uses the existing loopback, host, origin and Bearer middleware; query fields are restricted, unique and bounded uint32 values, with both epochs required. The typed IPC request remains source zero, operation 3, exactly 20 bytes; its reply remains the existing 92-byte no-roster shape. The capability decoder permits the additive geometry bit while retaining existing bit meanings.

The geometry channel validates the fixed header and payload bounds before payload reception, checks count consistency, finite clip attributes, opaque alpha and index limits, and retains only a validated complete current-epoch frame. Current frame delivery includes native capture age, elapsed transfer/retention time, matching native sequence age, superseding native sequence rejection and final outgoing age recomputation. Epoch changes clear obsolete geometry. No authorization bypass, unbounded payload allocation or malformed-payload acceptance was found in the inspected path.

The inherited socket and reader are separate from image capture, with cleanup on spawn/session close. Geometry parsing and activation failures use separate error fields, and malformed spectator replies do not tear down shared game IPC. Older image-only engines are capability-gated before operation 3. The existing image route and image default remain compatible with this manager change.

The controller lock serializes activation against normal control and polling requests; repeated successful fetches are limited to one activation request per second for the same epochs. Status and input do not activate geometry or renew its lease. The deadline is checked before awaiting activation and renewed after its reply. I considered the possibility of a response arriving after the prior deadline. This is not reported as a separate defect: the already authenticated in-flight fetch is viewer activity, and the frozen contract does not explicitly anchor renewal to request admission rather than completion. Delivery still checks current ready session, active observer, state freshness and frame age through `_geometry_frame()`. No additional actionable renewal/lifetime defect is claimed by this review.

## Intentional tradeoffs and limits

Retiring a malformed geometry transport until session restart, retaining a real geometry control failure until an epoch change, and preserving image fallback are deliberate bounded failure policies described by the task report. I1 is different: result 2 represents a routine epoch conflict, and the error is attached after the very epoch change intended to recover it.

Flat-colour opaque rendering, no textures or visual-parity claim, and retained native scene preparation are approved milestone limitations, not findings. This review does not claim live rendering, native lease behavior, browser integration or packaged-binary correctness. Root owns full-suite integration, live qualification and packaging.

## Review scope

Read the task brief, implementation report and review diff, the frozen geometry protocol and approved design, and focused surrounding manager/IPC/test code. Reviewed independently without editing product files, creating commits, spawning agents, or running broad tests. The only execution beyond reads was the narrow deterministic controller probe described above.

## Scoped re-review — fix round 1

**I1: ADDRESSED.** Reviewed `task-2B-fix-1.diff` and the appended fix-round report only. The result-2 branch now clears obsolete geometry and returns HTTP 409 after applying the authoritative reply, without setting `_geometry_control_error` on the new epoch. Consequently the new-epoch request can pass the availability gate and issue a fresh activation. Other nonzero results continue to retain the independent geometry denial diagnostic and return 503.

The added HTTP/subprocess regression exercises the actual reported transition, including a previously valid capture, native control-epoch advancement during operation 3, stale-frame invalidation, an additional activation on retry, new-epoch geometry delivery and image/IPC continuity. The strengthened denial test verifies that ordinary denials remain persistent across refresh and do not damage image delivery. The task report records the expected pre-fix HTTP 503 failure and a 54/54 passing focused regression run after the fix; this reviewer did not rerun tests.

**New Critical/Important issues introduced by this fix: none found.** The manager review's blocking finding is resolved; specification and code-quality verdicts are approved for the reviewed manager scope. This scoped approval does not claim completion of root-owned full-suite integration, live qualification or final artifact packaging. No broader re-review, product edits or test execution were performed.
