# Lily corrective recovery learning

## Intent and authorization

Continue the delegated learned-player work from `79f8373`. Contact/history v2
lands on 21/27 original starts and 7/16 nearby starts; all eight nearby pool
failures miss the demonstrated exit approach. The next experiment adds
corrections from states reached by the learner itself. Preserve existing bots,
production engines, v1 and v2. Implementation and publication to the existing
development branch remain authorized by the user.

## Approaches and decision

An arbitrary-state reset would need to reconstruct contacts, collision state,
held inputs and physics residuals. A planner running invisibly during the model
prefix would introduce decisions and mutable state absent from the reference.
Choose continuous stock simulation: frozen v2 drives first, then the ordinary
native controller takes over at a predeclared boundary. Teacher success is
collection coverage, never independent learner success.

Use one fresh refit of the same network and optimizer recipe after augmenting
the training data. Warm-starting v2 would also change initialization and update
schedule. The fixed refit makes the chosen corpus/recipe comparison clearer;
it still changes normalization, minibatches and total optimizer updates.

## Collection contract

Only the original training assignments `pool-90-yaw0` and `pool-110-yaw0` may
supply learner-induced correction states. Keep their original actor parameters,
fixed endpoint, intervals and frozen v2 weights/export. The first control
boundary at or beyond physics steps 150, 600, 1200 and 2400 gives eight assigned
mixed runs. The saved reference identifies handoff ticks 25, 100, 200, 400 for
pool-90 and 39, 154, 308, 616 for pool-110. Freeze each exact tick and all reference
hashes in a declaration before executing any collection.

For handoff tick K, model inputs own `[0,K)` and native inputs own `[K,N)`.
Verify exact prefix observations, applied controls, native controls and decision
journal entries against the frozen v2 reference. The pre-input observation at K
also matches byte-for-byte. There is no neutral input tick. Keep the actual
actor, orientation, velocity, health, breath, held buttons, RNG, graph, clocks,
physics residual and dry-support streak. Preserve the original 9,000-step total
budget from episode start. A terminal before K remains an assigned outcome and
provides no correction rows.

The native planner starts without a fictitious route or objective. Assert its
pristine goal/route/maneuver and world/graph state. Set its progress position and
stuck timer to the current position/clock at takeover, so it does not charge
learner time as its own stall. Passively track only native-style water interval,
previous observed health and previous observed breath debt during model ticks,
then provide that bookkeeping at takeover. Water interval follows the native
control-boundary sector-water rule, including post-advance clock on reentry.
The teacher chooses its own route; never force its objective to the scorer's
endpoint. Do not modify physical state or manufacture a prior AIR route.

Keep worker transport identity separate from the active controller selector.
Model ticks never execute the baseline planner or its debug navigation query.
Native ticks use the same driver/debug path as the baseline. No policy decision
is solicited at or after K. Preserve all five native button bits in evidence;
the learner still predicts only jump and duck. The first teacher tick receives
the actual preceding model-held keys through the stock edge calculation.

Every receipt identifies assignment, frozen controller, reference traces,
handoff reached/step, controller counts, native bookkeeping, exact terminal and
total/suffix physics time. All mixed runs are marked assisted and are excluded
from the original baseline-only loader. Capture every success, physical loss
and infrastructure-censored result. Retry only a diagnosed infrastructure fault,
retaining its first receipt; never substitute for a physical loss.

## Training contract

Audit the whole mixed timeline before extracting rows. A successful teacher
suffix may contribute eligible ticks `[K,min(K+128,N))`; apply the 128-tick cap
before the existing remaining-goal eligibility filter. No model-prefix frame,
failed suffix, incomplete trace or post-cap frame enters fitting. The first
teacher feature uses the previous actual input, even when nonzero. Preserve all
3,431 original training rows in their canonical order; append corrections by
case ID, numeric K and tick, all with unit weight. Eight branches contribute at
most 1,024 extra rows and remain members of the two original pose groups.

If no correction row qualifies, publish the collection result without fitting
an identical corpus. Otherwise fit exactly one `water_recovery_v3` candidate:
17 existing features, 32 hidden units, six outputs, 200 epochs, seed 23,
Adam learning rate 0.01, batch 128 and button threshold 0.5. Reuse the contact
validation/export contract. Recompute normalization from training rows only.
Record every eligible/excluded count, ordered source hash, fit setting and
model/policy digest. Freeze before opening fresh evaluation outcomes.

## Evaluation contract

Seal six fresh pool positions generated by all permutations of barycentric
weights `(1,2,5)/8` over original pool-90, pool-100 and pool-110 XYZ. Each uses
headings -90, 0, 90 and 180 degrees, giving 24 assignments in six pose groups.
Use the prior stress nonspatial settings: 40 ms control, 100 HP, 12,000 ms used
breath, zero pitch/vertical speed, pool edge and flags. Verify binary32 uniqueness
against all older positions and sufficient sphere clearance before declaration.
No controller runs on this fresh set until the new model/export are frozen.

Compare native baseline, frozen v2 and v3 at every original control tick. Run
separate single-policy evaluations, then pair by assigned initial observations,
seed, edge and repeated baseline native/motor hashes; first actions are allowed
to differ between policies. Retain every assigned outcome. Report gains,
regressions, both/neither success per position and overall. The 27 original and
16 earlier perturbation cases are diagnostic/nonregression sets.

A predeclared engineering signal of narrowly scoped progress requires at least
four net additional landings among the 24 fresh starts, positive net gains in
at least three of six positions, no newly failed original shaft assignment
that v2 previously landed, and complete matched evidence. This is not a
statistical significance test or an automatic production promotion gate.
The same known pool and clustered headings limit generalization.

## Verification and publication

Tests must reject moved handoff boundaries, lost held-key edges, changed prefix
or target, post-handoff model decisions, failed/censored training rows and split
leakage. Disabled recovery mode must preserve established pure-controller
traces. Review the fixture and trainer independently. Publish portable tools,
frozen model, every result, source/provenance receipts and a clear checkpoint;
exclude raw retail geometry and host-specific private paths. Check the release
inventory and push the authorized development branch, keeping draft PR #2.
