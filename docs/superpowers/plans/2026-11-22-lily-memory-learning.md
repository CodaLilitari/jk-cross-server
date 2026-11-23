# Lily protected memory experiment implementation

**Spec:** docs/superpowers/specs/2026-11-22-lily-memory-learning-design.md
**Goal:** execute and audit one bounded paired memory experiment, preserving existing bots and evidence, then push the reviewable results to draft PR #2.
**Architecture:** additive schema-3 leaky residual policy, deterministic paired search, explicit-state Python replay adapter, declaration-bound runner and offline reconstruction. The old native fixture remains byte-identical.
**Workflow:** inline implementation with focused RED/GREEN checks and one fresh whole-change review. Existing dedicated feature checkout supplies isolation. Publication is already authorized. Full suite: `python -m unittest discover -s tests -q`; retain actual skips. Do not open transfer outcomes before selection.

### Task 1: Add explicit memory inference and paired outcome search

Files: add bots/lily/motor_memory.py, bots/lily/memory_search.py, tests/test_lily_memory_motor.py, tests/test_lily_memory_search.py.

1. Add meaningful tests for exact zero-residual G4 reproduction, scalar/export recurrence agreement, physical-time decay, history-dependent controls, state validation, wait-state preservation, matched direction generation, protected-anchor selection and null/final qualification.
2. Run targeted unittest discovery. Expected: failures for the missing new modules/contracts.
3. Implement schema-3 validation, canonical identity, explicit state, standalone export, deterministic seeds/scales and selection from complete physical rows. Preserve G4 bytes and old code.
4. Run targeted tests. Expected: pass; actual differing histories can change action, while instantaneous mode removes history.
5. Commit task and run task-done with both new test modules.

### Task 2: Carry and independently audit state through real replay

Files: add scripts/bot_development/analysis/memory_rollouts.py and tests/test_lily_memory_rollouts.py.

1. Write failing tests for sequential state-chain/action reconstruction, duplicate ticks, swapped state/model, clean and interrupted traces, and observable control mismatches despite censored process receipts. Exercise actual standalone exports and the existing codec.
2. Implement session, worker, child lifecycle and audit using the unchanged native transport and oracle. Legacy/native arms delegate to the old code; new memory state resets for every independent read pass. Preserve true process exit witnesses and partial publications.
3. Run focused tests. Expected: pass; corruptions fail rather than become scores or benign censors.
4. Commit task and run task-done with the new rollout tests.

### Task 3: Freeze, run and reconstruct the bounded protocol

Files: add scripts/bot_development/analysis/run_memory_learning.py, audit_memory_learning.py, tests/test_lily_memory_experiment.py.

1. Write failing tests for the fixed schedule, exact assignment budgets, immutable retained build/model inputs, source/declaration binding, baseline integrity, anchor monotonicity, null preventing transfer, fixed selection, and offline reconstruction detecting tampering or incomplete receipts.
2. Implement separate declaration, calibration, training, open regression and conditional transfer stages, with create-only claims and no retries. Reuse old strict dispatch/oracle helpers without modifying them. Reconstruct proposals and ranks from raw observations, not reported scores.
3. Run focused and full suites. Expected: pass with explicitly reported unavailable-platform skips. Update the managed release manifest for new source files.
4. Request one fresh whole-change review with spec, plan, code range, evidence and rulings. Apply one consolidated important/critical fix pass with regression tests and full suite. Preserve minor deferred findings.
5. Publish verified source through Git connector, fetch canonical source SHA, generate and publish exact declaration, then execute only its fixed stages on authenticated retained fixture. Expected: either a complete null stop at 2,608 or complete conditional execution up to 3,030, or explicit incomplete/invalid evidence without a retry.
6. Run independent offline audit and record actual new outcomes. Expected: all reported scores reconstruct from raw bytes; no unearned live or memory benefit claim.

### Task 4: Preserve and publish the complete checkpoint

Files: qa/lily-memory-*.json and archives, docs/reviews/2026-11-22-lily-memory-learning-checkpoint.md, relevant README/manifest entries.

1. Archive candidate models/exports and retained input receipt; retain expensive raw evidence durably with verified hashes.
2. Document outcomes, paired controls, limits, review findings and outstanding next step. If selection is null, state it clearly and leave transfer unopened.
3. Verify full suite, archive inventory/hashes and Git diff; publish all new useful artifacts to the existing branch with exact tree verification. Verify PR remains draft and base unchanged.
4. Report actual results, source links, limitations, all ledger rulings and deferred findings. Clean only this plan's transient workflow workspace after preserving its final record.
