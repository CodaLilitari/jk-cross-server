# Stock water replay

Use this Linux fixture to replay an observed swimmer state on an owned Canyon Oasis map. It runs one bot control update per chosen control frame and 150 physics steps per game second. It succeeds after the actor stays attached to a floor in the requested dry sector for 38 consecutive physics steps. Drowning, an unavailable exit edge, or 60 simulated seconds without a supported landing fail the run.

Provide a patched JKWeb engine checkout with its dependency headers, the native CMake build directory used by the other bot tests, and your own extracted Canyon Oasis JKL. The build directory must contain `CMakeFiles/sith_engine.dir/flags.make` and the generated headers referenced by its include paths. Run from the repository root. Set the shell variables below from the observed state, using game units for position and vertical speed, degrees for pitch and yaw, hexadecimal for physics flags, and milliseconds for endurance.

```sh
python3 native/tests/stock_water_replay/run.py \
  --source "$PATCHED_WEB_SOURCE" --build "$NATIVE_BUILD" --map "$OWNED_JKL" \
  --position "$X" "$Y" "$Z" --control-hz "$CONTROL_HZ" \
  --flags "$PHYSICS_FLAGS" --health "$HEALTH" --endurance-ms "$ENDURANCE_MS" \
  --pitch "$PITCH" --yaw "$YAW_OFFSET" --vertical-speed "$VERTICAL_SPEED"
```

The default Canyon Oasis setup builds the graph from spawn sector 41, selects an exit edge from sector 54 to sector 41, and starts the swimmer in sector 54. Set `--start-sector` if the observed swimmer occupies a different underwater sector from the selected exit edge. The actor starts at the supplied position with zero horizontal velocity. Yaw zero points along the selected wet-to-dry graph edge. The replay uses these assumptions for the three pool captures below.

Use either `--control-hz` for the existing 15, 20, 30, or 60 Hz cases or `--control-dt` for a measured interval in seconds. The replay holds that interval constant. It accepts intervals from one 150 Hz physics step through the bot's 0.25 second frame limit.

For the three pool captures below, use `--origin 41 --wet 44 --dry 10 --start-sector 42 --flags cb4f --yaw 0` with each row's arguments. Sector 44 supplies the exit edge and heading. The swimmer starts in sector 42 and must reach sustained floor attachment in sector 10.

| Capture (s) | `--position` | `--control-dt` | `--health` | `--endurance-ms` | `--pitch` | `--vertical-speed` |
|---|---|---:|---:|---:|---:|---:|
| 90 | `-1.946 1.935 -.276` | .040 | 100 | 15480 | 2.9 | .001 |
| 100 | `-1.873 1.848 -.349` | .079 | 70 | 19473 | 15.6 | .003 |
| 110 | `-1.798 1.874 -.312` | .026 | 20 | 19526 | 12.7 | .037 |

The fixture uses the stock player size, standing height, air drag, and thrust. The bot's underwater timer starts at 20 seconds so these cases exercise air recovery. The supplied endurance governs drowning. A fresh dive's first choice of an air objective is outside the scope of this fixture.

The runner extracts the required stock control, movement, sector transition and endurance functions from the supplied source checkout. Physics and world collision code come from that checkout as well. The map conversion, generated C include and executable live in a temporary directory. Rendering, sound, inventory powers, multiplayer transport and other players are outside this fixture. The actor begins with the specified health, and the damage callback deducts the stock actor timer's damage directly.

Look for `BREATH` (endurance reset), `TRANSITION` (a sector or surface flag change) and `SUPPORTED_DRY` (sustained floor attachment). The process exit code reports the final result.

## Applied-control demonstrations and live policy probe

`run.py --trace-out PRIVATE.jsonl --episode-id UNIQUE_ID` records the selected
ordinary movement controls before stock input handling, plus the independent
supported-dry terminal. `collect_motor.py` compiles once and records the full
matrix in a new private directory. It groups yaw variants of one captured pose
for a training split. These demonstrations use the existing autonomous controller.

`live_policy.py --source SOURCE --build BUILD --map OWNED_JKL --output NEW_PRIVATE_DIR`
runs a separate 30-second, wall-paced integration probe. It uses a real native
companion socket, authenticated loopback HTTP, the supervisor CLI and isolated
policy processes. The probe lets baseline navigation finish swimming or airborne
movement, sends ordinary motor controls on supported dry ground, swaps executable
policy source, rejects an invalid candidate and checks baseline return after the
controller stops. It writes an explicit receipt and retains private logs. Rendering,
opponents and stock inventory/Force scripts remain outside this fixture.

