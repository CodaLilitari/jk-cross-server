# Bot trial analysis helpers

These tools preserve the analysis used for the Canyon Oasis bot refinements. They take explicit input paths instead of depending on the original development machine. They use Python 3.11 or newer. Most use the standard library; the independent motor failure audit needs NumPy and SciPy, and the optional public-footage extractor needs `yt-dlp` and FFmpeg. The geometry tools also import the existing repository map parser.

Keep your map exports, telemetry and generated reports outside the checkout. The source tools contain no retail map, model, recording or companion credentials. Run the commands below from the repository root, with the quoted variables set to your own files.

## Inputs and recording window

The current reports consume a gzip-compressed JSON trial wrapper with `result`, `qualification`, `observations` and `directed_commands` sections. `result` identifies the runtime and supplies the recorder-call start/return times and captured duration. Each observation supplies its poll time, native-driver activity, own-state age, world/life epochs and game state. The qualification console carries the native equipment/fire/status messages.

Current clip analysis keeps driver-active publications with an age from zero through one second, deduplicates by world, life and game time, and clips to the intersection of the possible recording windows: recorder return through recorder-call start plus capture duration. Displayed clip times are relative to the recorder-call midpoint. The maximum clock uncertainty from that bracket remains relevant when comparing a frame with telemetry.

Geometry-dependent analysis accepts the numeric format already used by `native/tests/stock_water_replay/geometry.py`. Export it from your own extracted JKL:

```sh
python scripts/bot_development/analysis/export_numeric_map.py \
  "$OWNED_JKL" "$BOT_MAP_NUMERIC"
```

The numeric export contains map geometry and entity data; it is a local input, not a distributable tool artifact.

Validate predeclared stock-replay starts without running a controller:

```sh
python scripts/bot_development/analysis/validate_replay_poses.py \
  --source "$PATCHED_NATIVE_SOURCE" --map "$OWNED_JKL" \
  --cases qa/lily-motor-stress-cases.tsv --output "$POSE_GEOMETRY_RECEIPT"
```

This helper reads the engine's collision and movement-adjoin flags and requires
the entire 0.065-radius actor sphere to clear every relevant sector plane, with
a conservative rounding allowance. It records map, source and case hashes and
per-case clearance, without copying geometry to the receipt. It establishes a
sufficient geometry check for a declared starting sphere; it does not measure
bank reachability or controller performance. The
[perturbation declaration](../../../qa/lily-motor-stress-plan.json) freezes eight
nearby poses and both headings before contact-model fitting or stress outcomes.

## Current refinement reports

Generate a detailed gameplay report. This records sampled environment, selected weapons, equipment messages, requested fire modes, ammunition increases, scores, and intervals of little horizontal movement:

```sh
python scripts/bot_development/analysis/analyze_gameplay.py \
  "$TRIAL_GZ" "$DETAIL_JSON" --map "$BOT_MAP_NUMERIC"
```

Add `--verbose` to print the original human-readable diagnostic summary. A living actor remaining within 0.13 horizontal world units for at least two seconds is a candidate confinement interval. Life changes, deaths, observation gaps, and movement outside that radius break the interval.

Compare any number of matching trace/detail pairs:

```sh
python scripts/bot_development/analysis/compare_gameplay.py "$COMPARISON_JSON" \
  --run "$FIRST_TRIAL_GZ" "$FIRST_DETAIL_JSON" \
  --run "$SECOND_TRIAL_GZ" "$SECOND_DETAIL_JSON"
```

Inspect prolonged visits to a sector. The default `--sector 54` preserves the Canyon Oasis shaft analysis. The report keys include the selected sector number. A visit must last at least six sampled seconds and have unambiguous membership in that sector:

```sh
python scripts/bot_development/analysis/review_column.py \
  --map "$BOT_MAP_NUMERIC" --sector 54 "$TRIAL_GZ" > "$COLUMN_JSON"
```

Inspect equipment choices, observed bank returns, and subsequent entries during each native `failed-approach` retry window:

```sh
python scripts/bot_development/analysis/analyze_approach_windows.py \
  "$TRIAL_GZ" "$DETAIL_JSON" --map "$BOT_MAP_NUMERIC" > "$WINDOWS_JSON"
```

Add sampled health, shields, ammunition and recent equipment plans to selected seats' prolonged sector visits. The column report can contain several trials; the tool requires exactly one label matching the supplied trace:

```sh
python scripts/bot_development/analysis/inspect_pool_context.py \
  "$TRIAL_GZ" "$DETAIL_JSON" "$COLUMN_JSON" "$POOL_CONTEXT_JSON" \
  --map "$BOT_MAP_NUMERIC" --sector 54 --bank 41 --seat boba --seat jan
```

