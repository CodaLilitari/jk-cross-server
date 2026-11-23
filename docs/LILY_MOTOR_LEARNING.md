# Lily motor learning experiment

Lily has a trainable movement policy and an executable policy loader. The first
network is an **unpromoted experiment**, not the default controller. The retained
route and skill estimates used by the adaptive policy are a separate, online
learning mechanism. Training this network does not alter those estimates.

The latest [protected memory-learning checkpoint](reviews/2026-11-22-lily-memory-learning-checkpoint.md)
trains a small residual over G4, pairing a recurrent arm with an equally trained
static control. Both reached 24/24 pool and 8/8 shaft landings on the open
regression set, repairing G4's lost shaft escape. Static was selected with
45,889 physics steps versus recurrent's 57,099; the same recurrent weights with
history removed used 56,081. This set therefore shows no additional benefit
from the four-unit memory. The shafts were protected training anchors and the
pool results had informed the design; this is not an unseen generalization test.

All 2,608 calibration/training/open assignments completed. The transfer stage
stopped after two invalid reference attempts: the heading checker expected
ideal trigonometry, while the frozen game uses a sine table. Independent
binary32 arithmetic matches both recorded starts exactly. Transfer remains
inconclusive, with 286 sealed assignments and 134 diagnostics unrun. The
declaration, selected model, all candidates, raw evidence and root-cause review
are preserved. No new policy was promoted to live play.

The preceding [autonomous outcome-learning checkpoint](reviews/2026-11-22-lily-outcome-learning-checkpoint.md)
trained the output head from its own unaided physical results. Both measured
checkpoints landed all 24 development pool starts, versus recovery v3's 11/24,
but each lost one shaft success (7/8 versus 8/8). The retention rule selected
neither. All 928 attempts and 519,793 model decisions passed the offline audit;
sealed and historical evaluation remained unopened. The complete candidate
lineage is preserved, and the deployed controllers remain unchanged.

The earlier [corrective recovery checkpoint](reviews/2026-11-22-lily-recovery-learning-checkpoint.md)
records the v3 initialization. One refit on the original corpus plus successful
teacher corrections improved that earlier fresh bank from 0/24 to 10/24, against
the native baseline's 23/24. That bank is distinct from the outcome study's development
set. The v1-v3 model and export bytes remain available unchanged.

## Autonomous outcome learning

The earlier output-head experiment varies only its 198 parameters, retaining
v3's 17-feature, 32-unit hidden representation. Eight generations measure the
incumbent plus six positive/negative perturbation pairs on eight shared starts.
Successful supported-dry landings rank first; actual successful physics steps
break ties, with each loss charged the full 9,000-step budget. A model owns every
input from tick zero, without a teacher handoff or native rescue.

| Development starts | v3 | Generation 4 | Generation 8 |
| --- | ---: | ---: | ---: |
| Pool | 11/24 | 24/24 | 24/24 |
| Shaft | 8/8 | 7/8 | 7/8 |
| Eligible for sealed evaluation | Reference | No | No |

Both candidates gain 13 pool starts across all six development pool positions
and lose `outcome-development-shaft-01-yaw90`. Each reaches first breath there,
but times out without supported dry landing. V3 lands at step 1,366. The null
selection preserves the predeclared requirement to retain every v3 development
shaft win. The 144 sealed and 134 historical diagnostic executions were never
assigned; this checkpoint has no sealed-transfer or native-comparison result.

The [declaration](../qa/lily-outcome-declaration.json),
[audit](../qa/lily-outcome-evaluation.json),
[independent review](reviews/2026-11-22-lily-outcome-independent-review.md) and
[checkpoint](reviews/2026-11-22-lily-outcome-learning-checkpoint.md) explain the
fixed budget, geometry splits, physical oracle, failed retention gate, preserved
artifacts and offline reconstruction. New helpers live under
`scripts/bot_development/analysis/`; the historical stock fixture is unchanged.
The source/QA checkpoint remains an experiment; no new policy is selected by a
launcher or advertised as FF-guns combat competence.

## First measured candidate

