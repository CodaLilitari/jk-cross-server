# Lily protected memory-learning checkpoint — 2026-11-22

## Outcome

Both newly trained candidates achieved **24/24 pool and 8/8 shaft landings** on
the open regression set. Both restored the shaft success that the preceding G4
outcome-trained model lost. The predeclared rule selected the **static residual
candidate**, which used 45,889 physics steps across the 32 successes, compared
with the recurrent candidate's 57,099. The same recurrent weights with history
removed also succeeded on all 32 starts, using 56,081 steps. This measurement
does **not establish an advantage from memory**.

The experiment is **inconclusive for transfer**. All 2,608 calibration, training
and open-regression assignments completed with scoreable evidence. The first
two sealed assignments were invalid under the frozen starting-heading checker,
and execution stopped. The other 286 sealed assignments and all 134 conditional
diagnostic executions were not run. Neither learned model was evaluated in a
scoreable sealed attempt. No policy was promoted to live play.

| Open regression | Frozen recovery v3 | Frozen G4 | Trained static | Trained recurrent | Recurrent, history removed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pool landings | 11/24 | 24/24 | 24/24 | 24/24 | 24/24 |
| Shaft landings | 8/8 | 7/8 | 8/8 | 8/8 | 8/8 |
| All landings | 19/32 | 31/32 | 32/32 | 32/32 | 32/32 |
| Charged physics steps | 158,090 | 75,687 | 45,889 | 57,099 | 56,081 |
| Eligible final training arm | Reference | Reference | Yes, selected | Yes | Diagnostic only |

Failures cost the declared 9,000-step cap; successes cost their measured landing
step. For the three successful residual variants the table therefore reports
actual summed physics steps, without a failure penalty. Static uses 11,210 fewer
steps than recurrent, about 19.6%. Removing history from recurrent reduces its
total by 1,018 steps, about 1.8%. These are descriptive paired measurements on
one fixed set, not confidence intervals or independent geometry replications.

The [declaration](../../qa/lily-memory-declaration.json),
[supplemental reconstruction](../../qa/lily-memory-supplemental.json),
[selection](../../qa/lily-memory-selection.json),
[freeze](../../qa/lily-memory-freeze.json),
[independent measurement review](2026-11-22-lily-memory-measured-review.md) and
[validation receipt](../../qa/lily-memory-validation.json) retain the evidence.

## What learned, and what the control tests

The experiment begins from the exact G4 checkpoint retained by the previous
outcome-learning study. Its 17 relative physical features, normalization, hidden
representation and six-output head are frozen. A four-unit residual learns a
correction to that controller's action logits. It has 100 parameters: a 4-by-17
input matrix, four biases, four retention logits and a 6-by-4 output matrix.
The output matrix starts at zero, so both initial policies exactly reproduce G4.

The recurrent arm carries a four-number state between control observations.
Its learned retention is scaled by the physical interval between controls. The
static arm uses the current four activations directly, with the same initialization,
candidate directions and evaluation budget; its four retention parameters do not
affect action. It therefore has 96 effective trainable parameters. A final
diagnostic applies the recurrent weights with the state replaced by the current
activation. That removes history without changing its trained numerical weights
or merely attenuating the output through repeated zero resets.

No case label, sector identifier, yaw index or absolute world position enters
the learned features. The inherited relative target, measured surface-contact
bit and preceding applied jump state remain available. Thus the static arm still
has the inherited one-step jump feature: “static” means it lacks the added
four-unit recurrent state, not that every input is memoryless.

An episode has an explicit state identity bound to its canonical model. The
session resets to zero for each independent episode and each offline inference
pass. Every decision records the observation hash, state hashes before and after
the update and the quantized action. Independent replay joins those decisions to
the actual native input, button edges and physical terminal. The native fixture,
action packet and existing controllers were not changed.

The models learn from their own complete physical outcomes. They receive no
teacher intervention or native rescue in an attempted escape. This is a small
neural weight search over a fixed movement task; it is not a trained combat
planner, an online opponent model or a general game-playing system.

## Training and retention

The old study's eight development shaft starts are now explicit training anchors.
The old 24 development pool starts are an open, design-informed regression check.
Their earlier outcomes informed this study's design, so neither group is an
untouched generalization test.

There are eight generations per arm. Each evaluates the incumbent and four
positive/negative perturbation pairs on the same 16 starts: all eight anchors,
six rotating training pool starts and two rotating training shaft starts. The
rotation covers all 64 original training starts once. Both populations are
retained before either arm's generation is measured. All seeds, perturbation
scales, schedule entries, ranking rules and execution budgets were published
before the first outcome.

A proposal cannot discard any v3-winning anchor that its own incumbent has
already retained. Eligible proposals are ranked by fewer lost reference shaft
wins, fewer lost reference pool wins, more supported-dry landings, then fewer
charged steps. Exact ties retain the incumbent. Only each arm's final generation
can qualify for transfer; intermediate candidates cannot be substituted after
looking at regression results.

