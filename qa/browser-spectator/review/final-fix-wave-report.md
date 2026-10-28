# Final review fix wave — both concrete findings resolved

Review base: `576f768ca1328d9d7a0dd917942a1f09aa9f6915`. This single focused wave addresses both Minor findings in `whole-branch-review.md`. No commits, package replacement, full manager rerun, or full alternate-platform build occurred. Root owns documentation corrections, release/SHA manifests, commits and publication.

## Changes

1. `manager/ui/spectator.js` retains its latest geometry-sequence guard and also rejects a geometry envelope older than the available authoritative image sequence in the current status. Existing epoch/session/backend checks still run first.
2. `tests/test_spectator_geometry_ui.js` adds a mounted-controller delayed-response regression: geometry request starts, status becomes `{geometry:{available:true,frame_available:false,sequence:0,age_ms:null,...},frame:{available:true,sequence:10,age_ms:0}}`, then sequence 9 arrives. Assertions cover no indexed draw, retained waiting text and visible waiting overlay.
3. Native `src/Main/jkObserver.c` and `src/Main/jkObserverGeometry.h` wrap the complete triangle capture definition/declaration in `#ifndef RDCACHE_RENDER_NGONS`, matching the existing call guard in `rdCache.c`.
4. `native/tests/check_spectator_ngon_compile.py` reconstructs the actual observer command from the recovered Linux compile database, remaps source paths, removes object emission and adds `-DRDCACHE_RENDER_NGONS -fsyntax-only`. This is a persistent focused compile regression, using actual engine types and Linux SDL2 definitions.
5. Regenerated the complete 24-section `native/crossplay-dedicated.patch` in the original section order. Used a temporary Git index to include all tracked/new native source, compared its sections with the full staged source diff, and passed `git apply --reverse --check` against the native checkout. The real native index was not changed.
6. Updated the patch file entry in `native/BUILD.json` and appended `post_review_rebuild` evidence to that manifest and both native build/packaging receipts. Historical build records remain intact; the appended record identifies the current patch, current source hashes, exact rebuild commands and byte identity. The full command arrays are in `qa/browser-spectator-native-build.json`.

No rebuild-helper change was needed. No observer protocol, renderer profile, control route or manager behavior changed.

## RED evidence, before implementation edits

```sh
node tests/test_spectator_geometry_ui.js
python3 native/tests/check_spectator_ngon_compile.py --source ../jk-native-browser-spectator --build /tmp/jk-native-recovery-build
```

- Browser: 18 named tests, 17 passed, 1 failed. The new regression observed one draw instead of zero: `capture 9 is superseded by known image capture 10`.
- Native syntax: compiler exit 1, three errors at `jkObserver.c:205`, requesting `v1`, `v2`, `v3` members on an integer typedef. The wrapper raises `CalledProcessError` for that exit.

Captured logs: `final-fix-wave-ui-red.log`, `final-fix-wave-ngon-red.log`. These were captured by shell redirection followed by `cat`; the shell wrapper itself returned 0 after displaying the failure, while the underlying test/compiler results above are recorded in the logs.

This supersedes the earlier absent-type/TARGET_TWL claim: `types.h` defines `rdTri` as `int` with n-gons. The actual failure was Linux SDL2 supported capture code accessing triangle members. No full TARGET_TWL build was attempted or claimed. Earlier dated review records are preserved.

## GREEN evidence

All following commands exited 0:

```sh
node tests/test_panel_ui.js
node tests/test_spectator_ui.js
node tests/test_spectator_geometry_ui.js
node --test --test-reporter=tap tests/test_panel_ui.js tests/test_spectator_ui.js tests/test_spectator_geometry_ui.js
python3 native/tests/run_spectator_tests.py --source ../jk-native-browser-spectator --build /tmp/jk-native-recovery-build
python3 native/tests/check_spectator_ngon_compile.py --source ../jk-native-browser-spectator --build /tmp/jk-native-recovery-build
```

Individual Node counts: 7 panel + 9 spectator + 18 geometry = **34 named cases passed**. The combined invocation reports three passing file subtests. Native observer suite: **19 behavior groups across five compiled test programs passed**. The native suite ran with approved sandbox escalation for AF_UNIX socketpairs. Actual Linux SDL2+n-gon syntax probe: **passed**. Logs are the adjacent `final-fix-wave-*-green.log` and individual `final-fix-wave-test_*.js.log` files.

Scoped `git diff --check` passed for production browser code, UI test and native manifests. No full manager suite rerun was required for this wave.

## Isolated build and exact byte proof

```sh
python3 native/rebuild_spectator_geometry.py --source ../jk-native-browser-spectator --baseline-build /tmp/jk-native-recovery-build --output ../jk-native-browser-spectator-final-build
```

Exit 0. Copied the new unstripped output to `openjkdf2-stripped` in that same new directory and ran `strip` on the copy. Only `jkObserver.c` and `rdCache.c` were recompiled. Reused 204 application objects and 12 dependency inputs; all **218 original baseline link inputs**, including the original two replaced objects, were independently rehashed and match the prior receipts. `/tmp/jk-native-recovery` and its build were not modified by this wave.

| Artifact | SHA-256 | Bytes |
| --- | --- | ---: |
| New stripped binary = existing packaged binary | `16944b47e2ceecf3f09cc2820af26372e2af8642057c2b0a963e353ff090c745` | 7496192 |
| New unstripped binary = previous qualified unstripped binary | `ef29783aae3cf33cc2bddad1a5dda0ff077f79bdd90f7f5b862d54ef747331da` | 8603560 |
| New observer object = packaged observer object | `9ddf7ee73f7cbbee7196d355f8d289fc5cb41a5b0bdccc34ca0107c521821e7b` | 35584 |
| New cache object = packaged cache object | `3c842a3f55972ff088e1cb62c31b3c14462c74dc03c80ea4a9fc61fa662c8a81` | 22768 |
| Retained relink archive | `8abea7457b84141777bef76685ad7f91eec9710a40811811bda12293fddb88d2` | 5992217 |
| Current complete native patch | `cbc3cb1d1d22e072f4427ecaa926e604163b2520dd2f21effcd7b0710871a542` | 157404 |

The default Linux compile profile has no changed compiled behavior, as established by identical objects and executable. The in-use packaged binary and relink archive were preserved. Prior supplied-object and libsmacker relink qualifications continue to refer to those identical bytes; this wave does not claim a new clean dependency build or a repeated source-relink test.

Exact current source SHA-256 values:

- `src/Main/jkObserver.c`: `0c0201da6e87049e702138a60069a6a5ef07fffe354dcd08de63f56260209254`
- `src/Main/jkObserverGeometry.h`: `fcdaa3f8756df6d9d3da4335d9b4c1f2311ac9abd6f2c40e5b8558a3c00dc9b1`
- `src/Raster/rdCache.c`: `5797bc91036ff41c59e8f394b3edaf71dd282bd789fd75561d89570ebe844252`

## Scoped re-review handoff

`final-fix-wave.diff` captures before/after contents of exactly the seven owned repository source/test/patch/manifest files plus both changed engine source/header files. Its `repo/` and `engine/` labels identify the two roots. Before snapshots remain at `/workspace/scratch/55e850edc256/final-fix-wave-before`. Historical review reports were not edited. This report and adjacent logs are additional evidence, not included recursively in the scoped diff.
