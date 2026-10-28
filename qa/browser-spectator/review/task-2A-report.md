# Task 2A native geometry capture — DONE

Implemented the exact JKSG v1 protocol without interface changes. The existing image channel, control errors and game IPC are independent from geometry congestion/failure.

## Changed files

Engine source:
- `src/Main/jkObserver.c`: bounded geometry state/serialization, independent socket startup and close, nonblocking partial sends, operation 3, capability 16, 5000 ms opt-in lease, epoch/off/disconnect reset, capture start/end within the observer render pass and sequence shared with RGBA.
- `src/Main/jkObserverGeometry.h`: typed draw-list sink declaration.
- `src/Raster/rdCache.c`: invokes the sink after normal-triangle sorting, before triangle submission.

Project:
- `native/tests/test_spectator_geometry.c`: behavior tests for wire encoding/projection, colours, rebased indices, invalid/oversized batches, operation/epoch validation, lease, congestion and independent socket failure.
- `native/tests/run_spectator_tests.py`: runs geometry tests alongside all existing observer tests.
- `native/rebuild_spectator_geometry.py`: reproducible isolated incremental rebuild using recovered compile/link inputs; writes only new units and output binary to its separate output directory.
- `native/crossplay-dedicated.patch`: regenerated complete patch including new/untracked native files; preserves prior section order to keep review focused. `git apply --reverse --check` succeeds against the reconstructed source.

## Implementation details

Geometry memory is fixed: one 2,097,216-byte complete-envelope buffer plus a 786,432-byte temporary index buffer. Counts and payload arithmetic are checked before accessing input. Every clip coordinate must be finite; numeric RGB is extracted and alpha is forced to 255. Invalid captures discard the complete geometry frame. Line-only batches do not contribute vertices. Empty frames are 64-byte envelopes.

Startup accepts only a connected AF_UNIX SOCK_STREAM descriptor distinct from the image FD, sets nonblocking and CLOEXEC, and allocates fixed buffers. Capture is opt-in, at the existing observer cadence. One pending frame suppresses new geometry capture but does not gate image capture. Sends use MSG_DONTWAIT and MSG_NOSIGNAL with a bounded attempt count. An unsent envelope can be dropped on disable/epoch transition; a partial envelope finishes or its channel closes. Age is refreshed before the first successful send and never rewritten during a partial transfer. Geometry channel failure changes no image observer fields.

Operation 3 is exactly 20 bytes, validates expected epochs and the 0/1 boolean, rejects enable without active ready observation/channel, returns the existing 92-byte reply without roster, and never changes camera/control epoch. Control changes stop capture, and Poll enforces the five-second lease even when no render occurs.

## RED evidence

Command (run before implementation):

```sh
python native/tests/run_spectator_tests.py --source ../jk-native-browser-spectator --build /tmp/jk-native-recovery-build
```

Executed with sandbox escalation because the default sandbox denies local AF_UNIX socketpair. Existing observer tests passed; the added geometry test failed to compile on absent `ObserverGeometry_Startup`, `geometry`, `ObserverGeometry_Begin`, `jkObserver_CaptureGeometry`, `ObserverGeometry_End`, `ObserverGeometry_Flush` and `ObserverGeometry_Shutdown`. This established missing behavior before implementation. Full captured output follows:

