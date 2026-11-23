# Lily corrective recovery learning checkpoint

The fixed recovery-learning candidate landed on 10/24 fresh pool starts, against
0/24 for frozen contact/history v2. Its gains cover five of six positions, and it
retained every original shaft assignment v2 previously landed. The candidate
remains experimental. The independently reproduced physical evidence meets all
four parts of the predeclared engineering criterion.

## Recorded unaided results

| Case set | Native baseline | Frozen contact v2 | Recovery v3 |
| --- | ---: | ---: | ---: |
| Fresh pool starts, six positions × four headings | 23/24 | 0/24 | 10/24 |
| Original starts, diagnostic/nonregression | 27/27 | 21/27 | 26/27 |
| Prior nearby starts, diagnostic | 16/16 | 7/16 | 10/16 |

Every model trial owns every input from tick zero through the physical terminal.
There is no native rescue during these evaluations. Success requires the same
38 consecutive supported dry physics steps in the assigned sector, within
9,000 physics steps. All 268 executions completed with physical outcomes and
zero infrastructure censoring. The inventory includes 67 repeated baseline
executions for pairing, leaving 201 distinct controller/start configurations.

| Fresh position | V2 landings | V3 landings | Net gain |
| --- | ---: | ---: | ---: |
| recovery-pool-125 | 0/4 | 1/4 | +1 |
| recovery-pool-152 | 0/4 | 2/4 | +2 |
| recovery-pool-215 | 0/4 | 4/4 | +4 |
| recovery-pool-251 | 0/4 | 1/4 | +1 |
| recovery-pool-512 | 0/4 | 2/4 | +2 |
| recovery-pool-521 | 0/4 | 0/4 | 0 |

The observed threshold components are ten net additional fresh landings,
positive gains at five positions, and zero lost original shaft winners. All 67
start quartets have complete matched evidence. The fresh
headings are clustered within six positions, not 24 independent map samples.

Two regressions remain visible: `pool-100-yaw0` in the original diagnostic set,
and `perturb-shaft-a-yaw90` in the previous nearby set. Neither result is removed
or offset when reporting its own assignment. V3 landed all 24 original shaft
starts and both original training pool starts, but lost the original development
pool start. On the fresh set, the native failure at `recovery-pool-215-yaw0`
remains counted; v3 landed that assignment. The native baseline is still much
stronger over the complete fresh set.

## Question and scope

The preceding contact/history v2 model landed on 21/27 original starts and
7/16 nearby starts. Its eight nearby pool failures reached the surface but
missed the demonstrated bank approach. The
[preceding checkpoint](2026-11-22-lily-independent-motor-checkpoint.md) records
that diagnosis. This experiment collects native corrections after v2 has
already driven, preserves the original training corpus, and permits one fixed
supervised refit. It does not change the production bots or claim multiplayer
strength, online reinforcement learning or self-play.

The [declaration](../../qa/lily-recovery-declaration.json) predates every
canonical collection run. It fixes the eight handoffs, a 128-teacher-tick
training cap, the numerical recipe, six fresh positions at four headings, and
the transfer/nonregression criterion. Its SHA-256 is
`156e35ea59eb2fc681a1c9e5ca83d44c3a349c202607da359d2b0f6b92600e54`.

## Continuous collection

The frozen model owns inputs before the scheduled handoff. The native teacher
then takes over within the same stock simulation. Exact model-prefix
observations, applied controls, decision journals and the pre-input handoff
observation match the archived v2 bytes. Position, orientation, velocity,
health, breath, held keys, physics history and the 9,000-step budget continue.
The first native tick derives its button edges from the actual model-held keys.

The teacher starts with a cold planner and chooses its own route. Only its
progress timer and passively observed water, health and breath bookkeeping are
seeded at takeover. The collector asserts all other planner state is pristine.
No model action is requested after the boundary. The collector retains its
executed binary, validates a fixed fixture-source manifest, and records actual
engine and worker statuses. These are artifact and execution records, not
independent cryptographic attestation of the physical simulation.

| Training start | Handoff tick | First teacher physics step | Required bank landed | Teacher ticks | Eligible correction rows |
| --- | ---: | ---: | --- | ---: | ---: |
| pool-90, yaw 0 | 25 | 150 | Yes | 183 | 128 |
| pool-90, yaw 0 | 100 | 600 | Yes | 145 | 128 |
| pool-90, yaw 0 | 200 | 1,200 | No; simulation timeout | 1,300 | 0 |
| pool-90, yaw 0 | 400 | 2,400 | No; simulation timeout | 1,100 | 0 |
| pool-110, yaw 0 | 39 | 152 | Yes | 207 | 128 |
| pool-110, yaw 0 | 154 | 601 | Yes | 491 | 128 |
| pool-110, yaw 0 | 308 | 1,201 | Yes | 333 | 128 |
| pool-110, yaw 0 | 616 | 2,402 | Yes | 688 | 128 |

The [collection receipt](../../qa/lily-recovery-collection.json) preserves all
eight assigned results, source/build identities, boundary witnesses and raw
file hashes. It contains six assisted landings, two physical timeouts and no
infrastructure-censored run. There were no retries. All 6,289 applied control
ticks and 1,842 model-prefix decisions pass the continuous ownership audit.
These assisted outcomes measure teacher coverage, not autonomous learner wins.

The successful first-128-tick windows provide 768 eligible correction rows.
The two later pool-90 failures remain visible and contribute none. Selecting
successful teacher suffixes limits what this corpus can teach: it excludes
the states the native teacher could not bring to the assigned bank within the
remaining episode budget. The eight branches come from only two training poses.

