# Bot trial analysis helpers

These tools preserve the analysis used for the Canyon Oasis bot refinements. They take explicit input paths instead of depending on the original development machine. They use Python 3.11 or newer and the standard library; `export_numeric_map.py` also imports the existing repository map parser.

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