```
PASS observer draw preserves sighting, AI, visibility, extra hooks and transform
PASS observer does not consume explosion flashes or alter player palette effects
PASS ordinary renderer retains its pre-existing gameplay effects
PASS startup is opt-in, off, bounded, and roster excludes host/provisional peers
PASS follow reacquires respawn, rejects stale generation, and never moves host
PASS finite bounded inputs, radian angles, replay/epoch checks, and 250 ms motion expiry
PASS saturated socket never blocks, partial frames finish, old epochs stay stale, closure disables camera
PASS exact world/focus/visibility, animation cursors, saber matrices, mesh lighting and frame-counter restoration
PASS bounded snapshot rejects excessive worlds before drawing and remains reusable
PASS actual observer frame supplies yaw/pitch/roll to the engine horizon calculation and restores camera ownership
PASS actual frame retains its capture timestamp through three seconds of backpressure and status reports age 3000 ms
PASS subsequent free-camera rotation refreshes horizon offsets and roll
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c: In function ‘main’:
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:12:5: error: implicit declaration of function ‘ObserverGeometry_Startup’ [-Werror=implicit-function-declaration]
   12 |     ObserverGeometry_Startup(-1);assert(geometry.fd==sockets[0]);
      |     ^~~~~~~~~~~~~~~~~~~~~~~~
In file included from /workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:2:
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:12:41: error: ‘geometry’ undeclared (first use in this function)
   12 |     ObserverGeometry_Startup(-1);assert(geometry.fd==sockets[0]);
      |                                         ^~~~~~~~
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:12:41: note: each undeclared identifier is reported only once for each function it appears in
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:18:5: error: implicit declaration of function ‘ObserverGeometry_Begin’ [-Werror=implicit-function-declaration]
   18 |     ObserverGeometry_Begin(now);
      |     ^~~~~~~~~~~~~~~~~~~~~~
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:19:5: error: implicit declaration of function ‘jkObserver_CaptureGeometry’ [-Werror=implicit-function-declaration]
   19 |     jkObserver_CaptureGeometry(v,3,&t,1,NULL,0);
      |     ^~~~~~~~~~~~~~~~~~~~~~~~~~
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:21:5: error: implicit declaration of function ‘ObserverGeometry_End’ [-Werror=implicit-function-declaration]
   21 |     ObserverGeometry_End(now,7,8,9,1);
      |     ^~~~~~~~~~~~~~~~~~~~
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:30:14: error: implicit declaration of function ‘ObserverGeometry_Flush’; did you mean ‘Observer_Flush’? [-Werror=implicit-function-declaration]
   30 |     now+=123;ObserverGeometry_Flush(now);uint8_t received[512];assert(recv(sockets[1],received,sizeof(received),0)==208);
      |              ^~~~~~~~~~~~~~~~~~~~~~
      |              Observer_Flush
/workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:48:5: error: implicit declaration of function ‘ObserverGeometry_Shutdown’ [-Werror=implicit-function-declaration]
   48 |     ObserverGeometry_Shutdown();return 0;
      |     ^~~~~~~~~~~~~~~~~~~~~~~~~
cc1: some warnings being treated as errors
```

## GREEN evidence

The same command passed after implementation, including the final portability guard/header inclusion. Output:

```
PASS observer draw preserves sighting, AI, visibility, extra hooks and transform
PASS observer does not consume explosion flashes or alter player palette effects
PASS ordinary renderer retains its pre-existing gameplay effects
PASS startup is opt-in, off, bounded, and roster excludes host/provisional peers
PASS follow reacquires respawn, rejects stale generation, and never moves host
PASS finite bounded inputs, radian angles, replay/epoch checks, and 250 ms motion expiry
PASS saturated socket never blocks, partial frames finish, old epochs stay stale, closure disables camera
PASS exact world/focus/visibility, animation cursors, saber matrices, mesh lighting and frame-counter restoration
PASS bounded snapshot rejects excessive worlds before drawing and remains reusable
PASS actual observer frame supplies yaw/pitch/roll to the engine horizon calculation and restores camera ownership
PASS actual frame retains its capture timestamp through three seconds of backpressure and status reports age 3000 ms
PASS subsequent free-camera rotation refreshes horizon offsets and roll
PASS hand-derived projection, RGB extraction, index rebasing and capture age
PASS malformed and oversized batches discard whole capture
PASS operation 3 validates epochs and boolean, advertises capability, renews lease without changing control epoch
PASS congestion skips capture; partial envelope finishes across epoch changes; lease expiry and disable discard unsent frames
PASS geometry peer failure preserves image channel and observer control
```

## Isolated build

```sh
python native/rebuild_spectator_geometry.py --source ../jk-native-browser-spectator --baseline-build /tmp/jk-native-recovery-build --output ../jk-native-browser-spectator-build
```

Recompiled `jkObserver.c` and `rdCache.c`; linked their replacement objects against existing baseline objects and local dependency libraries. Link dependency-file writing was removed, and output object/binary paths are isolated. `/tmp/jk-native-recovery` and `/tmp/jk-native-recovery-build` were not edited. The complete compiler/link argument vectors are saved in `../jk-native-browser-spectator-build/commands.json`.

Output binary: `/workspace/scratch/55e850edc256/jk-native-browser-spectator-build/openjkdf2`

SHA-256: `d859b790d4106506e70bf8b8d083b050c342f21095d2362a1c16b0a019b27e03`

## Remaining integration qualification

Root owns native package manifests, commits and publication. This task proves native synthetic behavior and successful build; it does not claim live browser rendering or live gameplay isolation qualification. The integrated live run should verify geometry/RGBA sequence agreement, moving-world geometry, image delivery during geometry backpressure, and the browser view. The flat-colour profile intentionally approximates native sky, transparency and special depth/culling state as specified. No assets or dependencies were downloaded.