## Corpus and evaluation boundaries

The archived v2 matrix's baseline arms reproduce the original 3,431 training
rows and all 22 original source identities exactly. The ordered original-row
digest is `54c5c99552b9e5ee928502522f5582932081d18fa98b8b07d035dc67f9f2f79d`.
The independently reviewed loader accepted exactly 4,199 rows. Original rows precede corrections
ordered by case ID, numeric handoff tick and control tick. Teacher frame K
uses the actual preceding mask, including a held Jump or Duck.

The fixed recipe is a fresh 17-input, 32-hidden, six-output fit for 200 epochs,
seed 23, Adam learning rate .01, batch size 128 and button threshold .5.
Normalization uses combined training rows only. Exactly one fit and export ran.
The [candidate freeze](../../qa/lily-recovery-freeze.json) records the model,
export, corpus, source and recipe digests at 15:00:07 UTC on 2026-11-22, before
any fresh controller outcome. Adding data also changes normalization, minibatches
and total updates; this is not a matched-compute causal isolation of
demonstration coverage.

The fresh set contains six declared interior positions in the same known pool,
each at headings -90, 0, 90 and 180 degrees. All six starting actor spheres pass
the conservative geometry check, with minimum clearance 0.0261122 beyond the
radius. No fresh controller outcome was opened before collection or candidate
freeze. The new model's file digest is
`e08532a4c1a2f7b0fa88417456d177cedd03c67d26555c4a5be1f4d80b599043`;
its standalone export digest is
`f849e6bae2e41e86a3ed70b6df00d6365c1803da9973fbaae6e1db8d26650d51`.

Progress requires at least four net additional fresh landings, positive net
gain at three or more of six positions, no lost original shaft assignment that
v2 previously landed, and complete matched physical evidence. The 27 original
and 16 older nearby starts are diagnostic/nonregression sets. The criterion is
an engineering signal within this task, not statistical significance or an
automatic production promotion rule.

## Evidence verification

The [complete evaluation receipt](../../qa/lily-recovery-evaluation.json)
preserves all six input receipts, their raw file hashes/sizes, every assignment,
the paired gains/regressions and the criterion. The
[portable auditor](../../scripts/bot_development/analysis/audit_recovery_learning.py)
reopens the evidence and reconstructs these results without fitting or running
the game. A separate independent audit agreed with the portable result. The final auditor
regenerated the published receipt byte-for-byte after its interruption checks
were corrected; its SHA-256 remains
`3c9ac2887e7d2a00736f5656280cb76be5009bb59f6f9b65506533812022a263`.

| Verification | Result |
| --- | --- |
| Final full regression suite, native tests enabled | 362 tests in 121.958 seconds; 359 passed, three platform-specific skips, zero failures. |
| Evaluation continuity | 268 physical executions, 148,051 applied control ticks and 958,776 physics steps recorded. No model assistance and no censored result. |
| Frozen evaluation inference | All 111,159 model decisions reproduced their quantized applied controls. |
| Collection inference | All 1,842 model-prefix decisions reproduced frozen v2; all eight exact prefix/boundary comparisons passed. |
| Start and native pairing | All 67 start quartets matched; all 67 repeated baseline native/motor traces matched byte-for-byte. Different policies chose different initial inputs, which is permitted. |
| Historical preservation | All 54 original and 32 prior-nearby baseline/v2 rows exactly reproduced the preceding checkpoint, including trace identities. |
| Training reconstruction | All original, correction and combined corpus digests matched the frozen 4,199-row candidate provenance; zero evaluation rows entered fitting. |
| Fixture and trainer review | Held-key handoff, exact source/build identities, actual process outcomes, cap-before-filter and complete decision/actuation contradiction rejection independently reviewed and regression tested. |
| Release inventory | Version `0.4.0-dev`, 569 managed files; refreshed manifest and checksum verification passed. |

The three skipped tests require PowerShell or Windows SID/DACL support.
Existing v1/v2 model and export bytes, production controller code and packaged
native/browser engines are unchanged by this checkpoint. The owned retail map,
raw private traces and retained collection executable are not distributed.

The evaluator's temporary executables have individual recorded hashes; those
files were discarded after their runs, so the audit does not claim independent
binary equivalence. It verifies their source/compiler/geometry identities and
raw control/terminal evidence. Pure evaluation has no separate per-trial process
status file; its final engine marker and physical terminal agree, and all six
evaluator commands exited cleanly. The collection separately retains its binary
and both child process statuses. The 38-step dry streak comes from the native
150 Hz oracle; the control-boundary trace alone cannot reconstruct every
intermediate floor contact.

## Decisions and continuation

The later 1/4/8/16-second handoffs target accumulated learner drift. The cost is
harder teacher states and potentially fewer usable examples; the two late
pool-90 branches did fail. The 128-tick cap and single cold refit limit teacher
trajectory dominance and prevent tuning against fresh outcomes. Their cost is
limited correction coverage and an unresolved normalization/update-count
confound. Parallel work used disjoint source ownership and independent readers;
mixing source versions would invalidate attribution, so code/data identities
were checked at collection, fitting and evaluation.

This is a useful local learning result. It supports keeping corrective examples
from learner-reached states in the training process. It does not make the native
teacher sufficient for every recovery state or qualify the model for live FF
guns. A next substantial learning step should add task-outcome optimization and
temporal/terrain context, retaining frozen v3 and the native bot as comparisons.
The original and prior-nearby regressions, and the 14 remaining fresh failures,
remain diagnostic cases; any next candidate needs newly declared evaluation
starts before its outcomes are opened.