See [the motor learning report](../../../docs/LILY_MOTOR_LEARNING.md) for the
measured candidate, scope and reproduction commands.

## Bank landing regression cases

`bank_cases.tsv` supplies the six later swimmer poses at four initial yaw offsets and the three earlier sector-42 controls at their recorded test heading. Every row must establish 38 consecutive supported dry steps in its requested sector before the deadline. To run the full matrix from the repository root in Bash, set the three paths as above and run the following.

```bash
set -eu
fixture=native/tests/stock_water_replay
while IFS=$'\t' read -r id origin wet dry start x y z dt flags hp endurance pitch vz yaws; do
    for yaw in ${yaws//,/ }; do
        echo "$id yaw=$yaw"
        python3 -B "$fixture/run.py" --source "$PATCHED_WEB_SOURCE" \
            --build "$NATIVE_BUILD" --map "$OWNED_JKL" --origin "$origin" \
            --wet "$wet" --dry "$dry" --start-sector "$start" --position "$x" "$y" "$z" \
            --control-dt "$dt" --flags "$flags" --health "$hp" --endurance-ms "$endurance" \
            --pitch "$pitch" --yaw "$yaw" --vertical-speed "$vz"
    done
done < <(tail -n +2 "$fixture/bank_cases.tsv")
```

## Matched bank evaluation

Run the unchanged autonomous controller and the checked-in movement clone on
the same 27 assigned case/yaw pairs. The optional `--episode` argument selects
one case/yaw ID (for example, `boba-190.017-yaw0`) for a paired smoke run.

```bash
python3 native/tests/stock_water_replay/evaluate_bank.py \
    --source "$PATCHED_WEB_SOURCE" --build "$NATIVE_BUILD" --map "$OWNED_JKL" \
    --output "$NEW_PRIVATE_DIRECTORY" --workers 4
```

Each candidate gets its own real-time engine, loopback companion, fenced
`escape-bank` directive, supervisor, policy worker and fresh database. The
directive uses the actual destination node selected by the fixture. The native
baseline advances the same sequence of control and 150 Hz stock physics steps
without wall-clock pacing. A simulated timeout ends on step 9,000. First breath
means the first observed transition from positive breath usage to zero.

The evaluator-only build observes the return from the native control selector
before end-of-frame cleanup clears a completed action. Its wrapper calls the
original selector once and returns the original result. Each native control
frame records the applied axes, buttons, control tick, water flag, action
sequence, revision, sample and fence. `applied.jsonl` joins actual motor ticks
to the supervisor's bank task, action identity and full policy digest. An
unmatched motor or missing frame makes controller attribution unknown.
Neutral boundary frames have a distinct owner. The baseline-only demonstration
writer is disabled whenever the adaptive seat is enabled.

The private output keeps all assigned rows in `receipt.json`, including
configuration failures and timeouts. `physical_success` uses the native
landing/death/time oracle. `controller_success` also requires complete
ownership, actual wet takeover by a candidate, and freedom from baseline
assistance for that candidate. The summary reports the model's five original
holdouts separately. A physical loss counts as a completed trial. The process
returns nonzero if one or more trials lack a physical verdict. Publish the
sanitized receipt after review. The per-case traces, databases and engine logs
contain private fixture evidence.

## Independent motor cadence

The synchronous fixture measures a frozen movement model with exclusive control
from the first input through the physical terminal. It bypasses the deployed
Supervisor, live observations, handover checks and native baseline decisions.
The baseline arm runs the existing driver. Both arms use the same stock look,
movement, freecam, collision, damage and 150 Hz physics functions.

```sh
python3 -B native/tests/stock_water_replay/evaluate_motor.py \
    --source /path/to/patched-engine --build /path/to/configured-build \
    --map /path/to/m10.jkl --output /new/private/output
```