## Fix round 1 — native capture diagnostics and isolated linker correction

Important review finding addressed: malformed/oversized native captures previously set only an invalid bit and were silently discarded. The native adapter now retains a finite rejection category for each discarded capture and writes a bounded stderr diagnostic: `size-limit`, `missing-data`, `nonfinite-projection`, or `invalid-index`. Logging occurs once at capture end and is limited independently to one line per reason per 5000 ms (at most four lines per five-second window); the fixed limiter state survives new captures and lease transitions. A valid later capture resumes ordinary exact JKSG output. No wire fields changed; image/control status is untouched. Minor n-gon portability finding remains deferred as requested by root.

Changed files in this round:
- Engine `src/Main/jkObserver.c`: finite reason selection and bounded stderr logging.
- Project `native/tests/test_spectator_geometry.c`: actual stderr capture verifies distinguishable reasons, 100 repeated rejected captures, the 4999/5000 ms rate boundary, valid recovery on the real socketpair, and byte-for-byte unchanged image/control state.
- Project `native/rebuild_spectator_geometry.py`: root identified a literal escaped dollar in the original binary RUNPATH. The helper now removes shell escaping only from linker RPATH arguments, matching existing `package_native.py`; subprocess still receives an argument vector with no shell evaluation.
- Project `native/crossplay-dedicated.patch`: regenerated complete 24-section native patch in prior section order, including untracked/new native files.

Pre-edit files were captured under `/workspace/scratch/55e850edc256/task-2A-fix-1-before`. The exact scoped source/test/helper/patch diff is `task-2A-fix-1.diff` beside this report. No commits were created. `/tmp/jk-native-recovery` and `/tmp/jk-native-recovery-build` were not edited; the in-use `jk-native-browser-spectator-build` binary was not overwritten.

### RED: behavior regression before native implementation

Command (with `require_escalated` because local AF_UNIX socketpairs require it):

```sh
python native/tests/run_spectator_tests.py --source ../jk-native-browser-spectator --build /tmp/jk-native-recovery-build
```

Exit status 1. The real capture succeeded/recovered but stderr lacked the oversized diagnostic, causing the intended assertion failure:

```
PASS observer draw preserves sighting, AI, visibility, extra hooks and transform
PASS observer does not consume explosion flashes or alter player palette effects
PASS ordinary renderer retains its pre-existing gameplay effects
PASS startup is opt-in, off, bounded, and roster excludes host/provisional peers
PASS follow reacquires respawn, rejects stale generation, and never moves host
PASS finite bounded inputs, radian angles, replay/epoch checks, and 250 ms motion expiry
PASS saturated socket never blocks, partial frames finish, old epochs stay stale, closure disables camera
PASS exact world/focus/visibility, animation cursors, saber matrices, mesh lighting and frame-counter restoration
PASS bounded snapshot rejects excessive worlds before drawing and remains reusable
PASS actual observer frame supplies yaw/pitch/roll to the engine horizon calculation and restores camera ownership
PASS actual frame retains its capture timestamp through three seconds of backpressure and status reports age 3000 ms
PASS subsequent free-camera rotation refreshes horizon offsets and roll
test_spectator_geometry: /workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:77: main: Assertion `strstr(messages,"size-limit") && "oversized capture needs a diagnostic reason"' failed.
test_spectator_geometry failed with exit status -6
```

### Intermediate verification and test harness correction

The first run after implementation failed the diagnostic byte-count assertion because `ftell` cached the stdio position after reading the same file via another duplicated descriptor. The test now queries the real shared descriptor offset with `lseek`. This was a test capture measurement issue, not a change to native rate limiting. Same command, exit status 1, complete output:

```
PASS observer draw preserves sighting, AI, visibility, extra hooks and transform
PASS observer does not consume explosion flashes or alter player palette effects
PASS ordinary renderer retains its pre-existing gameplay effects
PASS startup is opt-in, off, bounded, and roster excludes host/provisional peers
PASS follow reacquires respawn, rejects stale generation, and never moves host
PASS finite bounded inputs, radian angles, replay/epoch checks, and 250 ms motion expiry
PASS saturated socket never blocks, partial frames finish, old epochs stay stale, closure disables camera
PASS exact world/focus/visibility, animation cursors, saber matrices, mesh lighting and frame-counter restoration
PASS bounded snapshot rejects excessive worlds before drawing and remains reusable
PASS actual observer frame supplies yaw/pitch/roll to the engine horizon calculation and restores camera ownership
PASS actual frame retains its capture timestamp through three seconds of backpressure and status reports age 3000 ms
PASS subsequent free-camera rotation refreshes horizon offsets and roll
test_spectator_geometry: /workspace/scratch/55e850edc256/jk-browser-spectator/native/tests/test_spectator_geometry.c:80: main: Assertion `lines==4 && burstBytes==firstBytes && renewedBytes>burstBytes' failed.
test_spectator_geometry failed with exit status -6
```