The stock-physics replay recorded 27 successful bank escapes from nine captured
starting poses, including four yaw variants for six poses. Each demonstration
records the selected ordinary movement inputs immediately before stock player
control and physics consume them. Success requires 38 consecutive physics steps
attached to a floor in the requested dry sector. All 27 cases reached that
criterion. The resulting dataset has 4,306 control frames.

The network has 15 relative physical features, one 32-unit tanh hidden layer, and
six outputs: forward, strafe, turn, pitch, jump probability and duck probability.
It has no absolute world-position input. Training uses NumPy; deployed inference
uses the Python standard library. Export embeds the exact weights and inference
code in a single ABI-1 policy, so the live loader hashes the whole candidate.

| Evaluation | Result |
| --- | ---: |
| Training frames / captured-pose groups | 3,431 / 7 |
| Held-out frames / captured-pose groups | 875 / 2 |
| Held-out axis mean squared error before fitting | 0.38896 |
| Held-out axis mean squared error after fitting | 0.18565 |
| Held-out jump/duck binary accuracy | 85.89% |
| Deployed candidate-assigned bank escapes | 22/27; 18 assisted landings and 4 without wet candidate takeover |
| Independent v1 bank escapes, 550 ms / 100 ms / every original tick | 22/27 / 21/27 / 18/27 |
| Contact/history candidate, every original tick | 21/27 original starts; 7/16 predeclared nearby starts |
| Multiplayer or human-opponent score of the learned network | Not measured |

Every yaw variant of a captured pose stays in the same split. This prevents
nearby versions of a held-out starting state from entering training. All examples
still come from one map and a simplified actor fixture. The axis error remains
substantial, and button accuracy can benefit from an imbalanced label distribution.
Neither metric measures strategic competence or traversal success.

The checked-in candidate is `bots/lily/models/water_bc_v1.json`; its self-contained
policy is `bots/lily/policies/water_bc_v1.py`. Model provenance includes the source,
map and demonstration digests and the exact split identities. The raw retail map,
private recordings and experience databases are not included. The candidate is
enabled only by explicitly staging it and supplying a current `learned-motor`
directive. No launcher selects it automatically.

## Reproduce collection, training and export

Use your owned extracted map and the pinned patched source described in the build
receipts. The build directory supplies the same generated headers and compiler
flags used by the native regression suite.

```sh
python native/tests/stock_water_replay/collect_motor.py \
  --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" \
  --map "$OWNED_JKL" --output "$NEW_PRIVATE_DEMO_DIRECTORY" \
  --compare-baseline qa/bots-bank-landing.json

python -m bots.lily.train_motor "$NEW_PRIVATE_DEMO_DIRECTORY"/*.jsonl \
  --output candidate.json --epochs 200 --hidden 32 --seed 23
python -m bots.lily.export_motor_policy candidate.json --output candidate.py
```

The collector compiles once, runs every case, records both failed and successful
outcomes, and writes a receipt. The trainer accepts only physically successful
episodes with matching applied action identity. It excludes interrupted,
censored, failed and mismatched samples. An optional `split_group` groups related
episodes; otherwise the episode itself is the split unit. At least two independent
successful groups are required. Related demonstrations must be given the same
group by the data producer.

Every accepted live training row matches a physical terminal on its scoped episode ID, integer action sequence and SHA-256 policy identity. The native sample's revision must match the full policy hash's 32-bit wire revision. Its owner must be running, its source sample must match the recorded attempt, and the attempt, observation and outcome must share an identity and life fence. Sequence zero is reserved for an identified native-baseline stock-water demonstration with its supported dry landing criterion. Old live motor samples that repeat an initial direction and distance without a world endpoint are excluded. Historical stock-water demonstrations already measured the direction and remaining distance to the dry node at every tick. The original 4,306 replay samples remain eligible.

The exported policy takes a fresh, fenced operator directive whose `goal` is `learned-motor` and whose `parameters.position` is a fixed world-space endpoint. Each inference recomputes the relative direction and remaining distance from the current pose. It waits within 0.001 game units of the endpoint. The target must be within 100 game units to produce a motor action. Optional `parameters.duration_ms` accepts 1..600 and defaults to 550 ms. Its outputs
still pass through native command validation and ordinary player controls.
Demonstration control ticks and a deployed motor chunk can have different timing;
that difference is another reason to require physical evaluation before promotion.
Use the staging and rollback procedure in [the controller guide](LILY_ADAPTIVE.md).

