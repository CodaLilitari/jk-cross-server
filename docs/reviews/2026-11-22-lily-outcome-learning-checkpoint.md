# Lily autonomous outcome-learning checkpoint — 2026-11-22

## Outcome

Both outcome-trained checkpoints reached **24/24 development pool landings**, up
from the frozen recovery-v3 reference's **11/24**. Each also lost one of v3's
eight shaft successes. The declared retention gate therefore selected neither
candidate. The experiment closed after **928 complete executions**. The sealed
transfer and historical diagnostic stages remain unopened, and the deployed
controllers retain their previous behavior.

| Development starts | Frozen v3 | Generation 4 | Generation 8 |
| --- | ---: | ---: | ---: |
| Pool: six positions, four headings each | 11/24 | 24/24 | 24/24 |
| Shaft: two positions, four headings each | 8/8 | 7/8 | 7/8 |
| All development starts | 19/32 | 31/32 | 31/32 |
| Lost v3 shaft wins | 0 | 1 | 1 |
| Eligible under the declared rule | Reference | No | No |

For either candidate, the 13 added pool successes cover all six positions: gains
of 3, 2, 2, 2, 1 and 3. All 11 v3 pool wins survive. Both candidates lose exactly
`outcome-development-shaft-01-yaw90`. The aggregate gain does not override the
predeclared per-start retention requirement. No alternative candidate was tested
after this decision and no new deployed policy was designated.

The [declaration](../../qa/lily-outcome-declaration.json),
[complete offline audit](../../qa/lily-outcome-evaluation.json),
[null-selection freeze](../../qa/lily-outcome-freeze.json),
[independent evidence review](2026-11-22-lily-outcome-independent-review.md) and
[validation/preservation receipt](../../qa/lily-outcome-validation.json) retain
the exact inputs, outcomes and decision.

## What actually learned

This checkpoint changes neural weights using the model's own complete physical
outcomes. It starts from the exact recovery-v3 model and holds its 17 physical
features, normalization, 32-unit hidden representation and action codec fixed.
The learned parameters are the 198 weights and biases in its six-output head.
The outputs still request ordinary forward, strafe, turn, pitch, jump and duck
inputs. No teacher controls a model episode or rescues an unsuccessful attempt.

Eight fixed generations each measure the incumbent and six positive/negative
parameter perturbation pairs on eight shared starts. That is 13 candidates per
generation and 832 actual executions. The first four output rows use perturbation
scale 0.18/sqrt(33), the two button rows use 0.65/sqrt(33), and generations 5–8
halve those scales. PCG64 direction seed 41023 and schedule seed 31023, all batch
IDs and candidate ordering were committed before the first rollout.

The score first maximizes supported-dry landings. Successful trials are then
charged their actual number of physics steps; every physical loss costs the full
9,000-step budget. Exact ties keep the incumbent. This prevents an early death
from appearing preferable to a slower success. The two later checkpoints tested
on development were fixed in advance: the generation-four and generation-eight
winners. Selection required strictly more pool landings while preserving every
v3 shaft win on that development set.

The generation-one winner improved 4/8 incumbent landings to 6/8 on its shared
batch; generation two improved 7/8 to 8/8. Generations three through seven retained
eight landings and reduced charged steps. Generation eight improved 7/8 to 8/8.
Batches differ between generations, so this is not a learning curve evaluated on
one common test set. The independent review retains all 104 rankings and the
exact parent-to-winner lineage, including every rejected candidate.

## Physical task and execution accounting

The unchanged fixture applies every model decision from tick zero through the
production movement-input codec and stock movement, collision, damage and
150 Hz physics functions. The final oracle requires **38 consecutive physics
steps supported on a floor in the requested dry sector**, within 9,000 physics
steps. Surfacing, entering the target sector, or moving nearer the endpoint does
not satisfy that criterion. Each model supplies every original control tick;
there is no native teacher, fallback or between-generation source change.

| Phase | Executions | Supported-dry wins | Simulation timeouts | Deaths |
| --- | ---: | ---: | ---: | ---: |
| Training: all candidates | 832 | 746 | 85 | 1 |
| Development: v3/G4/G8 | 96 | 81 | 15 | 0 |
| Total | 928 | 827 | 100 | 1 |
| Conditional sealed evaluation | 0 | Unmeasured | Unmeasured | Unmeasured |
| Conditional historical diagnostics | 0 | Unmeasured | Unmeasured | Unmeasured |

All attempted runs completed with usable evidence: zero censored, invalid or
unrun assignments, zero unpublished process sidecars, and zero unverifiable
applied decisions. The audit independently re-inferred **519,793 model decisions**
and joined them to the actual native inputs and terminal records. The independent
review compared all 928 public rows against their closed assignments and block
records, recomputed the rankings and development gate, and sampled raw terminal
and control evidence. Its review added no game executions.

Training took 219.932 wall-clock seconds. The selection command took 151.711
seconds, including full reconstruction of training before the 96 new attempts.
The final offline audit took 146.681 seconds. These are measured command durations
on this host; they are not simulated traversal times or hardware benchmarks.
Two workers were used, below the declared maximum of four.

## The shaft regression

The three policies start from identical physical observations on the regressed
case. All reach first breath. V3 establishes the required landing at physics
step 1,366, about 9.107 simulated seconds. G4 and G8 both time out at step 9,000,
alive at 100 health in shaft sector 54 with zero terminal supported-dry steps.

