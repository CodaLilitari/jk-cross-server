# Lily Outcome Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train and honestly evaluate a fixed-budget, autonomous outcome-selected neural motor head initialized from recovery v3.

**Architecture:** A pure numerical search module proposes and ranks heads. An additive runner uses the unchanged stock fixture with explicit process witnesses and full decision audits. A separate offline audit reconstructs the entire experiment before results are published.

**Tech Stack:** Python 3, existing NumPy, standard-library IPC/process orchestration, unchanged native stock-physics fixture.

**Spec:** `docs/superpowers/specs/2026-11-22-lily-outcome-learning-design.md`

## Global Constraints

- Add experiment code outside `native/tests/stock_water_replay`; do not change existing fixture, controller, codec, model, exporter, training or historical QA files.
- Freeze v3's schema 2, 17 features, six outputs, normalization, `w1` and `b1`; train only the 198 `w2`/`b2` coefficients.
- Model episodes use `every_tick`, exclusive model ownership from tick zero, no native assistance, and the original 9,000 physics-step / 60-second budget with 38 consecutive supported-dry steps.
- Death and simulation timeout are losses; censored or contradictory evidence never supplies a score. No retries; incomplete blocks stop the experiment.
- Eight generations, six antithetic pairs plus incumbent, eight shared starts per generation: 832 training executions. Development evaluates v3/G4/G8 on 32 starts. Sealed execution is conditional on selection.
- Preserve exact measured model/export bytes. No post-outcome model metadata changes. No production or live-policy promotion.
- Standard library and existing NumPy only. Keep map-derived geometry and raw traces private. User has authorized implementation and push to the existing feature branch/draft PR, without merging.

## Review Focus

- Early deaths and all-failure batches must not outscore an additional supported-dry win; Task 1 exercises lexicographic reward and stable ties.
- A terminal flushed before worker failure must remain censored; Task 2 exercises actual process status independently of trace success.
- A restart or interrupted block must not consume a new seed or hide an attempted loss; Task 2 exercises exclusive claims and incomplete-block refusal.
- Distinct policies may choose different first actions from identical physical starts; Task 2 tests paired identity without action equality.
- Edited lineage, wrong split roles or incomplete denominators must fail offline auditing; Task 3 tests these independently of summary totals.

---

### Task 1: Pure output-head search and development selection

**Files:**
- Create: `bots/lily/outcome_search.py`
- Test: `tests/test_lily_outcome_search.py`

**Interfaces:**
- Consumes: unchanged `bots.lily.motor_contact` validation/canonical/export helpers and the exact v3 JSON.
- Produces: `head(model) -> numpy.ndarray` of shape `(6,33)`; `candidate_models(incumbent, generation, declaration_sha256) -> list[dict]` with keys `candidate_id`, `model`; `score_episodes(rows, expected_ids) -> tuple[int,int]`; `select_generation(candidates, evaluations, expected_ids) -> dict` with `selected_id`, `scores`; `select_development(evaluations, pool_ids, shaft_ids) -> dict` with `selected` (`v3`, `g4`, `g8` are evaluated; selected is `g4`, `g8` or null), per-policy pool/shaft counts, shaft-regression IDs and eligibility.

- [x] Write behavior tests for unchanged encoder/normalizer and parent data; 198 varied coefficients; exact antithetic offsets; seeded repeatability independent of call order; half-scale generations 5-8; exact incumbent model identity; standalone export validation.
- [x] Write score tests proving a slow extra win outranks quick deaths, all losses charge 9,000 each, exact ties keep incumbent, and duplicate/missing assignments, wrong ownership, censor, invalid terminal or out-of-budget steps are rejected. Development tests cover per-start shaft preservation, strict pool improvement and G4-first ties.
- [x] Run the new test module and record the expected missing-module failure.
- [x] Implement the interfaces. Draw directions using PCG64 seed 41023 with full tensor `(8,6,6,33)`; scales `.18/.65/sqrt(33)` for generations 1-4 and half thereafter. Candidate IDs `g{generation:02d}-c{index:02d}` ordered incumbent then paired +/- directions. Proposals replace provenance with method, v3 ancestor identity, actual parent canonical digest, declaration digest, generation/direction/sign/seed/scales and frozen-encoder description. Stable lexicographic ranking is `(wins, -sum(win_steps if win else 9000))`.
- [x] Run `python3 -B -m unittest discover -s tests -p 'test_lily_outcome_search.py' -v`, self-review, commit only these files and report RED/GREEN evidence.

### Task 2: Bounded stock-physics runner with evidence gates

**Files:**
- Create: `scripts/bot_development/analysis/outcome_rollouts.py`
- Create: `scripts/bot_development/analysis/run_outcome_learning.py`
- Test: `tests/test_lily_outcome_rollouts.py`
- Test: `tests/test_lily_outcome_runner.py`

