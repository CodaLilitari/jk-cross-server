# Protected memory learning for Lily

## Purpose and scope

Continue the existing experimental Lily controller with learned temporal state while preserving acquired skills. The previous output-head search achieved all 24 open pool landings but lost one of eight shaft landings. Its null selection remains final. This new experiment asks whether a small, outcome-trained memory correction can repair that tradeoff, and whether carrying history contributes beyond a matched instantaneous correction. Existing bots, v3, G4, and historical evidence remain unchanged. Nothing in this experiment deploys to the live game.

This is a bounded control experiment on two water exits in Canyon Oasis, not a demonstration of combat competence, general adaptation, or necessary partial observability. Relative geometry can distinguish the two families even without explicit identifiers.

## Model and state contract

Freeze the exact previous g04-c11 contact network (canonical SHA256 `83b5d06e4d110d0354c74b74512bbb89f2229d7ae708fc1d4ffac6f816838cf2`). Its normalization, 17-to-32 encoder, six-output head, and output transformations remain unchanged. Compute its six logits. In parallel, pass the existing 17 bounded physical features, before normalization, through four learned units:

```
u = tanh(W x + b)
rho_ref = .995 sigmoid(a)
rho = rho_ref ** (tick_ms / 40)
m = rho m_previous + (1-rho) u
logits = G4_logits + O m
```

W is 4x17, b and a have four entries, and O is 6x4: 100 learned parameters. The matched instantaneous arm sets m=u and holds a fixed, leaving 96 effective parameters. All parameters are finite and bounded by 1,000. Memory components are finite and bounded by one. Both arms use ordinary four-axis, jump/duck inputs, the existing quantizer, the measured surface contact bit and preceding applied jump. No case ID, sector ID, heading index, absolute position, label, teacher, fallback, or family gate enters the neurons. The physical relative goal remains legal input.

Initialize W with PCG64 seed 541123, standard normal divided by sqrt(17); b and O are zero. The initial rho_ref values are .30, .75, .93, .98. Both arms initially reproduce G4's exact quantized controls. The decay exponent uses physical time so that a constant input over two 20-ms updates has the same memory effect as one 40-ms update. This is a leaky memory bank, not a fully coupled recurrent network or free-running oscillator.

The schema-3 model contains its frozen base, mode, residual parameters and provenance. Export is a self-contained ABI-1 Python policy of at most 128 KiB. Explicit context.state contains exactly a state schema, model canonical hash and four memory values. Each episode and independent audit pass begins with zero memory. State is separate from observation.state, which is physical health/shields/mana. The session adapter enforces consecutive tick order, computes before/after state hashes, extracts the returned state, and passes the remaining action to the original codec. At an endpoint within .001 units, wait holds memory and is encoded as the exact state-free wait action. Malformed, wrong-model or nonfinite state fails closed. No module-global mutable state or cross-episode carry is permitted.

The no-history intervention uses the recurrent G8 weights with m=u each tick. It preserves constant-input steady-state response; resetting to zero each tick would also attenuate the residual and is not the chosen intervention. It is a distinct frozen model identity with the same numerical weights.

The original native fixture and nine-byte control packet remain unchanged. New Python execution and audit helpers live outside its frozen directory. The production live SENSE interface lacks measured on_water_surface, so the new model is fixture-only and rejects escape-bank undertakings.

## Search, rehearsal and fixed budget

Run ID: `lily-memory-learning-20261122-01`, with a single create-only live execution path `/tmp/lily-memory-learning-20261122-01` on the regular filesystem. Offline audit may read a relocated copy. Two workers maximum at the execution API boundary, zero retries or resumed attempts. Any invalid or censored attempt stops admission and prevents selection. Preserve all claimed, in-flight and unrun assignments, and any selection or transfer that occurred before a later interruption. No outcomes precede a published source commit and a separately published declaration binding that commit.