Sector and bank numbers are map-specific. Change them for another map; their defaults describe the checked Canyon Oasis route.

## Independent motor failure audit

Compare the frozen contact candidate's nine stress timeouts and all three
original pool starts against the corresponding v1 and baseline trajectories:

```sh
python scripts/bot_development/analysis/audit_motor_failures.py \
  --original-v1 "$PRIVATE_V1_CADENCE" \
  --original-contact "$PRIVATE_CONTACT_ORIGINAL" \
  --stress-v1 "$PRIVATE_V1_STRESS" \
  --stress-contact "$PRIVATE_CONTACT_STRESS" \
  --output "$MOTOR_FAILURE_AUDIT"
```

This helper verifies the pinned case/model identities and motor trace hashes.
It records actual surface jump presses, visited sectors, nonzero inputs,
horizontal progress and distance to the training trajectories. It also checks
the engine's 150 Hz transition log for sectors visited between control samples.
The [published audit](../../../qa/lily-contact-failures.json) includes all twelve
selected cases and all three controller arms, plus definitions and input hashes.

The first and final five-second windows belong to each arm's own trajectory;
successful and failed runs can be in different task phases. Distance to training
is descriptive, not a calibrated confidence threshold. A fresh surface jump
press does not establish an impulse or successful landing. This is post-result
diagnosis; it does not change a model or produce new held-out evidence.

## Earlier diagnostic methods retained

`analyze_speedvideo.py` computes clip-bounded power observations, sampled activation intervals and score changes. Its JSON includes a detailed method statement and clock uncertainty:

```sh
python scripts/bot_development/analysis/analyze_speedvideo.py \
  "$TRIAL_GZ" > "$POWER_JSON"
```

`analyze_trial.py` preserves the early whole-session wet-episode and Force observation report. Unlike the current refinement analysis, it does not deduplicate publications or use the video clip bracket:

```sh
python scripts/bot_development/analysis/analyze_trial.py \
  "$TRIAL_GZ" --map "$BOT_MAP_NUMERIC" > "$WET_EPISODES_JSON"
```

`compare_legacy_runs.py` preserves the early comparison using the first 120 seconds after all seats publish fresh observations. It uses the older polling and horizontal-confinement method, without the later world/life continuity checks. Use it to reproduce those historical receipts; use `compare_gameplay.py` for the current refinement method:

```sh
python scripts/bot_development/analysis/compare_legacy_runs.py \
  "$FIRST_TRIAL_GZ" "$SECOND_TRIAL_GZ" > "$LEGACY_COMPARISON_JSON"
```

## Human match references

Two helpers preserve the public-footage review method without packaging the
recordings. Both require a new output directory outside the checkout.

Collect official seek previews and their nominal timestamp index with the
standard library:

```sh
python scripts/bot_development/analysis/review_youtube_previews.py \
  --video XfU43kYxC88 --start 120 --end 180 --output "$NEW_PREVIEW_DIRECTORY"
```

For a playable public excerpt, supply `yt-dlp` and FFmpeg. This helper ignores
`yt-dlp` configuration, uses no cookies or browser session, limits each request to
five minutes, and writes one-second samples, contact sheets and a hashed manifest:

```sh
python scripts/bot_development/analysis/sample_public_match.py \
  'https://www.youtube.com/watch?v=1dCC8uMLdjo' 370 410 "$NEW_CLIP_DIRECTORY"
```

An inaccessible stream remains inaccessible; the helper does not attempt login.
Preview timestamps and decoded sample times are nominal. Sparse stills cannot
establish input order, exact Force timing, hit confirmation or hidden inventory.
See the [bounded human reference review](../../../docs/reviews/2026-11-22-human-oasis-reference.md)
for the actual observations and their limits.

## Evidence limits

Sector membership comes from sampled actor-center coordinates, with the original geometry tolerance. It does not prove floor attachment, body clearance, a completed bank landing, breath remaining, or a successful weapon hit. Position on a shared boundary can be ambiguous. Fire messages record requested inputs; ammunition increases and score changes do not identify their cause. Confinement intervals can include intentional pauses, combat effects or steering failure. Unseeded bot matches do not establish causal performance improvement or strength against human opponents.

The scripts expect complete, qualified trace wrappers and the corresponding map/build. A failed or incomplete capture may lack the fields necessary to analyze it. Raw exported traces can contain local paths or in-game messages; inspect any report before publishing it.

## Provenance and portability verification

