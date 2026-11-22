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
