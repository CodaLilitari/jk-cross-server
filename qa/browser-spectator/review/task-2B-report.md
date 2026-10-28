# Task 2B implementation report

## Scope and implementation

Implemented the frozen `docs/SPECTATOR_GEOMETRY_PROTOCOL.md` contract without changing its fields or bounds. No native source, native patch/binary, browser JavaScript/HTML/CSS, Git staging or commits were changed by this worker.

Owned changes:

- `manager/spectator_geometry.py`: independent nonblocking Unix socketpair, native environment descriptor, independent reader task and retirement, strict 64-byte JKSG validation before payload allocation, finite float32 attributes/opaque alpha/uint32 index validation, bounded bytearray reception and retention of only the latest complete valid current-epoch frame. The first received byte starts the transfer timer; waiting for a new envelope does not age a future capture. Native header age and all remaining transfer elapsed time contribute to `captured_at`.
- `manager/spectator.py`: prepares, transfers and closes the geometry descriptor alongside the existing image descriptor. Maintains separate geometry transport/control failures, geometry renewal timestamps and the agreed additive status shape. Epoch changes, disconnect and observer-off clear obsolete geometry. Only the geometry fetch path calls operation 3; repeated fetches within one second for the same epochs reuse activation. Authenticated geometry fetches renew the existing five-second viewer deadline; status and input do not. Image fetches retain their previous behavior.
- Geometry serving requires a current authenticated observer, current epochs, a ready session, prepared geometry capability, valid current native state, an unexpired viewer lease, no geometry failure, no superseding native sequence and capture age at most 2000 ms. Matching native frame age plus elapsed time since the native reply also bounds freshness. The HTTP envelope age is recomputed immediately before returning the complete header and payload.
- `manager/runtime.py`: async `spectator_geometry(**query)` entry point and removal of inherited geometry descriptor environment values before engine/bot launch preparation.
- `manager/admin.py`: allows `spectator-geometry.js` and adds `GET /api/spectator/geometry`; both epochs are mandatory, query names are unique and restricted, counters are uint32, and the existing loopback/origin/Bearer guard is reused. Returns full JKSG bytes as `application/octet-stream`, 204 for no newer valid capture and structured errors for invalid, stale or unavailable requests.
- `web_gateway/ipc.py`: accepts capability bit 16 and typed operation 3 as exactly `<5I` (20 bytes), with strictly integer 0/1 activation, 92-byte reply and no roster. No gameplay framing or maximum IPC size changed.
- `tests/test_runtime_display.py`: extended the existing authored engine fixture with a real inherited geometry descriptor, independent synthetic triangle/empty frames, controlled fragmentation/delay/corruption and operation-3 behavior. It does not import or duplicate the production validator.
- `tests/test_spectator.py`: extracted existing HTTP setup/helpers to `SpectatorHTTPFixture` so geometry tests reuse actual manager startup, private IPC, process supervision and HTTP authorization without duplicating existing test cases.
- `tests/test_spectator_geometry.py`: 16 tests, including 15 real subprocess/socket/HTTP cases and one direct compatibility check against the original shared `.jksg` fixture.

## RED evidence

Commands below ran with local-socket permission, before the corresponding implementation/fix:

1. `python -m unittest tests.test_spectator_geometry -v`
   - Saved as `task-2B-red.log`.
   - **9 tests failed**, all because the geometry HTTP endpoint returned 404 instead of the required 204/400/503/401 behavior. The framing, lease, authorization, age/epoch, independent failure and old-engine tests were authored first.
2. `python -m unittest tests.test_spectator_geometry.SpectatorGeometryTests.test_future_epoch_capture_cannot_poison_current_stream -v`
   - Saved as `task-2B-epoch-red.log`.
   - **1 failure**: a future-epoch frame could prevent a later valid current-epoch frame from reaching HTTP 200. Fixed by rejecting mismatched authoritative epochs before retention, rather than sorting arbitrary incoming epochs into the latest-frame slot.
3. `python -m unittest tests.test_spectator_geometry.SpectatorGeometryTests.test_geometry_native_denial_reports_reason_independently -v`
   - Saved as `task-2B-denial-red.log`.
   - **1 failure**: an explicit native geometry denial returned HTTP 503 but left geometry status available. Fixed by retaining an independent geometry control error and retiring cached geometry, while keeping image availability intact.

## GREEN and regression evidence