### GREEN: complete native observer suite

Same command with local-socket escalation, exit status 0. No runner change was needed because the existing runner already includes the geometry test and every observer suite. Complete output:

```
PASS observer draw preserves sighting, AI, visibility, extra hooks and transform
PASS observer does not consume explosion flashes or alter player palette effects
PASS ordinary renderer retains its pre-existing gameplay effects
PASS startup is opt-in, off, bounded, and roster excludes host/provisional peers
PASS follow reacquires respawn, rejects stale generation, and never moves host
PASS finite bounded inputs, radian angles, replay/epoch checks, and 250 ms motion expiry
PASS saturated socket never blocks, partial frames finish, old epochs stay stale, closure disables camera
PASS exact world/focus/visibility, animation cursors, saber matrices, mesh lighting and frame-counter restoration
PASS bounded snapshot rejects excessive worlds before drawing and remains reusable
PASS actual observer frame supplies yaw/pitch/roll to the engine horizon calculation and restores camera ownership
PASS actual frame retains its capture timestamp through three seconds of backpressure and status reports age 3000 ms
PASS subsequent free-camera rotation refreshes horizon offsets and roll
PASS hand-derived projection, RGB extraction, index rebasing and capture age
PASS malformed and oversized batches discard whole capture with distinct bounded diagnostic reasons
PASS rejection logging is rate limited across 100 captures and renews after five seconds
PASS valid capture recovers after rejection without changing image/control status or adding diagnostics
PASS operation 3 validates epochs and boolean, advertises capability, renews lease without changing control epoch
PASS congestion skips capture; partial envelope finishes across epoch changes; lease expiry and disable discard unsent frames
PASS geometry peer failure preserves image channel and observer control
```

### Isolated rebuild and artifact validation

```sh
python native/rebuild_spectator_geometry.py --source ../jk-native-browser-spectator --baseline-build /tmp/jk-native-recovery-build --output ../jk-native-browser-spectator-fixed-build
```

Exit status 0, complete output:

```
/workspace/scratch/55e850edc256/jk-native-browser-spectator-fixed-build/openjkdf2
```

Original artifact evidence before helper correction:

```sh
readelf -d ../jk-native-browser-spectator-build/openjkdf2 | rg 'RPATH|RUNPATH'
```

```text
 0x000000000000001d (RUNPATH)            Library runpath: [\$ORIGIN]
```

Corrected artifact validation:

```sh
readelf -d ../jk-native-browser-spectator-fixed-build/openjkdf2 | rg 'RPATH|RUNPATH'
sha256sum ../jk-native-browser-spectator-fixed-build/openjkdf2 native/crossplay-dedicated.patch
git diff --check
```

Complete output (`git diff --check` emitted nothing, exit status 0):

```text
 0x000000000000001d (RUNPATH)            Library runpath: [$ORIGIN]
ef29783aae3cf33cc2bddad1a5dda0ff077f79bdd90f7f5b862d54ef747331da  ../jk-native-browser-spectator-fixed-build/openjkdf2
26ea7f659236222c3a8f6abaf8f6967109e21a0dd1fe5b1bd39f8ddf65de6734  native/crossplay-dedicated.patch
```

The new `commands.json` records the exact direct linker argument `-Wl,-rpath,$ORIGIN`. It is ready for root-owned packaging.

Patch regeneration method: extract ordered paths from existing `diff --git` section headers, obtain tracked changes using `git diff --name-only HEAD` and new files using `git ls-files --others --exclude-standard`, append any missing paths, then concatenate `git diff --binary HEAD -- PATH` for tracked files and `git diff --no-index --binary -- /dev/null PATH` for new files in that order. All commands run in the reconstructed engine source tree. The complete regenerated patch was verified with:

```sh
git -C ../jk-native-browser-spectator apply --reverse --check "$PWD/native/crossplay-dedicated.patch"
```

Exit status 0. Regeneration/check output:

```text
PASS complete patch regenerated: 24 sections, prior section order preserved, reverse apply check passed
```

Root owns subsequent final review, live qualification, package manifests and publication. This fix provides full native-suite evidence and the corrected isolated native artifact; it adds no claims about browser visual parity or live gameplay isolation.