Both arms recovered the missing eighth anchor in their first generation and
retained it thereafter. Every selected generation candidate landed on all 16
starts in its current batch. Those batches rotate, so the generation totals are
not a learning curve measured on one unchanged test set. The independent review
recomputed all 144 candidate scores, exclusion decisions and all 16 selections
from native terminal and process records.

On the open set, static gains 13 pool successes over v3, spread across the six
positions as 3, 2, 2, 2, 1 and 3, while preserving all 19 v3 successes. Relative
to G4, it preserves all 31 successes and restores
`outcome-development-shaft-01-yaw90`. Recurrent and its no-history diagnostic
have the same landing outcomes. The eight shafts were rehearsed during training;
repair there demonstrates retention on the protected task, not unseen transfer.

## Execution and independent validation

| Phase | Assigned | Attempted | Scoreable | Supported-dry landings | Physical failures | Invalid | Unrun assignments |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Calibration | 144 | 144 | 144 | 110 | 34 | 0 | 0 |
| Training, both arms | 2,304 | 2,304 | 2,304 | 2,133 | 171 | 0 | 0 |
| Open regression, five arms | 160 | 160 | 160 | 146 | 14 | 0 | 0 |
| Sealed transfer, six arms | 288 | 2 | 0 | Unmeasured | Unmeasured | 2 | 286 |
| Published assignments | 2,896 | 2,610 | 2,608 | 2,389 | 219 | 2 | 286 |

There are zero censored attempts. The 134 conditional original, stress and
recovery diagnostics were never assigned. Of the maximum 3,030 declared
executions, 420 never ran: 286 assigned sealed starts and those 134 diagnostics.
Invalid attempts are neither physical wins nor physical losses. Selection is
static, not null; transfer started, but did not complete. The audit preserves
all of those distinctions.

The two zero-residual initial policies reproduce G4's native and motor traces
byte for byte on their first common 16-start batch. The fresh calibration
reproduces all 40 overlapping historical policy/start traces. On open regression,
all 64 v3 and G4 start, motor and native trace filesets exactly reproduce the
previous study. Each of the five open arms has identical starting observations
on every paired start. These checks bind the new learning result to an unchanged
physical baseline.

The frozen offline auditor re-infers decisions, reconstructs proposals and
rankings, checks state and physical control joins, and authenticates build/source
manifests. Its CLI reached the partial sealed block and exited 1 on the same
heading error, before writing a final JSON report. That failure is retained
explicitly; it is not a successful complete audit. The separate measurement
reviewer checked every scoreable terminal/process pair, all 20,880 per-attempt
file hashes and sizes, and seven complete recurrent/no-history episodes totaling
4,285 state/action joins. The completed journals contain 1,120,070 decisions.

A distinct post-run supplemental report invokes the unchanged strict
reconstruction, preserves its verified completed prefix and reproduces the
original dispatcher classifications for the two failed attempts. It retains the
actual static freeze and marks transfer unscored. Its report is labeled as a
post-run reconstruction, not an output of the preregistered CLI. The helper
neither relaxes heading validation nor changes scores; a different error remains
an error. The [audit-failure analysis](2026-11-22-lily-memory-audit-failure.md)
explains the exception boundary and why invalid attempts require a separate
unscored record. No audit or investigation launches additional game episodes.

That supplemental reconstruction completed in 464.781 seconds, re-inferring
**1,120,070 scoreable decisions**. All 18 complete blocks, 16 ranking records,
the open comparison and static freeze reconstructed successfully. The two
strict transfer rejections and the full 21,338-file inventory also matched.
The [supplemental command log](../../qa/lily-memory-supplemental-audit.txt) and
[original failed-command log](../../qa/lily-memory-strict-audit.txt) keep the
successful prefix reconstruction and the failed frozen CLI distinct.

The fixed-source full suite ran **441 tests: 434 passed, seven skipped, zero
failed**. Four skips require the unavailable original native build/map
environment; two require PowerShell and one requires Windows SID/DACL support.
The 28 new focused tests passed with NumPy. The standard-library-only discovery
profile cleanly skipped those optional training tests. The
[full suite log](../../qa/lily-memory-unit-tests.txt) is preserved.

After adding the separate preservation/reporting helpers and three focused
failure-report tests, the final checkpoint suite ran **444 tests: 437 passed,
seven skipped, zero failed**, in 131.220 seconds. Its
[separate log](../../qa/lily-memory-checkpoint-tests.txt) preserves that later
scope without replacing the pre-run test record. Standard-library-only discovery
also cleanly skips the three new optional-NumPy report tests.

## Why the transfer checker stopped