- Initial vertical slice: `python -m unittest tests.test_spectator_geometry -v`: **9 tests passed in 11.785 s** (`task-2B-green.log`).
- Expanded geometry plus the rendering-disabled regression: `python -m unittest tests.test_spectator_geometry tests.test_spectator.SpectatorManagerTests.test_disabled_rendering_passes_no_fd_and_explains_restart -v`: **16 tests passed in 30.640 s** (`task-2B-geometry-green.log`).
- Shared original protocol fixture: `python -m unittest tests.test_spectator_geometry.GeometrySharedFixtureTests -v`: **1 test passed** (`task-2B-shared-fixture-green.log`). Verifies dimensions, epochs, sequence, counts, exact size and all attributes/indices from the same original envelope the browser tests consume.
- The first combined focused run (`tests.test_spectator_geometry tests.test_spectator tests.test_runtime_display`) completed **50 tests with one error**, `test_disabled_rendering_passes_no_fd_and_explains_restart` (`task-2B-focused-green.log`). This was a fixture-only typo from a broad string replacement: a nonempty default argument accidentally made absent image-FD environment values truthy. The fixture was corrected, the exact failing regression passed in the expanded run above, and the existing spectator/runtime groups were rerun separately as recorded below. This error is not omitted or characterized as a passing run.
- Existing image spectator and runtime/display regressions rerun: `python -m unittest tests.test_spectator tests.test_runtime_display -v`: **37 tests passed in 59.484 s** (`task-2B-regression-green.log`), including the corrected rendering-disabled case.
- `git diff --check` on all task-owned production/test paths: no whitespace errors.

The root worker owns the final full-suite integration run after all workers finish, as required by the task brief. Native 5000-ms geometry lease implementation, live capture and browser rendering qualification are outside this worker's scope; the subprocess fixture checks manager renewals, framing and observable HTTP invariants rather than claiming native/rendering evidence.

## Self-review

- Geometry transport faults, malformed replies, unsupported operation and explicit geometry denials do not set `_control_error` or `_frame_error` and do not disconnect shared game IPC. Real tests continue image delivery after malformed index/header/attributes and after operation errors.
- An older image-only engine exposes no capability bit 16; a geometry fetch returns unavailable without sending operation 3, while its image frame route stays usable.
- Tests exercise alpha corruption, NaN coordinates, out-of-range indices, oversized byte/count headers, nonzero reserved fields, stale capture age, delayed payload transfer, superseding native sequence, future epoch rejection, invalid current session, stale query epochs, expired viewer lease, unauthorized/cross-origin calls and duplicate/unknown query fields.
- Framing tests inspect the actual complete HTTP envelope, age increase, empty geometry and latest-only sequence filtering. The shared fixture independently catches field/layout disagreement with browser fixtures.
- The geometry socket is nonblocking and noninheritable in the manager; the child end is closed after spawn, and stopping the session closes the parent and joins the reader task. Both image and geometry environment variables are removed before deciding whether rendering is enabled.
- Geometry operation errors remain unavailable until a control/world epoch change resets their diagnostic. A malformed geometry channel remains retired until session restart. These are deliberate bounded fallbacks; image capture/control remain usable.
- The canonical shared geometry contract was not modified. No dependency/media downloads, external service operations, commits or subagents were used.

## Review fix round 1 — I1 stale activation epoch

The reviewed stale-epoch bug is fixed with a separate result-2 branch after applying the authoritative native reply. A result-2 activation rejects the request with HTTP 409 and clears obsolete geometry, without assigning a persistent geometry control error to the new epoch. Other nonzero native results retain the existing independent geometry denial diagnostic and HTTP 503 behavior. No viewer-lease timing changes were made.

The subprocess fixture now simulates a follow-target departure exactly while processing operation 3: it advances the control epoch, switches to free mode, clears the old capture sequence and returns the protocol's stale-epoch result. The new authenticated HTTP regression begins with a valid geometry capture, triggers this transition, verifies 409 and invalidation of the old capture, retries using the authoritative new epoch, checks that another operation 3 actually reaches the subprocess, receives new-epoch geometry, and confirms image delivery and connected IPC. The native-denial regression additionally checks that its diagnostic survives a normal status refresh, another geometry fetch remains 503 without further activation, and image delivery remains usable.

Production change: `manager/spectator.py`. Fixture/test changes: `tests/test_runtime_display.py`, `tests/test_spectator_geometry.py`. The exact diff from this fix round's starting state is `task-2B-fix-1.diff`; it excludes prior task implementation changes. No commits, subagents, protocol changes or changes outside manager-owned production/test paths. Root retains full-suite integration and live-server restart responsibility.

### RED

Command (with local-socket permission):

```text
python -m unittest tests.test_spectator_geometry.SpectatorGeometryTests.test_stale_activation_epoch_can_retry_after_follow_target_departure -v
```

Full output: `task-2B-fix-1-red.log`. Executed before production modification. Relevant output:

```text
self.assertEqual((await self.geometry(updated))[0], 204)
AssertionError: 503 != 204
Ran 1 test in 1.130s
FAILED (failures=1)
```

### GREEN and regression verification

Command (with local-socket permission):

```text
python -m unittest tests.test_spectator_geometry tests.test_spectator tests.test_runtime_display -v
```

Full output: `task-2B-fix-1-green.log`. Output summary:

```text
Ran 54 tests in 92.775s
OK
```

All 54 tests passed, including the new stale-activation regression, the strengthened independent native-denial regression, all geometry framing/freshness/authentication tests, existing image spectator tests, and runtime/display subprocess tests.

Whitespace command:

```text
git diff --check -- manager/spectator.py tests/test_runtime_display.py tests/test_spectator_geometry.py
```

Exit status 0, no output. The focused test run also exited 0. No additional actionable lease-await finding was addressed because the reviewer explicitly ruled it out.