G4 remains in sector 54 at all 1,500 recorded control observations and reports
continuous surface contact from tick 137 onward. G8 reaches the target sector on
140 control observations but has no supported control observation. These samples
occur every six physics steps; the terminal oracle separately checks consecutive
support at physics resolution. Initial quantized axes differ, and the trajectories
differ despite the same final failure.

This post-hoc inspection identifies the transition from surfacing or approaching
the target to establishing support as a useful next question. It does not isolate
one action as the cause, establish how often the behavior recurs elsewhere, or
justify a rule tied to this case ID or heading. No corrective weights were fitted
after examining this regression.

## Scope and next learning question

The development positions are disjoint from training positions and cover a
broader portion of the same pool and shaft geometry. However, the measurement
still concerns one map, two known bank edges and a fixed learned representation.
Four headings of one position are related trials. G4 and G8 share a lineage, and
development outcomes directly determine eligibility. The untouched sealed set
would have changed both positions and headings; no result from it is available.
The 27 original, 16 prior stress and 24 recovery starts are historical diagnostics
and were not rerun. Native baseline performance on the new development bank is
also unmeasured.

The result supports further outcome learning: a small weight search produced
large gains on new development pool starts. It also exposes an optimization
tradeoff: the search did not retain every shaft behavior the reference could
already perform. A future predeclared experiment should make retention visible
during training through a broader mixture of skills and protected rehearsal,
then test whether a learned phase or recurrent state helps convert surfacing into
stable support. Those are design hypotheses, not implemented results. Simply
adding a case-specific exception would not answer that learning question.

No FF-guns combat, stock Force-script use, opponent adaptation, full match,
rendered gameplay or elite-player comparison was measured in this checkpoint.
The inherited water-surface feature is still absent from the live observation
contract, so these contact-based policies remain synchronous fixture experiments.
The v1-v3 artifacts and existing native/browser controller packages are preserved.

## Source verification

The implementation was frozen at `0b1e1fc3cae838b88ee1b1cabdde61a1289917b6`.
Declaration commit `68907b6ac1209aa9372a04a088ade88182e9e941` precedes the first
rollout. It pins 60 repository source files and 96 external project/configuration
inputs. The 95 external source files were authenticated against the pinned
upstream engine and native patch; the configured header was independently
regenerated byte for byte. The actual six-unit compiler dependency set is checked
against those pins before outcomes can be scored. The original 27-file historical
source inventory and fixture/controller/model bytes remain unchanged.

Review closed four concrete issues before freezing: hidden prior-stage evidence
in model directories; disagreement about unpublished process receipts; lost
initial-state comparison after a genuine late worker failure; and unbound
physics-affecting project headers. Both live and portable verification reject
modified physics headers even when a run receipt is edited to match them.
Compiler-provided system headers and link libraries are outside the project-input
manifest. The compiler, runtime, flags and actual executable identities are
recorded; no cross-toolchain bit-identical-build claim is made.

The fixed-source native-enabled suite ran **413 tests: 410 passed, three skipped,
zero failed**. Two skips require PowerShell and one requires Windows SID/DACL
support. The [complete test output](../../qa/lily-outcome-unit-tests.txt) and
validation receipt bind that result to the tested source commit. No frozen source
changed after the full suite or during the experiment.

## Preserved artifacts and offline reconstruction

| Artifact | Contents |
| --- | --- |
| `qa/lily-outcome-candidates.tar.gz` | Exact 210 model/export files for v3 plus all 104 candidate artifacts, including losing heads. |
| `qa/lily-outcome-build-inputs.tar.gz` | Exact 96 declared project inputs plus the OpenJKDF2 and MIT license notices. |
| `lily_outcome_evidence_2026-11-22.tar.gz` (private) | The other 7,459 run files: all raw attempts, complete receipts, measured replay, numeric owned geometry and generated build output. |

The three bundles form a disjoint inventory of all 7,765 original run files,
529,056,264 bytes in total; the two public license notices are additional. The
private compressed archive is 82,309,070 bytes and was saved persistently. Every
archived original file was compared with the measured bytes. Exact archive hashes
and member counts are in the validation receipt and independent review. Retail
map-derived geometry remains in the private evidence.

To reconstruct for offline review, use the repository at this checkpoint and a
new destination with sufficient space. Extract the private archive there, then
overlay the model bundle and only the build members from the project-input
bundle. The license members remain available in the distributed archive and the
repository's `licenses/` directory.

```sh
mkdir -p "$RESTORE_PARENT"
tar -xzf "$PRIVATE_EVIDENCE_ARCHIVE" -C "$RESTORE_PARENT"
RESTORED_RUN="$RESTORE_PARENT/lily-outcome-learning-20261122-01"
tar -xzf qa/lily-outcome-candidates.tar.gz -C "$RESTORED_RUN"
tar -xzf qa/lily-outcome-build-inputs.tar.gz -C "$RESTORED_RUN" --wildcards 'build/*'
python3 -B -m scripts.bot_development.analysis.audit_outcome_learning \
  --declaration qa/lily-outcome-declaration.json \
  --run "$RESTORED_RUN" --output "$NEW_AUDIT_JSON"
```

The auditor neither compiles nor executes a game or optimizer. Its current free
filesystem-byte observation can differ on another host. Scientific identities,
assignments, outcomes and reconstructed decisions must still agree. Never write
new audit output inside the retained run, and never use the retained run as the
destination for a new training attempt.
