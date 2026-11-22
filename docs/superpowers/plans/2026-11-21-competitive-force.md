# Competitive Force Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for implementation and independent review.

**Goal:** Implement legal competitive Force builds and ordinary-input sequencing, then build and qualify the resulting native candidate.

**Architecture:** Extend the existing native bot patch and saved-character planner. Existing COGs own effects and inventory; Python forwards a validated style. Keep legacy styles available.

**Tech Stack:** C, Python standard library, pinned OpenJKDF2 source and verified archived link objects.

**Spec:** `docs/superpowers/specs/2026-11-21-competitive-force-design.md`.

## Global Constraints

- JKDF2 only; no MotS, JK2 or JA power assumptions.
- Ordinary player inputs and saved-character allocation only; no live inventory grants or cooldown writes.
- No original game scripts or assets in the public repository.
- Preserve Force-disable, peace, teams, actor/availability, range and actual bin-wait restrictions.
- Distinguish historical expert guidance, script facts, implemented policy and measured match outcomes.

## Review Focus

- Rank/style validation and lower-rank unlocks must remain legal.
- A changed or wrong Grip marker must not release at an unintended player.
- Existing Blind must not be treated as cured by Seeing.
- A short cross-power guard must not bypass per-bin waits or cancel a useful active Grip.
- The launcher, compiled profile parser and shipped binary must agree on accepted styles.

## Task 1: Implement competitive builds and ordinary Force policy

**Files:** `native/bot-client.patch`; `native/tests/test_bot_loadout.c`; `native/tests/test_bot_behavior.inc` and driver stubs if needed; `bots/run.py`; `bots/profiles.json`; `tests/test_bots.py`; `bots/README.md`.

**Engine source:** use a dedicated patched tree rooted at `/workspace/scratch/4fefaafc768d/engine-force-work`, pinned to `74e4657c4f1751d09af9ad9e056acb8f41997acb`. Edit the actual engine files, then regenerate the complete patch against that base; retain unrelated existing hunks.

**Interfaces:** Keep `jkBotLoadout_Plan(int rank, int dark, int style, jkBotLoadout *out)` with style values 0 balanced, 1 master, 2 competitive and named constants. Rank-eight dark selected bins are 21,22,23,24,31,33; light selected bins 21,22,23,24,28,25. Each is four stars. Allocate lower ranks level-by-level over that ordered eligible list. Do not allocate unavailable side powers or spend more than rank times three.

`JK_BOT_FORCE_STYLE=competitive` is accepted by Python and `jkGuiMultiplayer_BotCharacter`; diagnostics report the actual style. Built-in persona profiles use it; omitted custom-profile styles retain balanced. Runtime `jkBot` records whether the style is competitive, without changing legacy sequencing except a corrected Protection minimum-mana eligibility check.

- [x] Add failing native loadout cases covering all 54 rank/side/style combinations, exact rank-eight competitive bins, invalid style 3, rank zero and original master behaviour. Add Python validation/transport coverage for the new style and rejection of unknown values.
- [x] Implement the planner, engine style parser/log and Python profile transport; select competitive in shipped profiles and document the build dependency.
- [x] Add native controller regression cases proving proactive Seeing while engaged/unblinded, no attempt to cure existing Blind, preemptive Absorb from observed engagement/threat, unchanged actor/mana/availability gates, and legitimate cross-power activation before the old 2.4-second gap while an actual future binWait still blocks it.
- [x] Implement competitive Seeing/Absorb priorities after urgent healing. Use a 0.15-second cross-power input guard, preserving the active held-input lifecycle; legacy styles retain 2.4 seconds. Protection has no generic minimum-mana gate in the original COG, but its normal availability/activation gates still apply.
- [x] Add Grip tests for intended marker match, wrong/missing/unknown marker, reused player identity, successful normal key release, active effect plus continued weapon keys, and peace/Force-disable cancellation. Confirm through the local inventory COG victim value; do not set it. Capture stable target identity when requesting the hold. Cancel with the normal deselect path if marker or identity is invalid. Avoid automatic Force switching while a valid released Grip remains active.
- [x] Run native loadout and driver suites using `--source ../engine-force-work --build ../engine-build-probe` (loadout has no build argument), relevant Python bot tests, patch-application checks and whitespace checks. Record effects not tested by these fixtures.
- [x] Commit only this task's owned files. Write report to `.superpowers/sdd/2026-11-21-competitive-force/task-1-report.md` with source path, commits, test commands/results, deliberately unimplemented behaviours and any build risk.

## Task 2: Build, qualify and publish the reviewed candidate

**Files:** Build receipt and qualification evidence; packaging outputs only after explicit source/executable consistency checks; design/source-audit documentation.

**Interfaces:** Task 1 source and complete patch feed `engine-build-probe/rebuild_pair.py --source PATH --repo PATH --output NEW_DIR`; this recompiles both changed native translation units against the pinned SDL/native multiplayer configuration. Its `recovery-build.json` is consumed by the existing `native/package_bots.py`.

- [x] Independently review Task 1 and fix substantive findings before packaging.
- [x] Build both affected translation units; verify ordinary native join symbols and exact source/patch hashes.
- [x] Package a candidate with matching patch, binary, build receipt and relink archive; keep claims limited to tests actually run.
- [x] Establish a private original-data or self-contained fixture path for connected cloud testing; use the existing player-bot hooks because the fork's agent controller is single-player only. Verify actual join/loadout and effects where possible; report an exact blocker for any missing test.
- [x] Update source audit and qualification receipt, review the final diff, push the authorized feature branch and report its URL and remaining competitive work.

## Qualification checkpoint

- Implementation: `5ac2c16`; matching native package: `ba6a3ca`; reviewed parser/documentation corrections: `fd78d3b`. The dedicated server was not modified.
- Native planner: 54 legal rank/side/style combinations. Native controller: 32 result groups. Full Python suite: 204 tests, two PowerShell skips, no failures; subsequent map/parser correction: all 16 targeted tests passed.
- Both changed native translation units were rebuilt. Independent review verified every one of the 218 relink inputs and the package/source hashes.
- Original-data parser validation reproduced all nine maps and 193 authored starts exactly, with both original archive hashes unchanged.
- Two private native sessions used the exact packaged client: 105 seconds on m2 and 75 seconds on m_boss17 after both joins. All 736 sampled live star vectors matched their selected builds. The second session observed both players targeting one another, Seeing, Absorb, dark Grip activity and independent light-client immobility/health changes. Exact damage attribution and modern browser/human competition remain unqualified.
- The fork agent controller at `766d6def4b275499c1941fc97b5dd487cae7725d` explicitly restricts itself to single-player operation; these tests used ordinary bot-client multiplayer hooks.
