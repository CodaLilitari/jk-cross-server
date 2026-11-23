# Lily Recovery Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Collect and learn native corrections from learner-reached training states, then measure unaided transfer to sealed pool starts.

**Architecture:** The stock replay switches from frozen v2 to a cold native planner in the same uninterrupted physical episode. A separate collector audits mixed ownership; a strict loader adds bounded successful teacher windows to the fixed original corpus. Existing exclusive-control evaluation measures the new model.

**Tech Stack:** Existing C fixture, Python standard library and NumPy offline fitting.

**Spec:** [Corrective recovery design](../specs/2026-11-22-lily-recovery-learning-design.md)

## Global Constraints

- Preserve production engines/controllers, frozen v1/v2 bytes, stock physics and the original 9,000-step total episode budget.
- Collection uses only pool-90-yaw0 at K=25,100,200,400 and pool-110-yaw0 at K=39,154,308,616; model owns `[0,K)`, native owns `[K,N)`.
- Prefix and boundary observations match frozen reference bytes; actual inputs, RNG, actor state and physical history are continuous.
- Cold native takeover may reset its progress timer and seed passive water/health/breath bookkeeping, with no fake objective or route.
- Fit only successful teacher ticks in the first 128 native ticks, appended to 3,431 original training rows; at most 1,024 added rows.
- One refit: unchanged 17/32/6 network, 200 epochs, seed 23, Adam .01, batch128, threshold .5. No fresh evaluation data in fitting.
- All failures remain visible. Mixed successes are assisted collection evidence; evaluation is exclusively controlled.
- Fresh evaluation: six declared barycentric positions × four headings, fixed before collection; freeze candidate before outcomes.

## Review Focus

- A nonzero prior Jump/Duck at takeover must produce the ordinary stock edge, never a fabricated press from a reset.
- A stale native timer must not count prefix time as a stall or invent uninterrupted water exposure through an air crossing.
- Moving K, replacing a prefix or asking the model for a decision at K must invalidate collection evidence.
- Failed, censored, model-prefix, post-cap, development and fresh rows must not enter the training matrix. Eligible tick K of a successful teacher suffix must enter with the actual K−1 button mask, including when nonzero.
- Different policies may legitimately choose different first actions; paired evaluation requires the same initial state rather than matching those actions.

### Task 1: Continuous recovery collection fixture

**Files:** Modify `native/tests/stock_water_replay/independent_motor.inc`, `replay_loop.inc`, and minimal shared execution plumbing in `evaluate_motor.py`; create `native/tests/stock_water_replay/collect_recovery.py` and, if useful, a focused recovery include; update fixture README; create `tests/test_lily_recovery_collection.py`.

**Interfaces:** Collector accepts `--source`, `--build`, `--map`, `--reference` (completed frozen-v2 original matrix), `--declaration` and new `--output`. It writes one receipt with all eight jobs and raw `start.json`, `motor.jsonl`, `native.jsonl`, `decisions.jsonl`, `handoff.json` and logs per job. Export `assess_recovery(...)` to audit a complete run; publish its signature and job fields to Task 2 before that task begins. Successful rows report the verified teacher start tick and suffix bounds; the original trainer must reject these mixed rows.

- [x] Add failing tests for held-key handoff, passive bookkeeping across water/air, moved/forged boundaries, changed prefix/goal, extra decisions, early terminal and complete assignment accounting.
- [x] Add optional fixture-only takeover, with exact pristine-planner assertions and fully recorded permitted bookkeeping changes. Recovery disabled preserves existing behavior and trace bytes.
- [x] Implement declared eight-job collection and full reference/timeline audit, with physical losses separate from infrastructure failures.
- [x] Run focused tests and baseline/model byte-equivalence smoke, then independent spec/quality review before the canonical collection.
- [x] Commit this task's code and tests after review; root owns declarations and experiment publication.

### Task 2: Strict correction aggregation and fixed refit

**Files:** Create `bots/lily/train_recovery_motor.py`, `tests/test_lily_recovery_motor.py`; create experimental `models/water_recovery_v3.json` and `policies/water_recovery_v3.py` only after qualifying collection. Reuse existing contact inference/export and numerical optimizer.

**Interfaces:** `training_rows(original_directory, recovery_directory, declaration_path)` returns ordered original+correction rows and provenance; calls Task 1's complete recovery audit and hashes before extracting any window. CLI accepts the three explicit inputs plus new `--output`; refuses overwrite. Model schema remains 2. Teacher frame K's previous mask is the prefix's actual K−1 mask.

Here `original_directory` is the completed frozen-v2 original matrix used as the collection reference, including its baseline arms. Its original 3,431 ordered rows and all 22 source trace identities were checked equal to the corpus used to fit v2; record the actual receipt used without relabeling it as the older receipt.

- [x] Add failing tests for physical failure/censor rejection, prefix/post-cap exclusion, nonzero boundary history, immutable original split/order, receipt/source tampering and zero-row no-fit gate.
- [x] Implement strict original corpus preservation and bounded successful correction extraction in case/K/tick order, with per-assignment inclusion/exclusion counts.
- [x] Verify the numerical recipe and standalone export parity. Obtain independent spec/quality review before fitting once.
- [x] Fit and freeze one candidate after complete collection and fresh-case declaration; record all inputs/code/settings/hashes without opening fresh outcomes.
- [x] Commit task code, tests and frozen artifacts; root runs the fixed evaluation and publishes results.

### Task 3: Sealed evaluation, report and push

**Files:** New declaration, collection/evaluation/freeze QA receipts, fresh-case TSV, checkpoint and continuation/learning docs; release manifest/checksums.

- [x] Before collection, declare the eight fixed branches and six fresh positions/four headings with exact hashes and geometry checks.
- [x] After freeze, evaluate v2/v3/baseline on all 24 fresh, 27 original and 16 prior stress assignments; join across policies by actual starts and baseline trace bytes. Keep all outcomes.
- [x] Compute the predeclared paired engineering criterion, independently audit attribution/inference, and document limitations and next evidence-based step.
- [x] Run meaningful full regressions and whole-change review, refresh/check release integrity, commit final evidence and push the existing development branch; update draft PR #2.
