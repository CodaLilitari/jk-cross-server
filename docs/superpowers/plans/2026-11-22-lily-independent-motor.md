# Lily Independent Motor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Measure the learned motor without baseline intervention, isolate feedback cadence, and evaluate one contact-aware candidate if required.

**Architecture:** A fixture-only synchronous input loop uses isolated policy workers and unchanged stock physics. Its independently recorded observation/action stream supports a fixed timing ablation and an optional two-feature training experiment.

**Tech Stack:** Existing C replay, Python standard-library runtime and IPC, NumPy for offline training, SQLite/production code unchanged unless a shared helper needs a strictly compatible refactor.

**Spec:** [Independent motor feedback experiment](../specs/2026-11-22-lily-independent-motor-design.md)

## Global constraints

- Preserve production engine packages, existing bots, v1 weights and original native baseline behavior.
- All movements pass through stock handlers; no position/velocity injection or altered collision/jump physics.
- Exact verdict is 38 supported dry physics steps in the target sector; maximum 9,000 steps.
- Frozen-v1 cadence arms are 550 ms, 100 ms and one original control tick, with production input quantization.
- Every assigned failure stays visible; infrastructure loss is censored and cannot become baseline assistance.
- V2, if needed, uses only training groups, fixed settings and genuine applied-action history.

## Review focus

- Held jump input must not manufacture repeated keydown edges.
- Actor state and first model action must match across cadence arms before any physics advances.
- Missing or malformed observations/actions, partial transport and worker stalls must terminate within a bounded wall interval.
- Independent ownership requires a complete ordered tick stream; model traces must not enter the old native-baseline training path.
- Previously inspected held-out poses must not be represented as fresh confirmation for a feature selected after those diagnostics.

## Task 1: Independent stock-input fixture and timing evaluator

**Files:** `native/tests/stock_water_replay/` new model IPC/trace include, fixture integration, `evaluate_motor.py`, `run.py`, README; `tests/test_lily_independent_motor.py`.

**Interface:** Worker consumes current `state`, `lily.sense`, fixed goal and original tick interval. Sense adds `on_water_surface` and preceding actual `buttons`. Frozen v1 uses its existing `learned-motor` directive. C accepts one tick-identified, bounded quantized action; a held decision retains a source tick. Raw evidence includes before-state plus applied controls, pulse edges and exact terminal. Publish the schema before the training lane starts.

- [x] Add discriminating tests for cadence rounding, ordinary jump release/repress, strict axis/button bounds, failure accounting and trace identity.
- [x] Implement separate model-only control and complete observation/action provenance, with first decision before physics.
- [x] Run a paired baseline/model smoke, verify all baseline hashes against the previous fixture, then run the fixed 108 assigned timing trials.

## Task 2: Contact-aware candidate when justified

**Files:** New `bots/lily/motor_contact.py`, training/export helper and experimental model/policy files; shared optimizer refactor only if byte-compatible; `tests/test_lily_contact_motor.py`.

**Interface:** Consume schema from Task 1 baseline observations, including actual surface contact and previous applied jump. Produce one hashed 17-feature, 32-hidden, 6-output candidate and a self-contained ABI-1 benchmark policy that requires the additional observations.

- [x] Predeclare perturbation cases and validate starting geometry before evaluating the candidate.
- [x] Gate on the per-tick v1 outcome. If it fails, fit one fixed candidate on the seven original training groups and record every source/split identity.
- [x] Verify missing physical fields fail closed, previous input uses actual evidence, group boundaries hold and export reproduces inference.
- [x] Freeze weights before evaluating all original and predeclared perturbation cases. Preserve unsuccessful results; leave promotion separate.

## Task 3: Review, report and publish

**Files:** Sanitized QA receipts, learning/controller continuation docs, checkpoint, release inventory.

- [x] Audit every ownership/terminal stream and paired start identity; report physical results separately from deployed behavior.
- [x] Run meaningful focused/full regression tests and independent review; fix confirmed findings before final qualification.
- [x] Refresh and check release integrity, commit all authorized code/helpers and push the existing development branch; update draft PR #2.

## Observed checkpoint

The complete timing matrix found 27/27 native baseline landings and 22/27, 21/27 and 18/27 frozen-v1 landings at the three schedules. The fixed contact candidate reached 21/27 original and 7/16 nearby starts; v1 reached 10/16 nearby starts. Both remain unpromoted. All 226 executions have complete physical outcomes and ownership, including 43 repeated baseline checks. See [the checkpoint](../../reviews/2026-11-22-lily-independent-motor-checkpoint.md) for evidence, limitations and the next experiment.