**Interfaces:**
- Consumes Task 1 functions; root-provided `qa/lily-outcome/{train,development,sealed}.tsv`, geometry receipts and `qa/lily-outcome-declaration.json`; existing `run.build_replay`, `evaluate_motor._execute_trial`, `assess`, `make_jobs`, and recovery audit `engine_code`, `replay_decisions`, `START`.
- Produces CLI `python3 -B -m scripts.bot_development.analysis.run_outcome_learning {train,select,evaluate} --declaration PATH --output RUN_DIR` with `--source`, `--build`, `--map` required for train and `--workers` default 4, maximum 4. Train builds once, retains exact candidates/raw evidence and `training.json`; select retains 96 attempts, `selection.json` and `freeze.json`; evaluate requires a selected freeze and retains sealed (v3/selected/native) plus original/stress/recovery diagnostic pairs and `evaluation.json`. Existing stage refusal is mandatory. Output/data schemas and callable runner interfaces must be described in the implementation report for Task 3.
- `outcome_rollouts.audit_attempt(assignment, work, case, policy, model) -> dict` must recheck claims, source/model identity, factual process status, native ownership/terminal/inputs, and full frozen-export decisions; expose it for Task 3. It must distinguish physical failure, genuine censor and evidence contradiction. A censor has no score.

- [x] Add focused tests for late child failure after physical terminal, real timeout status and kill/reap, exclusive attempt/stage creation, preservation of pending/attempted denominator, no score or next generation on one censor, and paired initial identity accepting distinct first actions. Use real tiny subprocesses for status behavior where practical; reuse complete synthetic physical traces for evidence tampering.
- [x] Add orchestration tests with a small deterministic evaluator seam proving candidate order and batch identity, exactly declared assignment coverage, selection gating, no sealed access before a selected freeze, and refusal to load a case list under the wrong phase/digest.
- [x] Run the focused tests to record expected failure, then implement. Keep all additions outside the fixture directory. Pin and regenerate the v3 export, build and retain one executable, capture complete source/flags/geometry identities and actual child statuses. Reject insufficient initial free space (<2.5 GiB); retain raw traces without an archive subsystem. Re-audit each attempt before scoring. Pair start/seed/origin/goal with the frozen historical edge witness, never compare first actions across policies.
- [x] Use declaration schema documented in the spec: parent model/policy paths and three digests; role-bound case paths/digests; eight explicit training batch ID lists; frozen source digests; diagnostics paths/digests; fixed algorithm/selection/criterion settings. Coordinate exact schema with root before writing the declaration. All settings must equal the fixed supported recipe; no tuning CLI. Write assignment claims before dispatch; retain in-flight evidence on failure and refuse automatic resume/retry. Model provenance is fixed before execution and results live in external receipts.
- [x] Run `python3 -B -m unittest discover -s tests -p 'test_lily_outcome_*.py' -v`. If native integration is used, use only historical starts or synthetic fixtures; do not open new training/development/sealed outcomes before the declaration is frozen. Commit these four files, report test evidence and exact receipt interfaces.

### Task 3: Offline reconstruction and transfer scoring

**Files:**
- Create: `scripts/bot_development/analysis/audit_outcome_learning.py`
- Test: `tests/test_lily_outcome_evaluation.py`

**Interfaces:**
- Consumes Task 1 selection/score functions, Task 2 assignment/process/raw audit interfaces and retained receipts. Reads declared train/development/sealed roles, frozen source/model/case/build identities and exact diagnostic assignments.
- Produces CLI `python3 -B -m scripts.bot_development.analysis.audit_outcome_learning --declaration PATH --run RUN_DIR --output NEW_JSON`; output is a public receipt with numerical results, lineage, raw hashes/sizes, denominators, decision counts and criterion. No fitting, rollout or mutation of inputs.

- [x] Write tests proving proposals and incumbent lineage reproduce, a changed head/parent or external score is rejected, all declared candidate/start entries are present exactly once, held-out roles cannot be substituted, G4/G8 development selection reproduces, and no-selected experiments leave sealed/diagnostic results absent.
- [x] Write paired-score tests for net +4 sealed pool landings at >=3 positions, per-start sealed shaft preservation, retention of all 24 original v3 shaft winners, incomplete evidence yielding no positive criterion, and reporting gains/regressions by pose without pretending headings are independent samples.
- [x] Run the tests to record expected failure; implement independent reconstruction using measured model/export bytes and `audit_attempt` for every attempted execution. Recompute the fixed direction proposals, each generation's rankings and next incumbent, the development gate, frozen model identity and all final pairings. Verify real process evidence and raw hashes, including failures. Publish none-selected or inconclusive truthfully rather than manufacturing a winner.
- [x] Run `python3 -B -m unittest discover -s tests -p 'test_lily_outcome_*.py' -v`, self-review, commit these two files and report evidence.

## Execution and publication after code review

Root owns geometry/declaration preparation, source freeze, actual training and evaluation, and the final report. Freeze declaration and implementation digests before training. Run train and select; preserve a no-improvement result or freeze the chosen measured bytes before evaluate. Generate the offline public audit, obtain an independent evidence review, run the necessary full suite once, refresh/check the release manifest, update the learning/continuation guides and draft PR, push the authorized feature branch, and verify remote HEAD/PR state. Keep foundation SHA and v1-v3 unchanged. No new optional experiment follows this fixed budget in the same checkpoint.
