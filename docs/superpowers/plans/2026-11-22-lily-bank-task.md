# Lily Bank Escape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sustain one bank target across Lily's movement commands and measure how often the checked-in movement clone actually escapes under stock physics.

**Architecture:** The runtime owns a fenced, durable task above its existing native action journal. The stock replay emits physical evidence and control ownership independently. Both surfaces use one pure verdict function.

**Tech Stack:** Python standard library, SQLite, isolated ABI-1 Python workers, existing C stock-physics fixture, companion transport and project release tooling.

**Status:** Implemented and physically evaluated. See [the reviewed checkpoint](../../reviews/2026-11-22-lily-bank-checkpoint.md) for the observed results, fixes and exact verification scope. Initial preimplementation failure receipts are not retained; the review regressions have explicit failing and passing runs.

**Spec:** [Lily bank escape under stock physics](../specs/2026-11-22-lily-bank-task-design.md)

## Global Constraints

- Keep the baseline autonomous and Lily opt-in. Retain the existing learned-motor directive and model weights.
- Use ordinary player inputs, stock physics, existing atomic handover, and the Python standard library for deployed code.
- Keep motor evidence and bank-task evidence in separate records. Each task has one terminal per evidence source.
- Publish only sanitized receipts, provenance, and aggregate or case-level measurements. Keep retail assets, private traces and credentials out of git.

## Review Focus

- Repeated local successes or sampled dry states produce zero exact task wins (Tasks 1–2).
- The same order after supervisor restart cannot acquire a second task or retroactively claim actions (Tasks 1–2).
- New policy bytes between chunks cannot switch an ongoing task; a worker crash promptly releases the seat (Task 2).
- Startup delay or atomic baseline traversal can preclude all wet control; missing ticks preclude independent candidate credit (Task 3).
- A censored run, a wrong bank, a short support interval or a failed held-out case remains visible (Tasks 3–4).

---

### Task 1: Define and persist one verdict per bank task

**Files:** Create `bots/lily/bank_task.py` and `tests/test_lily_bank_task.py`. Modify `bots/lily/memory.py` and `tests/test_lily_memory.py`. Runtime/ledger lane owns these files.

**Interfaces:** Export `bank_verdict(*, terminal: str, controller: str, wet_takeover: bool, baseline_assisted: bool, ownership_complete: bool) -> dict` exactly as specified. Store a scoped task identity and terminal, with a unique association from child episode to owning task. Keep the existing motor estimates and historical databases readable.

- [x] Add tests for the complete terminal/attribution truth table, invalid values, and a previous-schema DB. Prove that two distinct task IDs can use one target, duplicate closure leaves the first result intact, duplicate child evidence cannot count a second time, and reopening SQLite preserves the terminal latch.
- [ ] Run `python -m unittest discover -s tests -p 'test_lily_bank_task.py' -v`; verify the new contract fails before implementation.
- [x] Implement classification, additive SQLite schema and atomic begin/link/finish/recovery operations. Recover only the run for which exclusive control was established. An unknown or contradictory record stays unscored.
- [x] Run `python -m unittest discover -s tests -p 'test_lily_*py' -v`; verify the focused suite passes.

### Task 2: Keep live steering committed across child actions

**Files:** Modify `bots/lily/runtime.py`, `bots/lily/export_motor_policy.py` and `tests/test_lily_runtime.py`. Regenerate `bots/lily/policies/water_bc_v1.py` only if the export template changes. Keep `bots/lily/models/water_bc_v1.json` byte-identical. Runtime/ledger lane owns these files.

**Interfaces:** Consume the Task 1 store and verdict. The new `escape-bank` operator directive uses `position`, `sector` and optional `budget_seconds`. Pass the immutable target to the existing exported movement implementation or an equivalent compatibility adapter. No second policy or model is required.