## What live replacement actually proved

The [integration receipt](../qa/lily-adaptive-live.json) records three bounded
stock-physics probes through the real native JKCP socket, authenticated companion
HTTP service, supervisor process and policy child processes. Each ran against a fixed engine binary.

The first deliberately simple forward-and-turn policy took control underwater.
Two revisions produced ordinary inputs, a broken candidate was rejected and the
baseline resumed when the supervisor stopped. The actor did not reach the dry
bank during that probe. Thirty-seven short displacement goals nevertheless
received positive physical verdicts. This is a concrete warning about reward
design: small local movement is not the task of escaping the water.

The revised plumbing probe lets the baseline complete swimming and airborne
movement before taking over on supported dry ground. In that run, both executable
revisions activated and applied inputs, the deliberately broken replacement was
rejected, and baseline control resumed after supervisor shutdown. The actor also
established the required dry landing. These are control and handover results.
The probe policies are not the trained network and do not establish a competitive
advantage.

A third run exercised the same dry-ground handoff with the `forward-probe` skill. Its two revisions produced 25 and 224 attributed control samples. Across 30 action outcomes, 29 reached their short displacement criterion and one was censored at shutdown. The subsequent offline readback opened the same SQLite database in an independent supervisor. At the same recorded pose, identical fresh policy workers made different validated motor decisions. An empty database supplied the 0.5 prior and the probe policy selected a 250 ms sidestep. The reopened database supplied three wins in three scored attempts, giving a smoothed probability of 0.8 and a 250 ms forward stride. The first controller's physical trace independently contains those three outcomes. The fresh workers ran after the fixture ended and both proposals were captured before transport. Attributed rows now carry a fixed endpoint and current remaining distance, and 241 samples from that trial passed the training filters. They were excluded from the previously fitted candidate.

A case-by-case comparison matched all 27 disabled-seat landings to the historical bank matrix on case, yaw, landing sector, health and supported dry time at millisecond precision. The largest difference between an unrounded recorded duration and the published rounded time was 0.000334 seconds. The receipt identifies the exact reference and collection digests.

## Matched physical evaluation

The [bank-task receipt](../qa/lily-bank-task.json) records 54 complete trials:
27 captured case/yaw starts for each controller arm. Candidate runs used the
deployed supervisor, isolated worker, authenticated companion and real native
motor commands. Both arms used the same stock physics, seed, starting state,
bank and control interval. The learned weights were unchanged.

| Measure | Preserved baseline | Candidate-assigned run |
| --- | ---: | ---: |
| Supported landings, all assigned starts | 27/27 | 22/27 |
| Supported landings, five previous holdouts | 5/5 | 4/5 |
| Simulated timeouts | 0 | 4 |
| Deaths before landing | 0 | 1 |
| Missing physical verdicts | 0 | 0 |

The candidate actually drove while wet in 23 runs. Eighteen of those reached the
bank with baseline assistance; five failed. Four other runs landed without wet
candidate takeover. Every control tick had an identified owner. None of the
candidate runs qualified for independent neural credit, so an autonomous
candidate success rate cannot be computed from this experiment. The deployed
combination performed worse on these assigned starts and remains unpromoted.

All 27 disabled-seat demonstration files were byte-identical to a fresh build of
the preceding `9e07697` checkpoint. Their landing times, sectors and health also
matched the historical matrix. All 4,306 original training observations matched
after accounting for metadata already added before this task. The receipt
distinguishes the original training archive hashes from newly emitted files.

The complete matrix followed fixes for task target binding, restart admission
reconciliation and conservative clock anchoring. A final local-outcome guard
prevents a custom policy from earning a displacement win at distance zero.
That guard does not change control inputs or bank verdicts; all 688 recorded
motor attempts had positive distances (minimum 0.119057 game units). The receipt
preserves the exact matrix source hashes and separately records this tested,
unexercised guard's final source hash.

Reproduce the comparison with a new private directory:

```sh
python native/tests/stock_water_replay/evaluate_bank.py \
  --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" \
  --map "$OWNED_JKL" --output "$NEW_PRIVATE_EVAL" --workers 4
```

