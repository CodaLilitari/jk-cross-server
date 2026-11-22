# Browser package verification

`web_candidate.py` preserves the independent source/relink check used for the
refinement builds. It does not change tracked QA receipts or the source checkout.
Use Python 3.11+ with tar extraction filters, Git and a local engine repository
containing the base commit pinned in `web_bots/BUILD.json`.

```bash
python scripts/bot_development/verify/web_candidate.py \
  --repo /path/to/jk-cross-server --engine /path/to/OpenJKDF2 \
  --source-only --receipt /path/to/new-source-check.json
```

This verifies all packaged file sizes and hashes, exports the exact base with
`git archive`, checks and applies the packaged patch, and compares every changed
source hash. It retains a temporary staging directory and prints its location.
`--work-dir` chooses the parent directory. No retail game data is needed.

For the full independent relink, initialize the Emscripten version pinned by the
manifest in your shell and omit `--source-only`:

```bash
python scripts/bot_development/verify/web_candidate.py \
  --repo /path/to/jk-cross-server --engine /path/to/OpenJKDF2 \
  --compiler /path/to/emsdk/upstream/emscripten/em++ \
  --receipt /path/to/new-relink-check.json
```

The verifier uses the command and objects in `engine-relink.tar.gz`, checks the SDK
version, and requires the resulting JavaScript and WASM to match the shipped bytes.
The relink does not recompile libsmacker. A source-only report explicitly sets
`independent_direct_relink` to null; it makes no claim that linking or live gameplay
passed. Full verification also does not launch a match or establish competitive
movement quality.