- [x] Add focused runtime cases for new/renewed/expired orders, replacement after safe completion, fault release, stale scope, restart while a command is pending, absent/regressing simulation clock, and a second distinct ID with the identical target. For sampled closure assert `physical_success is None`. Re-run the export reproducibility tests.
- [ ] Run `python -m unittest discover -s tests -p 'test_lily_runtime.py' -v`; verify new behavior assertions fail on the current implementation.
- [x] Validate and journal the wet assignment; pass fixed task metadata across commands and bind admitted children. At a terminal latch, stop new commands for that order and resume native fallback. Defer voluntary activation during a task; preserve worker-failure, release and fence handling. Never increment simulation time from polling cadence.
- [x] Run `python -m unittest discover -s tests -p 'test_lily_*py' -v` and verify all existing and new cases. Inspect a trace to confirm task IDs and native action sequence IDs remain distinct.

### Task 3: Evaluate wet candidate control and physical bank arrival

**Files:** Create `native/tests/stock_water_replay/evaluate_bank.py` and `tests/test_lily_bank_evaluation.py`. Modify fixture-only `native/tests/stock_water_replay/replay_loop.inc` and, as needed, `replay_trace.inc` or a neighboring fixture include. The evaluator lane owns this tree. Reuse `collect_motor.case_environment`, the existing replay build, and process/companion patterns in `live_policy.py`.

**Interfaces:** Consume only Task 1's `bank_verdict(...)` and Task 2's documented operator input if running the supervisor. Provide a CLI with `--source`, `--build`, `--map`, and `--output` pointing to a new directory. Emit a machine-readable receipt with unique case/yaw/arm records, separate physical and controller outcomes, and censored reasons.

- [x] Pin wrong-bank, 37 uninterrupted qualifying steps followed by loss, and 38-step exact success. Assert a finished replay with 37 local wins and an unescaped simulated timeout gives `physical_success is False`; missing native terminal yields null. Test baseline rescue, candidate applied only on dry ground, unknown ownership, and inclusion of every assigned row in a synthetic matrix summary.
- [ ] Run `python -m unittest discover -s tests -p 'test_lily_bank_evaluation.py' -v`; verify the missing evaluator/new behavior fails.
- [x] Emit exact terminal and authoritative owner counts without labeling adaptive frames as baseline demonstrations. Integrate actual applied controls from the checked-in policy, matching revision and wet entry before attributing autonomous success. Distinguish known neutral input from baseline and missing evidence. Retain stock handover and process cleanup.
- [x] Run the evaluator unit tests; run one controlled physical smoke case through the candidate and baseline entry points. Confirm timing, control-path provenance and wet-takeover diagnostics before the full matrix. Preserve even an unsuccessful candidate smoke result.

### Task 4: Qualify the complete comparison and publish measured scope

**Files:** Root owns `qa/lily-bank-task.json`, `docs/LILY_ADAPTIVE.md`, `docs/LILY_MOTOR_LEARNING.md`, `docs/BOTS_CONTINUATION.md`, the current review checkpoint, and tracked release inventory/checksums when required.

- [x] Run `python native/tests/stock_water_replay/evaluate_bank.py --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" --map "$OWNED_JKL" --output "$NEW_PRIVATE_EVAL"`. Verify 27 unique matched cases per arm and the five specified held-out rows per arm. Compare baseline landings, HP and elapsed simulated time to `qa/bots-bank-landing.json`. Investigate fixture mismatches before interpreting the comparison.
- [x] Report assigned, attributable, assisted, no-wet-takeover, unknown and censored counts; record paired duration, HP and first-breath values where observed. Publish assigned and attribution-eligible denominators independently. Include build/map/model/policy and case-list identities. A missing prerequisite or interrupted run is explicit in the receipt.
- [x] Run `python -m unittest discover -s tests -v`, the baseline matrix equivalence check, and the repository package integrity checks for changed tracked files. Verify that the historical baseline demo/model export remains reproducible and no launcher automatically selects the candidate.
- [x] Update the operator instructions, experiment report and review checkpoint using actual measurements. Preserve the existing baseline and candidate promotion status. Record human-footage observations with source/timestamps and distinguish them from fixture evidence. Refresh inventory hashes and check `git diff --check`; leave review and authorized branch publication to root.