The fixture contains no opponents, contested pickups or stock Force scripts.
Its wall-paced candidate transport also admits startup and scheduling variation.
The earlier complete run landed in 23/27 candidate trials; it is retained in the
receipt rather than substituted for the final 22/27 result. Neither run proves
multiplayer strength or isolates what the neural policy would do without any
baseline contribution.

## Independent control and feedback cadence

The [independent motor receipt](../qa/lily-independent-motor.json) records a
separate, synchronous stock-physics experiment. The model supplies every input
from control tick zero. No baseline decision, rescue or debug navigation query
runs during model-controlled ticks. Four axes still pass through the production
hundredth-unit codec, and held jump/duck inputs preserve ordinary rising edges.
The original player input, movement, collision, damage and 150 Hz physics
functions consume those inputs.

The predeclared timing comparison retained all 27 original starts and their
26–87 ms control intervals. A decision is held for a whole number of original
ticks: `ceil(requested_hold_ms / tick_ms)`. At a 41 ms interval, the three model
schedules therefore hold for 574 ms, 123 ms or 41 ms. The interval supplied as a
model feature stays unchanged.

| Original 27 starts | Landings | Timeouts | Deaths | Censored |
| --- | ---: | ---: | ---: | ---: |
| Native baseline | 27 | 0 | 0 | 0 |
| Frozen v1, requested 550 ms | 22 | 3 | 2 | 0 |
| Frozen v1, requested 100 ms | 21 | 3 | 3 | 0 |
| Frozen v1, every original tick | 18 | 7 | 2 | 0 |

Faster reconsideration reduced successful traversal for this frozen model on
these starts. That finding does not establish that faster feedback is generally
worse. It rules out treating the original timing mismatch as a sufficient fix.
All 27 baseline native traces remained byte-identical to the prior checkpoint.
The same physical initial state and first model action were verified across the
cadence arms, including the assigned heading.

This fixture pauses simulation while the worker decides. It measures independent
control with ideal synchronous observations. It does not qualify the deployed
supervisor's observation delays, handover behavior or multiplayer performance.
An invalid packet, worker failure or one-second exchange timeout censors the
assigned trial without baseline rescue. A completed simulated timeout or death
is a physical loss.

## One fixed contact/history candidate

Teacher-forced diagnostics found 9 correctly timed jump onsets and 13 missed
onsets in the 875 original excluded-group frames, despite substantially better
accuracy on whether jump was held. That observation motivated one conditional
candidate after the every-tick v1 arm had actual physical losses.

The candidate adds the genuine water-surface contact flag and the preceding
actually applied jump state to the existing 15 feature definitions. It keeps
32 hidden units, the six outputs, 200 epochs, seed 23, learning rate 0.01 and
0.5 button thresholds. The shared optimizer was extracted without changing v1's
result: a paired fit on all 4,306 original frames returned byte-identical model
and metric JSON before archive provenance was added. See the
[optimizer equivalence receipt](../qa/lily-optimizer-equivalence.json).

Exactly one contact candidate was fitted on 3,431 frames from the original seven
training poses and 22 yaw episodes. The loader verifies native controls against
the original baseline hashes, verifies real contact and preceding applied input,
and opens no excluded-group or perturbation trace. Recomputed relative goals
change the shared feature values at floating-point precision, by at most
7.12e-8 versus the archived training vectors. The action labels match exactly.
The wider input also adds 64 weights and changes seeded initialization, so this
is a combined candidate comparison rather than attribution to either sensor.

The [declaration](../qa/lily-motor-stress-plan.json) and
[pre-matrix addendum](../qa/lily-motor-gate-addendum.json) fixed eight nearby
synthetic poses, each at two headings, before fitting or opening stress outcomes.
The [freeze receipt](../qa/lily-contact-freeze.json) predates all stress trials.
Every starting sphere passed conservative geometry validation. These are nearby
perturbations on the known map. The two original excluded groups have informed
diagnostics and are development evidence for this candidate.

