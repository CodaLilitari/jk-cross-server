# Competitive Bot Foundation Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` for independent implementation and review. Steps use checkbox syntax for tracking.

**Goal:** Recover the current bot base, produce a verified authored spawn atlas, and prepare the source-grounded competitive and companion design for subsequent native increments.

**Architecture:** Retain the native ordinary-player controller and existing transports. Extend the metadata tooling without changing the game or packaging a speculative new binary. The full product target is described by the spec; this plan is its first bounded implementation increment.

**Tech stack:** Python 3.11+, standard library, existing GOB reader and JKL metadata parser; C/OpenJKDF2 source for qualification of engine semantics.

**Spec:** `docs/superpowers/specs/2026-11-21-competitive-bots-design.md`.

## Global constraints

- JKDF2 only; preserve jkweb/OpenJKDF2 transport compatibility.
- Treat authored start count, engine eligibility and live traversal as distinct facts.
- No retail assets or generated full game maps in the public repository.
- Preserve original thing index and authored encounter order; never invent an engine ordinal.
- Fail clearly on nonfinite/out-of-range/malformed spawn records.
- Top-player competence and external agent presence remain product acceptance requirements, not claims made by this metadata increment.

## Review focus

- Unordered/sparse thing IDs must not reorder authored starts.
- Nonfinite position/orientation and invalid sector indices must not produce a successful atlas.
- Template inheritance and placed overrides must determine player classification correctly.
- Duplicate thing IDs or ambiguous archive contents must not silently replace earlier evidence.
- CTF lobby/team eligibility must remain unqualified until checked against active engine rules.

## Task 1: Preserve and export authored spawn poses

**Files:** Modify `bots/map_audit.py`; add `bots/spawn_atlas.py`; add `tests/test_spawn_atlas.py`; document CLI in `bots/README.md`.

**Interfaces:** `parse_jkl(text: str) -> dict` keeps the existing return shape and adds `orientation` and `authored_order` per thing. `build_map_atlas(name: str, data: bytes) -> dict` returns map hash, source counts, ordered authored player starts, validation errors and a status. `build_atlas(data: Path) -> dict` reads the two stock MP archives using the existing validated archive index. `python -m bots.spawn_atlas --game-data PATH --output PATH` writes the complete JSON report; failures produce a nonzero exit and a report with errors.

- [x] Write failing tests for inherited player types, placed overrides, sparse/nonmonotonic IDs and exact orientation preservation.
- [x] Write failing tests for duplicate IDs, invalid sectors, NaN/infinity, malformed rows and missing stock archives/maps.
- [x] Implement the parser additions without changing the existing pickup audit's interpretation.
- [x] Implement deterministic atlas output with `source_kind: authored_player_thing`, `engine_eligibility: not_checked`, thing index, source order, template, position, orientation and sector. Preserve useful inherited properties without declaring a spawn mask interpretation.
- [x] Verify the new tests and existing bot/map tests. No full-map routing or real gameplay claim.
- [x] Document the command, expected input and evidence boundary, and review the diff.

## Task 2: Qualify the atlas against the installed stock data

**Files:** The full atlas with authored poses stays private. The tracked summary receipt is `qa/bots-stock-spawn-atlas-receipt.json`.

**Interfaces:** Use the Task 1 CLI on the user's installed `Episode/JK1MP.GOB` and `Episode/JK1CTF.GOB`; report observed archive and per-map SHA-256 and authored start counts.

- [x] Read the original archives without altering them; verify map names from installed data.
- [x] Run the implemented atlas and compare counts/identities to the baseline audit.
- [x] Check authored poses against raw rows, including `m4`'s extra authored player thing and CTF team/lobby structure.
- [x] Retain the generated result privately and record that engine-selectable starts and traversal are not yet certified.

## Task 3: Review, persist and hand off the full competitive direction

**Files:** Design above, atlas guide, a source/test checkpoint receipt.

- [x] Independently review the code against the five review-focus risks and the complete spec; fix substantive findings.
- [x] Record the new code commit, tests actually executed, original-data evidence and remaining native/companion work.
- [x] Commit the atlas checkpoint on the feature branch, preserving `main` and the packaged binaries at that checkpoint. The user subsequently approved GitHub publication, and the branch was pushed successfully.
- [x] Present current findings, the actual atlas result and the next native integration work without claiming completed competitive behavior.

## Execution ledger

- Baseline recovered at `260ef1449e8d65fefff2c574dab8dbce824cffad`; GitHub and GitLab agree.
- Baseline: `python3 -m unittest discover -s tests -p 'test_bot*.py'`: 29 tests passed.
- Source audits completed: old/native motion correction, ordinary player and chat control seams, current jkweb negotiated hit protocol, spawn selection, known map qualification limits.
- Atlas implementation: `5a2c861`; review fixes `3cd6214` and `0f3fb57` reject incomplete property assignments without losing spaced parenthesized values.
- Exact source at `0f3fb574bde4e8a6c58cd3541f4e24a2264a88f6` passed the installed-data CLI qualification. All nine map and both archive hashes/counts match the prior stock audit. A separate raw-row crosscheck matched position, orientation, sector, template and authored order for all 193 exported starts.
- The last 16 authored starts in each CTF map occupy that map's lobby sector. Runtime masks/ordinal mapping and playable spawn eligibility remain unqualified.
- Original-data evidence: `qa/bots-stock-spawn-atlas-receipt.json`. The full derived atlas is a separate private artifact.
- Full Python suite at the parser checkpoint: 203 tests, two platform skips, no failures or errors. The two skips require PowerShell on the test host.
- Final review fixed an output-path alias hazard: the CLI now refuses to overwrite either stock input archive, including a symlink or hardlink alias. Eight atlas and four existing map-audit tests passed on `1bd8604`, including all six source-preservation cases on the test host.
- Exact source at `1bd860456db42b76bfe98f36087ad74d29a91b6c` passed a repeat original-data CLI qualification and all 193 raw-row checks. The receipt and private atlas identify that revision. Final scoped review found no remaining issues.
- Publication was initially blocked pending authorization. The user's continuation explicitly approved it; `feature/competitive-bot-foundation` was then published to `https://github.com/CodaLilitari/jk-cross-server`. No merge was performed.
- Subsequent whole-branch review added strict ASCII decimal/binary32 pose validation and rejected duplicate template names at `fd78d3b`. Sixteen targeted tests passed; a new installed-data CLI run produced the identical canonical atlas previously checked against all 193 raw rows, with both original archive hashes unchanged. See the appended validation in `qa/bots-stock-spawn-atlas-receipt.json`.
- The separate competitive Force increment updates native client packaging and is tracked in `2026-11-21-competitive-force.md`.