| Preserved development helper | Portable tool |
| --- | --- |
| `refinement-gameplay-analysis.py` | `analyze_gameplay.py` |
| `refinement-gameplay-compare.py` | `compare_gameplay.py` |
| `refinement-column-review.py` | `review_column.py` |
| `refinement-approach-windows.py` | `analyze_approach_windows.py` |
| `refinement4-pool-evidence.py` | `inspect_pool_context.py` |
| `analyze_speedvideo.py` | `analyze_speedvideo.py` |
| `analyze_trial.py` | `analyze_trial.py` |
| `compare_runs.py` | `compare_legacy_runs.py` |

The portability changes preserve the analysis logic and existing output keys for the original sector defaults. The pool-context helper now resolves the matching trial label instead of assuming that the last column summary is the desired trial. `export_numeric_map.py` is a thin CLI around the existing stock replay exporter.

Portability verification on 2026-11-22 ran all nine `--help` interfaces and compiled each script. Regenerated C2–C5 gameplay reports, their combined gameplay and sector comparisons, the C5 failed-approach windows, and C4 pool context matched the retained parsed JSON exactly (eight comparisons). The three earlier analyzers matched the original scripts on the same C5 trace. Exporting the owned test map reproduced the prior numeric input byte for byte. These checks verify preservation of the diagnostic tools; they do not add a new live gameplay qualification.

## Frozen recovery evaluation

Rebuild the v2/v3 comparison on the 24 fresh, 27 original and 16 earlier
stress starts. Supply the six completed independent evaluation directories and
the original and recovery evidence directories. Each argument identifies a set
and model role. The auditor checks that role against the frozen hashes, including
the distinct TSVs for the two sets recorded by the evaluator as `perturbation`.
Use a new output filename.

```sh
python scripts/bot_development/analysis/audit_recovery_learning.py \
  --fresh-v2 "$FRESH_V2_DIR" --fresh-v3 "$FRESH_V3_DIR" \
  --original-v2 "$ORIGINAL_V2_DIR" --original-v3 "$ORIGINAL_V3_DIR" \
  --stress-v2 "$STRESS_V2_DIR" --stress-v3 "$STRESS_V3_DIR" \
  --reference "$ORIGINAL_V2_REFERENCE_DIR" --collection "$RECOVERY_COLLECTION_DIR" \
  --output "$NEW_EVALUATION_JSON"
```

The audit reconstructs the frozen training matrix without fitting. It replays
the v2 collection prefixes, joins each evaluation's observations to its actual
applied controls and native terminal, reruns the standalone policy on the
decision journal, and checks repeated baseline trace lengths and digests.
The receipt retains all six source receipts, raw-file digests, per-heading
results, per-position transitions, old v2 trajectory comparisons and the
predeclared criterion. Counts distinguish the 268 scheduled executions from
the 201 controller/start configurations and the 67 repeated baseline runs.
Collection branches are counted separately.

A physical timeout or death remains a loss regardless of native or model
success on the same assignment. A reported infrastructure censor retains its
reason and available raw evidence and makes the experiment inconclusive.
A missing assignment, pending evaluation or evidence contradiction stops the
audit. A completed measurement that misses an engineering threshold still
produces a valid receipt. The native terminal recorder supplies the 38-step
support streak. The 150 Hz support history and per-process OS exit status were
not separately archived for the independent evaluations. Executable hashes
are those captured by each evaluator during its temporary build.

## Autonomous outcome-learning experiment

The fixed [outcome checkpoint](../../../docs/reviews/2026-11-22-lily-outcome-learning-checkpoint.md)
adds an unaided neural output-head search while retaining the stock fixture.
`declare_outcome_poses.py` creates the geometry-only split proposal;
`run_outcome_learning.py` owns the fixed train/select/evaluate stages;
`outcome_rollouts.py` verifies actual process and physical evidence; and
`outcome_build_inputs.py` binds the compiled external project dependencies.
`audit_outcome_learning.py` independently reconstructs the retained experiment.

The committed declaration fixes one run ID, all seeds, 832 training executions,
96 development executions, and conditional sealed/diagnostic stages. Attempt and
stage claims are exclusive. There is no retry, resume, alternative output ID,
parameter-tuning CLI or outcome-dependent extension. A fresh reproduction needs
an empty canonical run path and the declared source/build/map inputs. Existing
recorded evidence should be audited using the restore procedure in the checkpoint.

```sh
python3 -B -m scripts.bot_development.analysis.run_outcome_learning train \
  --declaration qa/lily-outcome-declaration.json \
  --output /dev/shm/lily-outcome-learning-20261122-01 \
  --source "$PATCHED_NATIVE_SOURCE" --build "$NATIVE_BUILD" \
  --map "$OWNED_JKL" --workers 2
python3 -B -m scripts.bot_development.analysis.run_outcome_learning select \
  --declaration qa/lily-outcome-declaration.json \
  --output /dev/shm/lily-outcome-learning-20261122-01 --workers 2
```