The first two transfer jobs used −45° and +45°, whereas calibration and open
regression used cardinal headings. The frozen checker calculated ideal Python
sine and cosine and compared the starting facing vector at an absolute tolerance
of 0.00002. The game rotates with a quarter-wave lookup table. At +45°, that
table supplies sine approximately 0.7071070075 and cosine 0.7068359852.

An independent binary32 reconstruction from the pinned table and recorded bank
edge matches both initial facing vectors bit for bit. Their maximum discrepancy
from ideal trigonometry is approximately 0.000249835, or 12.49 times the checker
tolerance. The accepted +90° control on the same edge differs from the ideal by
only about 0.0000000301. The starts are correct under the declared engine's
rotation convention; the verifier's expectation is wrong for the diagonal
headings. This is a harness defect, not evidence that Lily selected a bad heading.

The [root-cause investigation](2026-11-22-lily-memory-heading-investigation.md)
records the arithmetic, exact float bits, source chain and prospective tests.
It used only existing tick-zero observations and authenticated source. No frozen
source, raw trace, invalid receipt or score was changed after the failure, and
the experiment was not retried or resumed. A changed validator cannot silently
turn this declared incomplete study into a successful transfer study.

The second defect concerns reporting. The online dispatcher catches an attempt
exception and publishes an invalid record with the exception and raw hashes. The
offline partial-block path calls that same verifier directly, allowing the
exception to escape before the incomplete report is written. Its existing public
row converter also assumes fields that an invalid record does not have. A future
core correction must exercise genuine verifier exceptions through the complete
partial-report path, keeping invalid attempts distinct from scored failures and
censored attempts.

The next harness change should derive expectations from the authenticated stock
coefficients for all eight supported headings, retain the tight tolerance and
independent up-axis check, reject unsupported yaw values, and test every quadrant
on a non-axis-aligned synthetic edge. It should include negative cases for wrong
signs, exchanged axes, a perturbed facing and a corrupted up vector. This can be
validated without a new game episode or tuning a tolerance to observed successes.

Any subsequent transfer run needs a new, prospective protocol with the current
weights frozen, explicit accounting for these two already exposed v3 starts,
and preservation of the original incomplete result. No new learned policy should
be chosen using those future transfer outcomes.

The two exposed headings belong to one pool position. Of 48 planned starts, 46
were not attempted, but only 44 belong to wholly unattempted positions. A
fixed-weight follow-up can report all 48 with exposure tags and a predeclared
44-start whole-position sensitivity analysis. A fully unopened 48-start primary
bank would instead require one outcome-blind replacement pool position, with
all four headings fixed before observing results and the old quartet retained
only as diagnostics. Correcting the instrument does not require retraining or
reselecting the existing candidates. The matched transfer, followed by the
historical retention diagnostics, is the next informative measurement.

## Preservation and reconstruction

The source freeze is `0df6d85faca861db917528bb8255e745f6725769`; declaration
commit `bfe9aa52957046375ca34733debdc8eb1ece3520` preceded execution. The
declaration SHA256 is
`77ef88dcfa3f94c2095a4fbd397cbfd3c6b11fafe8b55f387503df24b66b5b4d`.
It binds 71 repository files, six prior evidence files, all 101 retained build
files and the exact v3/G4 references. The original retail map and full build
checkout were unavailable after environment reset; the authenticated retained
replay was used, with baseline reproduction required. No alternate physics
binary was rebuilt. Existing v1-v3 policies remain byte-identical.

| Artifact | Contents |
| --- | --- |
| `qa/lily-memory-candidates.tar.gz` | Every new-run model and standalone policy, including all losing candidates and the final no-history diagnostic. |
| `qa/lily-outcome-build-inputs.tar.gz` | Reused, unchanged 96 project build inputs and two license notices; only `build/*` belongs in the restored run. |
| `lily_memory_evidence_2026-11-22.tar.gz` (private) | Every remaining original run file, including both invalid transfer attempts, the measured executable and owned numeric geometry. |
| `qa/lily-memory-preservation.json` | Exact archive hashes, sizes, member counts and the verified complete run inventory identity. |
| `qa/lily-memory-implementation.bundle` | The reviewed implementation history and consolidated pre-run correction commit. |

The archives preserve **21,338 original files and 1,313,391,948 source bytes**.
There are 298 public model/export files, 96 reused build inputs and 20,944 private
raw files. The private compressed file is 219,364,130 bytes. The public and
private run payloads form a disjoint reconstruction. The
preservation helper verifies every member against the measured file bytes and
rejects unsafe paths, links, duplicate members and missing or extra files. The
private evidence is retained durably; its storage identifiers are not published
in Git. The heading investigation and full review records are included in the
checkpoint so an interrupted transfer cannot disappear behind a positive summary.

To review saved evidence, restore it to a new directory with sufficient capacity
and use this checkpoint's source. This launches no games or optimizer:

```sh
mkdir -p "$RESTORE_PARENT"
tar -xzf "$PRIVATE_MEMORY_ARCHIVE" -C "$RESTORE_PARENT"
RESTORED_RUN="$RESTORE_PARENT/lily-memory-learning-20261122-01"
tar -xzf qa/lily-memory-candidates.tar.gz -C "$RESTORED_RUN"
tar -xzf qa/lily-outcome-build-inputs.tar.gz -C "$RESTORED_RUN" --wildcards 'build/*'
python3 -B -m scripts.bot_development.analysis.report_memory_failure \
  --declaration qa/lily-memory-declaration.json --run "$RESTORED_RUN" \
  --output "$NEW_AUDIT_JSON"
```

The supplemental report's expected status is `inconclusive`, with static
selected, transfer attempted but incomplete, 2,608 scoreable attempts and two
invalid attempts. It records that the frozen CLI failed. Running
`audit_memory_learning` directly with the same arguments reproduces its exit 1
and `incorrect_initial_heading`, without a final report. Write supplemental
output outside the restored run. The original canonical run directory remains a
used claim; do not use a relocated copy to restart the declared experiment.

## Review findings, rulings and limits

The [chronological workflow record](2026-11-22-lily-memory-workflow.md) preserves
the task completions, changed assumptions, validation and initial result
publication receipt. It supplements the concise rulings below.

One fresh pre-run code review found seven Important issues. One consolidated
correction pass added regression coverage for partial-run accounting, publication
and inventory boundaries, contradictory process evidence, a unique run claim and
worker limit, exact source/archive pins, an immutable calibration model mapping
and optional-NumPy discovery. All seven were addressed before the source freeze.
The [review](2026-11-22-lily-memory-independent-review.md) distinguishes reviewer
findings from author verification; there was no second code review presented as
independent validation. Actual measured-evidence review occurred after execution.

Two Minor findings remain deferred. Extreme allowed retention logits are clipped
before the physical-time exponent; an independent
[search envelope](../../qa/lily-memory-retention-bound.json) proves every possible
parameter lineage in this fixed search remains inside that clipping boundary.
A standalone caller omitting `context.state` receives initial zero state; the
experimental session always supplies and verifies explicit state. The newly
discovered diagonal-heading defect remains in the frozen reproducible evaluator
and is separately documented for a prospective correction.

| Ruling | Reason | Consequence or cost |
| --- | --- | --- |
| Use a four-unit learned residual with an equally trained instantaneous control. | Isolate the contribution of added carried state while retaining exact G4 initialization. | Small state and bounded search may miss useful strategies. |
| Scale retention by physical control duration. | Equal elapsed time should give equal constant-input decay. | Floating-point boundaries and the chosen memory architecture still constrain inference. |
| Reclassify old shafts as rehearsal and old pools as open regression. | Their outcomes already informed this design. | The open result cannot establish unseen generalization. |
| Reuse authenticated retained physics with fresh baseline replication. | The original retail build environment was unavailable after reset. | This is not a new independently reproduced build; a baseline mismatch would invalidate comparison. |
| Initially plan connector-based publication. | Local shell authentication was unavailable. | The integration returned 403 on writing; that route was superseded, not represented as successful. |
| Bind execution to one create-only canonical path and two workers. | Enforce one declared execution budget. | No retry or resume elsewhere; interrupted execution stays incomplete. |
| Validate actual outcomes and archives after the pre-run code review. | Those artifacts did not yet exist. | A source review alone could not establish empirical success or preservation. |
| Publish exact Git bundles using the already authenticated desktop Git CLI. | The repository integration lacked write access, while the desktop session had it. | Extra transfer/hash checks; no exported credentials or global Git configuration changes. |
| Add a distinct post-run report for the strict audit failure. | The frozen partial-report path throws before publishing its verified prefix. | The supplemental helper is not preregistered; it cannot turn the two invalid attempts into scores or certify transfer. |

**Storage erratum:** the pre-run description called `/tmp` a regular filesystem.
On this host it is actually a separate tmpfs. The recorded initial free space,
5,225,656,320 bytes, exceeded the declared 4-GiB requirement. Each block passed
its allocation-reserve check, and the final sealed receipt records
3,862,978,560 bytes free. The stop was an initial-heading validation error, not
storage exhaustion. No source, path or numerical gate was altered mid-run.
The final archives reside outside that temporary run filesystem.

This remains one map, two known water exits and correlated headings of a small
set of positions. The fixture pauses for synchronous inference. It does not
measure live latency, full matches, tactical switching, rendered perception,
stock Force-script timing, opponent adaptation or FF-guns combat. The inherited
water-surface feature is still absent from the live observation contract, so
these policies remain fixture experiments. The protected rehearsal result is
useful progress; an additional benefit from the four-unit memory and general
game-playing competence remain unproved.
