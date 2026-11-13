# Task 3 native packaging and provenance

Status: packaged and verified. This was an incremental build of exactly two native application units, not a full fresh 206-unit build. No source, helper, patch, or test changes were made by this packaging worker. No commits were made. Global SHA256SUMS/release-manifest remain the root agent’s responsibility.

## Deliverables

- `bin/linux-x86_64/openjkdf2`: SHA-256 `16944b47e2ceecf3f09cc2820af26372e2af8642057c2b0a963e353ff090c745`, 7,496,192 bytes, mode `0755`.
- `native/relink-linux-x86_64.tar.gz`: SHA-256 `8abea7457b84141777bef76685ad7f91eec9710a40811811bda12293fddb88d2`, 5,992,217 bytes.
- `native/BUILD.json`: updated for the incremental build, exact source/patch/object inputs, commands, and receipt references.
- `qa/browser-spectator-native-build.json`: exact compile/link arrays, baseline provenance, current source hashes, two fresh-object hashes, 204 reused application object hashes, and 12 reused dependency input hashes.
- `qa/browser-spectator-native-packaging.json`: archive/input verification, preserved notices, supplied-object byte identity, default source-relink result, and focused packager regression results.

The complete 24-section native patch remains SHA-256 `26ea7f659236222c3a8f6abaf8f6967109e21a0dd1fe5b1bd39f8ddf65de6734` (157,328 bytes), rooted at commit `74e4657c4f1751d09af9ad9e056acb8f41997acb`. A temporary Git index reconstructed the complete source diff without modifying the real index. Each patch section matched exactly; the distributed patch orders two sections differently from canonical Git path sorting. `git apply --reverse --check` also succeeded.

## Build and packaging method

The native fix worker supplied stable final `jk-native-browser-spectator-fixed-build/commands.json` and unstripped `openjkdf2`, SHA-256 `ef29783aae3cf33cc2bddad1a5dda0ff077f79bdd90f7f5b862d54ef747331da`. Packaging independently verified that only `src/Main/jkObserver.c` and `src/Raster/rdCache.c` differed among original compiled source hashes. Both newly compiled object paths came from the exact recorded compile commands. All remaining application objects and dependency inputs matched the original manifest.

An isolated overlay at `/workspace/scratch/55e850edc256/jk-native-browser-spectator-packaging-overlay-v3` copied the 218 original link inputs, replacing only `CMakeFiles/sith_engine.dir/src/Main/jkObserver.c.o` and `CMakeFiles/sith_engine.dir/src/Raster/rdCache.c.o`. The recorded final link command, with the two absolute object paths mapped back to distributable relative paths, matched the original command after removal of the linker dependency-file flag and correction of shell-escaped `$ORIGIN` to its literal subprocess value. Replaying it produced exactly the fix worker’s unstripped bytes. `strip openjkdf2` then generated the final distributable binary. No baseline object or library was modified.

The feature native source checkout has unpopulated dependency submodule directories. Existing `native/package_native.py` therefore read notices, submodule pins, and libsmacker materials from the preserved `/tmp/jk-native-recovery` checkout, while taking executable/object inputs from the isolated overlay. Every bundled libsmacker file and required engine header was checked byte-identical between feature and baseline source checkouts. The resulting BUILD method and receipts explicitly distinguish current compiled source from unchanged baseline notice/source materials.

All 27 existing native notice files and the `libGameNetworkingSockets.so` library retained their bytes and hashes. The library remains SHA-256 `45797fcd310f0812af9f55354ff22663859ca68c2d8bb0005efb88a748c471e7`. At final audit, all 218 original link inputs and the original source checkout status still matched the pre-package snapshot. No downloads or dependency recompilation occurred.

## Commands and verification results

The exact full compile/link arrays and overlay command are in the build receipt; the orchestration driver is `/tmp/jk-package-browser-native.py`. Principal commands:

```text
python3 /tmp/jk-package-browser-native.py
python3 native/package_native.py /tmp/jk-native-recovery /workspace/scratch/55e850edc256/jk-native-browser-spectator-packaging-overlay-v3
python3 relink.py --supplied-objects
python3 relink.py
readelf -d bin/linux-x86_64/openjkdf2
python3 -m unittest discover -s native/tests -p test_package_native.py -v
```

The two relink commands ran in independent clean archive extractions. Every one of the archive’s 218 link inputs matched the new manifest, with exactly two changed hashes compared with baseline. There are 206 application objects: 2 freshly compiled and 204 reused. The 12 remaining link inputs are 11 static dependency archives and the pinned GameNetworkingSockets shared library.

- Supplied-object relink exited 0 and produced bytes identical to the packaged binary, SHA-256 `16944b47e2ceecf3f09cc2820af26372e2af8642057c2b0a963e353ff090c745`. Clean extraction: `/tmp/jk-browser-supplied-relink-gbger9l9`.
- Default relink recompiled the three bundled libsmacker source files and exited 0. Output SHA-256 `1f1dd05cd35e151ca8ebb3dc59b0df146ed8d6a51d4b0a9f1c9e18dcd04e8449`, 7,496,192 bytes. Clean extraction: `/tmp/jk-browser-source-relink-gp9o0l53`. Upstream format warnings occurred; no compile/link failures. Log: `/tmp/jk-browser-spectator-libsmacker-relink.log`, with hash and size in the receipt.
- ELF RUNPATH is the literal `$ORIGIN`; executable mode is preserved.
- Focused packager regressions: 2 tests passed, 0 failures.
- Final receipt/file consistency audit: passed for all four BUILD file entries, all 28 preserved files, all 218 original input hashes, original source status, 2 compiled units, 204 reused application objects, and 12 reused dependency inputs.

## Limits and handoff

This validates incremental packaging and both relink paths; it does not claim a fresh full application/dependency build. System shared libraries and toolchain remain environment-provided. Default libsmacker source compilation uses different flags from the original CMake build, so it is expected to differ in bytes; only supplied-object mode promises exact byte identity. Live browser/gameplay QA is owned by root, which was notified to restart with the final packaged binary before acceptance.