1. Calibrate v3 and G4 on the 64 previously exposed training starts and all eight previously exposed development shaft starts: 144 attempts. All eight v3 anchor wins must reproduce. Paired starts, fixed engine/geometry, and prior per-start outcomes must match where corresponding old evidence exists. These are baseline replication, not new held-out data.
2. Train each arm for eight generations, each with its incumbent and four antithetic pairs, on 16 common starts: all eight shaft anchors, six rotating training pool and two rotating training shaft starts. A PCG64 schedule seed 541125 permutes pool and shaft IDs separately; each old training start appears exactly once across eight generations. Each arm receives 1,152 attempts, total 2,304. Draw direction components in generation/direction/W/b/a/O row-major order with PCG64 seed 541124; shared components are identical across arms. Per-entry scales are W=.15/sqrt(17), b=.12, a=.35, O axes=.30/sqrt(4), O buttons=.90/sqrt(4). Halve all scales in generations five through eight. Static candidates ignore a directions. Retain every candidate export before any outcomes for that generation.
3. Disqualify a proposal that loses a v3-winning fixed anchor retained by its own incumbent. The incumbent is always admissible. Rank admissible candidates lexicographically: fewest missing v3 wins across the ten shaft assignments; fewest missing G4 wins across six pool assignments; most supported-dry landings; fewest charged physics steps, charging every failure 9,000. Ties retain declared candidate order, incumbent first. Anchor retention is monotonic; rotating starts provide additional rehearsal, not an assertion of monotonic general retention.
4. Evaluate v3, G4, final static G8, final recurrent G8, and the recurrent no-history intervention on the old 32 development starts: 160 attempts. These starts are now an open, design-informed regression set; the eight shafts were also training anchors. Require v3's exact old 11/24 pool plus 8/8 shaft outcomes and G4's 24/24 plus 7/8 outcomes to reproduce. A candidate qualifies only at 24/24 pool AND 8/8 shaft. If both qualify, choose fewer total charged steps, tie static before recurrent. Intermediate checkpoints cannot be substituted. If neither qualifies, freeze null and stop after 2,608 attempts.
5. Only after a qualifying selection, run all six fixed arms (v3, G4, native, static G8, recurrent G8, recurrent no-history) on the untouched 48 transfer starts: 288 attempts. Run selected and v3 on the old 27 original, 16 stress and 24 recovery diagnostics: 134 attempts. Selection cannot change. Maximum new budget is 3,030, with 422 conditional attempts. The preceding study's unopened 278 remain its own historical fact.

## Evaluation and interpretation

Use the unchanged native oracle: 150-Hz physics, up to 9,000 physics steps, 38 consecutive supported dry steps in the assigned target sector. Water breathing, proximity, touching the target, or merely leaving the water do not count as landing. Record the actual wait results of both processes. Independent reconstruction joins each pre-input observation to the returned quantized action, applied action, rising-edge buttons, native clock, ownership and terminal. Every state hash is recomputed from the frozen export, with a fresh session on each pass. A malformed or contradictory prefix is invalid, not merely censored. A late process failure never becomes a scored success.

For the selected policy, confirmatory progress requires at least four net pool gains against v3 across the 32 transfer pool starts, positive net gains at at least three of eight pool positions, no lost v3 wins on 16 transfer shaft starts, and preservation of the 24 historical original v3 shaft winners. If v3 fails historical replication, the corresponding comparison is inconclusive. Report paired gains, regressions, ties, charged time and position clustering against both v3 and G4.

Separately, evidence that memory improved this policy on this set requires the recurrent policy to beat both the equally trained instantaneous arm and its own no-history intervention in net transfer landings, with positive net differences across at least two positions for each comparison. Disclose every paired outcome and timing regardless of sign. Correlated headings are not independent geometries. A positive result does not identify semantic phases or prove that recurrence is necessary; a negative result does not rule out larger models or different training.

## Reproducibility and publication

Reuse the authenticated prior executable (SHA256 `204ef95913b472b9190aa9b8d74aafff26043f0d8ddfd477f68d43d4ca54dd1f`), numeric geometry and all 101 retained build files. The fresh environment lacks the original retail map and complete engine build. Do not reconstruct proprietary inputs or silently rebuild a different fixture. Record current runtime and validate compatibility by the declared baseline replication. Bind previous declaration, evaluation, build archive, candidate archive, run header, model identities, case files, recipe, sources and all build hashes in the new declaration/header. Keep prior evidence intact.

Use authenticated Git object publication if normal shell push authentication is unavailable. Verify exact blob/tree identities, conditional fast-forward the existing draft PR branch, fetch the canonical commit, and freeze its returned SHA before declaring or executing outcomes. Retain private raw traces durably; publish model exports, scripts, tests, declaration, aggregate evidence and review. Report actual platform skips and limitations. No automatic live promotion, merge, new experiment, or budget extension is implied by a favorable result.