The default matrix runs the baseline and three independent schedules on all 27
case/yaw assignments. At 41 ms per original control tick, the 550 ms, 100 ms
and every-tick schedules hold one decision for 14, 3 and 1 ticks respectively.
The original tick interval remains a model feature. A new decision starts a
fresh hold. A wait applies zero input. The trial ends immediately on death,
38 consecutive target-sector floor-supported dry physics steps, or the
9,000-step budget. Use `--episode boba-190.017-yaw0` for a subset. An alternate
fixture policy and its matching weights use `--policy` and `--model`. A separate
perturbation TSV can use `--cases /path/to/cases.tsv --arms baseline,every_tick`.
Workers default to four.

Each private trial directory contains:

- `start.json` identifies the selected wet node. The scorer uses its position
  and the assigned dry endpoint to independently reconstruct the expected
  starting heading at the requested yaw. It also checks the first actor pose,
  time interval, health and physical flags against the TSV.
- `motor.jsonl` alternates a pre-input `observation` with the actual `input`
  for every original control tick. Both carry the tick and elapsed physics
  step. The observation contains the fixed goal, sector, physics flags, health,
  shields, mana, body orientation, motion, head pitch, medium, support and
  breath used. `sense.on_water_surface` comes from the stock physics flag and
  `sense.buttons` records the previous actual button mask, initially zero.
  The input carries the owning controller, decision source tick, four applied
  axes, buttons and rising presses. Button bits 0 and 1 are jump and duck.
- `decisions.jsonl` on a model arm binds each worker decision to the digest
  of its exact observation bytes. The worker sends one fixed-size tick-identified
  packet through a local sequenced-packet socket. Axes pass through the production
  signed-hundredths codec. Each exchange has one absolute one-second deadline.
  Disconnection, timeout or invalid input censors the trial.
- `native.jsonl` contains the established per-frame bank control trace and
  physical terminal. For canonical baseline trials its complete bytes must match
  the digest in `qa/lily-bank-task.json`. `engine.log` and, on model arms,
  `worker.log` retain diagnostics.

The root `receipt.json` includes assigned rows, observed owning ticks, per-arm
hold lengths, raw evidence hashes and build provenance. A completed simulation
timeout or death is a physical loss. Missing evidence and infrastructure
failures retain their assignment and a null physical result. Trials run without
wall pacing; elapsed performance is reported in simulated seconds. These
measurements do not establish deployed wet handovers or multiplayer performance.

For native boundary tests, set `LILY_TEST_SOURCE`, `LILY_TEST_BUILD` and
`LILY_TEST_MAP` to the corresponding inputs above and run
`python3 -m unittest discover -s tests -p test_lily_independent_motor.py -v`.

## Continuous corrective recovery

Run the eight declared branches against the original frozen v2 matrix. Each
assignment starts the actor at its original pose and runs a fresh process.
The worker supplies every model tick up to the declared handoff. The ordinary
native planner takes its first decision at that boundary using the held input,
stock physics state and remaining time from the same episode.

```sh
python3 -B native/tests/stock_water_replay/collect_recovery.py \
    --source /path/to/patched-engine --build /path/to/configured-build \
    --map /path/to/m10.jkl --reference /path/to/original-v2-matrix \
    --declaration qa/lily-recovery-declaration.json --output /new/private/collection
```

Each branch records the normal start, motor, decision and native traces.
`process.json` retains the actual engine and worker exit codes and any timeout.
A late process failure retains the native terminal as a diagnostic and makes
the branch ineligible for training. Bookkeeping at takeover is recorded in
`handoff.json`. This file records the planner checks, RNG, held buttons,
control clock, and the exact before/after values of the five bookkeeping
fields initialized at takeover. The native driver selects its own objective.
A run ending before its handoff has a `reached: false` record. The total
budget is 9,000 physics steps from spawn. All landings in the collection
are assisted outcomes.

`assess_recovery(output, reference, declaration)` verifies the assignment
matrix, frozen model and build identities, full reference file digests, exact
model prefix and boundary observation, ownership, held-key edges and physical
terminal. Its rows carry the verified `teacher_start_tick`, total
`control_ticks`, measured physics bounds and evidence hashes. Training may
consume the bounded suffix of a successfully recovered branch. An infrastructure
failure records a null physical result in its assigned slot. Each invocation
uses a new directory and preserves the initial attempt.

The private output directory retains `recovery-replay`, the compiled executable
used for every branch. Re-audit checks its bytes against the build digest and
the recorded fixture source manifest against the matching collector checkout.
These checks identify the archived artifacts. Historical execution depends on
the collection environment.