The recorded experiment selected no checkpoint: both G4 and G8 achieved 24/24
pool development landings but lost one protected shaft win. It stopped after
928 complete attempts. Do not run `evaluate` for this null selection. The audit
is read-only and works with a restored run path:

```sh
python3 -B -m scripts.bot_development.analysis.audit_outcome_learning \
  --declaration qa/lily-outcome-declaration.json --run "$RESTORED_RUN" \
  --output "$NEW_AUDIT_JSON"
```

The two public compressed bundles preserve all 105 measured model/export
artifacts and all 96 project build inputs, respectively. The latter includes its
two license notices; extract only `build/*` into the restored run. Raw attempts,
owned numeric geometry and the measured replay are kept in the private evidence
archive. The three payloads reconstruct all 7,765 original files; archive digests
and measured validation are recorded in
[`qa/lily-outcome-validation.json`](../../../qa/lily-outcome-validation.json).

## Protected paired memory experiment

The [memory checkpoint](../../../docs/reviews/2026-11-22-lily-memory-learning-checkpoint.md)
adds a four-unit learned residual over frozen G4, explicit per-episode state,
equally budgeted static/recurrent searches and protected rehearsal. The existing
native fixture and earlier model artifacts remain unchanged.

`run_memory_learning.py` binds the exact source, retained executable, schedule
and candidate lineage to one create-only run. `memory_rollouts.py` carries and
records state, joins exported actions to native controls and rejects invalid
or contradictory evidence. `audit_memory_learning.py` reconstructs the retained
run without launching a game. It preserves actual selection and transfer
attempts even when execution is incomplete in its covered paths. The recorded
diagonal-heading exception exposed an uncovered partial-report path: the
frozen CLI exits before writing JSON. That failure is retained explicitly.

The recorded result is **static selected, transfer inconclusive**. Both trained
arms achieved 32/32 open landings; static used 45,889 charged steps, recurrent
57,099 and recurrent with history removed 56,081. The open shafts are training
anchors and the pools are design-informed regression cases. All 2,608 preceding
assignments completed, then two diagonal-yaw reference attempts failed the
frozen heading validator. The native lookup-table arithmetic explains the
rejection. The 286 other sealed assignments and 134 conditional diagnostics did
not run. Do not restart or resume this declared execution.

Restore the private evidence and the two public overlays as described in the
checkpoint. The unchanged build archive's license notices are additional files;
only `build/*` should be extracted into the raw run. A distinct post-run
`report_memory_failure.py` invokes the frozen reconstruction, preserves its
verified completed prefix and independently reproduces both invalid exception
records. It does not change heading tolerances, accept invalid scores or claim
that the original CLI passed. To generate that read-only supplemental report:

```sh
python3 -B -m scripts.bot_development.analysis.report_memory_failure \
  --declaration qa/lily-memory-declaration.json --run "$RESTORED_MEMORY_RUN" \
  --output "$NEW_AUDIT_JSON"
```

The expected result remains `inconclusive`; there are zero scoreable transfer
attempts. Write audit output outside the raw run. Do not replace the committed
report or change the original invalid receipts after adjusting a validator.
Invoking the original `audit_memory_learning` with the same arguments reproduces
exit 1 and `incorrect_initial_heading`, without a final JSON report. The
[audit-failure analysis](../../../docs/reviews/2026-11-22-lily-memory-audit-failure.md)
documents both the exception-boundary fault and the invalid-row schema gap.

The post-run `preserve_memory_learning.py` helper creates disjoint, deterministic
archives and a receipt, then compares every member's bytes and mode with the
original. It authenticates the reused build archive, rejects links and unsafe
paths, checks complete model/export pairs and keeps the executable and numeric
geometry in the private archive. All three outputs must be new paths outside
the immutable run:

```sh
python3 -B -m scripts.bot_development.analysis.preserve_memory_learning \
  --run "$RESTORED_MEMORY_RUN" \
  --build qa/lily-outcome-build-inputs.tar.gz \
  --candidates "$NEW_PUBLIC_MODEL_ARCHIVE" \
  --evidence "$NEW_PRIVATE_EVIDENCE_ARCHIVE" \
  --receipt "$NEW_PRESERVATION_RECEIPT"
```

It does not execute or score episodes. Public/private archive identities and the
exact reconstructed inventory are recorded in
[`qa/lily-memory-preservation.json`](../../../qa/lily-memory-preservation.json).
The [heading investigation](../../../docs/reviews/2026-11-22-lily-memory-heading-investigation.md)
sets out the prospective numerical correction and synthetic tests; that
correction was not applied to this frozen study.