| Same every-tick controller schedule | Original starts | Predeclared nearby starts |
| --- | ---: | ---: |
| Native baseline | 27/27 | 16/16 |
| Frozen v1 | 18/27 | 10/16 |
| Contact/history v2 | 21/27 | 7/16 |

Contact v2 rescued five original failures and introduced two original failures.
On the nearby starts it rescued none and introduced three failures. All six
original and nine perturbation losses were simulation timeouts. The candidate
remains **unpromoted**. Its files are `bots/lily/models/water_contact_v2.json` and
`bots/lily/policies/water_contact_v2.py`. The latter is a fixture policy: the live
observation contract does not yet supply the required water-contact field, and
the export rejects missing physical observations instead of inventing defaults.

All 226 trial executions had complete ownership and physical outcomes. That
count includes 43 repeated baseline executions used for pairing, leaving 183
distinct controller/case/yaw configurations. The stress set has eight underlying
pose groups; its 16 headings are not 16 independent pose samples. Independent
review checked all 86,265 applied ticks and recomputed all 55,326 policy decisions.

Reproduce the cadence matrix and, only after its stated gate opens, the one
fixed fit and contact comparison:

```sh
python native/tests/stock_water_replay/evaluate_motor.py \
  --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" \
  --map "$OWNED_JKL" --output "$NEW_PRIVATE_CADENCE_DIRECTORY"

python -m bots.lily.train_contact_motor "$NEW_PRIVATE_CADENCE_DIRECTORY" \
  --output "$NEW_CONTACT_MODEL"
python -m bots.lily.motor_contact "$NEW_CONTACT_MODEL" \
  --output "$NEW_CONTACT_POLICY"

python native/tests/stock_water_replay/evaluate_motor.py \
  --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" --map "$OWNED_JKL" \
  --policy "$NEW_CONTACT_POLICY" --model "$NEW_CONTACT_MODEL" \
  --arms baseline,every_tick --output "$NEW_PRIVATE_CONTACT_DIRECTORY"
```

For the separately declared stress comparison, add
`--cases qa/lily-motor-stress-cases.tsv` and use another new directory. Compare
the frozen v1 at the same every-tick schedule. Neither training nor export
overwrites an existing candidate path.

## What the failed trajectories show

The [failure audit](../qa/lily-contact-failures.json) examines all nine contact
stress timeouts. All eight pool failures got a breath, reached surface contact
and generated 3–44 fresh surface-jump presses. No recorded 150 Hz physics step
placed those actors in exit sector 44; every matched baseline was recorded there. During
the final five seconds, the contact trajectories' median distance to the two
original pool training paths was 1.21–2.12 game units, versus 0.019–0.040 for
baseline. The remaining shaft failure entered the target sector, returned to
water, and made only 0.0018 units of net horizontal progress in its final five
seconds. Merely counting jump presses cannot distinguish a completed landing.

These traces support a problem with the approach and recovery, beyond a missing
jump edge alone. They do not isolate whether missing observations, insufficient
demonstration coverage or both caused the failures. They motivated the following
corrective demonstration experiment. The original excluded groups and this
stress set are diagnostic evidence for that candidate.

## Corrective recovery candidate

The [frozen declaration](../qa/lily-recovery-declaration.json) schedules eight
continuous handoffs from frozen v2 to the native teacher. Model control lasts
approximately 1, 4, 8 or 16 seconds on each of the two original training pool
poses. Exact prefixes and the pre-input handoff observation match archived v2
bytes. Position, momentum, breath, held inputs, RNG and the original 60-second
physics budget continue through the switch. The teacher begins with a cold
planner and selects its own route. Only progress timing and passively observed
water/health/breath bookkeeping are seeded at takeover.

Six branches completed the assigned bank task; the two later pool-90 branches
timed out. The [collection receipt](../qa/lily-recovery-collection.json) retains
all eight. Only the first 128 teacher ticks of each successful suffix enter
training, with that cap applied before the existing goal eligibility filter.
The loader uses actual preceding buttons at the first teacher frame, including
nonzero masks. Failed or censored suffixes, model-prefix actions, later teacher
ticks and development/fresh rows contribute no labels.

