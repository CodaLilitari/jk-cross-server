# Browser geometry spectator evidence

Start with [acceptance.json](acceptance.json) for machine-readable scope, test units, artifact identity and limits. The implementation is an experimental Linux x86_64 branch; the original image view remains the default.

## Evidence map

- `manager-tests.json` records the final explicit unittest TestResult and hashes of every tested manager/browser/test source file. All 176 cases completed, without skips. The corresponding raw log is under `logs/`.
- `other-tests.json` retains gateway27, UI34 and packager2 results from the integration run. The final native observer log has 19 behavior groups across five programs; its exact final command and RED/GREEN history are in `review/task-2A-report.md`.
- `synthetic-webgl.json` and its screenshot record eight actual pixel checks using the production renderer on original numerical geometry. The favicon404 is disclosed; page exceptions and WebGL errors were absent.
- `final-reviewed-live-panel.json` identifies the packaged binary and actual stock-map run: paired image/geometry sequence, payload-only geometry changes, free/follow controls, mobile layout and failure fallbacks. Input429 responses during control transitions are existing throttling, retained in the record.
- `final-viewer-lease.json` records actual tab closure, lease expiry after 6.5 seconds, the running engine and unchanged two-player roster.
- `review/` preserves implementation reports, scoped reviews, fix diffs and decisions so interruptions cannot erase their context. Historical RED attempts remain clearly separate from final GREEN results.

## Reproduction

Run `python -m unittest discover -s tests -p 'test*.py' -v`, the gateway unittest suite, and the three Node UI test files from the repository root. Native runner commands and pinned source/build identities are in the reports. `harness/` contains the exact environment-specific acceptance scripts, using the existing local Chromium and game fixture paths; adjust those paths and loopback port for another machine. These harnesses contain no credentials. They do not download game media or dependencies.

The live browser wrapper only records production draw calls and performs pixel reads after the actual renderer draws; it does not replace geometry, shaders, native output or gameplay. The unsupported-WebGL case deliberately returns no WebGL2 context to exercise production fallback.

No stock archives, executables from the supplied comparison build, ISOs, private runtime configuration or administrator tokens are included.

The final whole-branch review and single fix wave are preserved under `review/`. Both findings are resolved. `node-tests.json` and the final-fix logs identify the 34 current Node cases. The final guard rebuilt to identical native objects and executable bytes; current patch/source correspondence is appended to the native build and packaging receipts.