The original 3,431 rows and their canonical order are unchanged. The 768 added
corrections give 4,199 training rows. A single cold fit reuses the 17/32/6
contact network, 200 epochs, seed 23, Adam .01, batch128 and .5 button threshold.
All eight assignments have included/excluded counts and source hashes in the
model provenance. The [freeze receipt](../qa/lily-recovery-freeze.json) pins the
new weights and standalone export before all fresh rollouts. Normalization,
minibatches and total optimizer updates change with the larger corpus, so the
result does not isolate demonstration coverage at matched compute.

| Every-tick independent control | Native | Contact v2 | Recovery v3 |
| --- | ---: | ---: | ---: |
| Fresh six pool poses × four headings | 23/24 | 0/24 | 10/24 |
| Original starts, diagnostic/nonregression | 27/27 | 21/27 | 26/27 |
| Prior nearby starts, diagnostic | 16/16 | 7/16 | 10/16 |

The [complete evaluation](../qa/lily-recovery-evaluation.json) records all 268
executions, including 67 duplicate baseline runs used for pairing. Every
evaluated model input is unaided. The declared engineering criterion is met:
ten net fresh gains, positive gain at five of six positions, all 20 original
shaft winner identities preserved, and complete matched evidence. The original
`pool-100-yaw0` and old `perturb-shaft-a-yaw90` regressions remain visible.
The headings are clustered, and the map and pool are already known.

`bots/lily/models/water_recovery_v3.json` and its matching policy are experimental
artifacts. Fourteen fresh cases still fail. The live observation contract does
not supply the required contact field, and no launcher stages this candidate.
This is one supervised correction fit, not continuous neural training.

Reproduce with the private archived v2 matrix whose receipt matches the
declaration, the matching checkout, and your owned stock inputs. New source
versions or new collections need their own declaration and candidate freeze;
the fixed experiment's verifier deliberately rejects substituted artifacts.

```sh
python native/tests/stock_water_replay/collect_recovery.py \
  --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" --map "$OWNED_JKL" \
  --reference "$ARCHIVED_ORIGINAL_V2_MATRIX" \
  --declaration qa/lily-recovery-declaration.json \
  --output "$NEW_PRIVATE_RECOVERY_DIRECTORY"

python -m bots.lily.train_recovery_motor \
  "$ARCHIVED_ORIGINAL_V2_MATRIX" "$NEW_PRIVATE_RECOVERY_DIRECTORY" \
  qa/lily-recovery-declaration.json --output "$NEW_RECOVERY_MODEL"
python -m bots.lily.motor_contact "$NEW_RECOVERY_MODEL" \
  --output "$NEW_RECOVERY_POLICY"
```

After freezing, use `evaluate_motor.py` with baseline/every-tick arms and each
of the original, prior stress and fresh TSVs for both frozen policies. The
[offline audit helper](../scripts/bot_development/analysis/README.md#frozen-recovery-evaluation)
reopens the six directories, reconstructs the training matrix without fitting,
replays every frozen decision and computes the declared criterion. It permits
different policies to choose different first actions from the same physical
start. Neither training, export, collection nor audit output overwrites an
existing artifact.

## Development target

The bank task now supplies commitment across motor actions and a separate exact
outcome. It does not train a value function or change neural weights online.
Acquisition, combat disengagement and engagement outcomes still need their own
oracles. A short physical displacement remains supporting evidence and cannot
stand in for those outcomes.

Independent control and corrective collection are now measured separately.
The successful refit supports retaining learner-reached recovery states in the
training process. The two teacher failures and fourteen fresh v3 failures also
bound what this round of imitation achieved. The next learning work should add
task-outcome optimization and temporal/terrain context, with this frozen v3
candidate and the native bot retained as explicit comparisons.
Cloning the existing controller can initialize a skill. Improvement beyond that
controller needs outcome-based optimization and comparisons against the same
starting conditions. Opponent-conditioned tactics and self-play need recorded
engagements, consistent reward attribution and repeated matches.

The live loader supports that work by letting a trusted local candidate contain
new executable skill logic or new model weights. Retained experience survives
policy changes. A tactical operator can issue a fenced directive through the
existing owner, and a candidate can take over after the current undertaking ends.
The system does not yet generate code autonomously, run continuous neural training,
or promote its own experiments on the strength of prediction loss alone.
