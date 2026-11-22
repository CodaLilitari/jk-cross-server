# Earlier native development helpers

These helpers preserve the distinct native Force-observation and incremental-build
work from the first competitive-bot development session. Paths and WSL distribution
names are caller supplied. The current browser recording, transfer and analysis
tools live alongside this directory; use those for new four-browser trials.

## Observe two native clients on Linux

```sh
python scripts/bot_development/legacy/native_force_observation.py \
  --repo /path/to/jk-cross-server \
  --data /path/to/owned-jk-installation \
  --output /path/to/new-force-observation \
  --map m_boss17.jkl --duration 75
```

The output directory must be new and outside both inputs. The harness starts one
dedicated server and two real bot clients, verifies their distinct joined
identities and expected stock Force loadouts, and retains bounded numeric
observations in `receipt.json` and `force-trace.jsonl`. It copies the required game
files into a temporary private directory and cleans up its own process groups.
The original game installation is read only. Raw process logs remain in the
caller-selected output directory.

This is a Linux x86-64 native test with software/offscreen rendering and an overall
172-second deadline. It requires the packaged native server, bot and runtime
libraries. It does not qualify browser networking, rendering quality, successful
casts attributable to a specific player, or competitive skill.

## Stage an owned Windows installation through WSL

```powershell
python scripts/bot_development/legacy/windows_force_bridge.py --distro "Your WSL Distribution" --data "C:\Games\JediKnight" --repo /path/to/jk-cross-server --output /path/to/new-force-observation --map m_boss17.jkl --duration 75
```

The repository must already exist inside the named WSL distribution. `--repo` and
`--output` are absolute Linux paths; the output parent must exist. `--harness`
defaults to the sibling `native_force_observation.py`. The bridge hashes that file
before sending it and the receiver verifies the same digest before execution.

The bridge checks native runtime libraries, streams only four allowlisted game
files and the observation harness over WSL's standard input, and runs the test in
a temporary user/network namespace containing only loopback. WSL must support
`unshare -Urn`. It performs no clone, download or upload. The original Windows
installation is read only; the Linux output directory retains the numeric receipt
and process logs. Total bridge time is bounded to 300 seconds.

## Rebuild the two original native translation units

```sh
python scripts/bot_development/legacy/rebuild_native_pair.py \
  --repo /path/to/jk-cross-server \
  --source /path/to/pinned-and-patched-native-engine \
  --build-dir /path/to/configured-native-build \
  --sdl-source /path/to/pinned-sdl-checkout \
  --output /path/to/new-pair-build
```

This deliberately narrow helper rebuilds `src/AI/jkBot.c` and
`src/Gui/jkGUIMultiplayer.c`, then links them with the verified remaining object
files from `native/bot-relink-linux-x86_64.tar.gz`. It requires the original Unix
Makefiles flags, generated header, pinned SDL revision and compatible Linux
compiler/linker. The output must be outside all inputs and must not already exist.
It checks source and archive pins, hashes all retained link inputs, verifies the
expected GUI symbols and rejects recorded source changes outside the rebuilt
dependency set. It writes build receipts and an executable only in that new
directory. It does not refresh release manifests or replace packaged binaries.

The primary reproducible full build remains `native/build_bots.sh`. Use it for
changes spanning other translation units. This historical two-unit diagnostic
was retained because it reproduces the earlier bounded incremental build and is
useful when checking that particular recovery path.

## Provenance and disposition of earlier scratch helpers

| Earlier helper | Preserved form or replacement |
| --- | --- |
| `competitive-force-harness.py` | `native_force_observation.py`; behavior retained, explanatory module description updated. |
| `competitive-force-windows-bridge.py` | `windows_force_bridge.py`; fixed machine paths, distribution, output and harness digest replaced by explicit arguments and a per-run digest. |
| `engine-build-probe/rebuild_pair.py` | `rebuild_native_pair.py`; build/SDL paths are arguments; integrity checks remain active under optimized Python. |
| `engine-build-probe/rebuild_unit.py` | The verified pair builder supersedes this unverified one-unit experiment. |
| `receive_demo.py` | The shared bounded packet-transfer helper handles chunk offsets, sizes and digests without the old terminal-mode dependency. |
| `demo-review/analyze_speedvideo.py`, `analyze_trial.py`, `compare_runs.py` | Preserved in the adjacent analysis tools with caller-supplied inputs. |
| Earlier `record-*`, `transcode-*`, `export-*`, `prepare_private_update.py`, `install-private-update.py` | The shared capture/transfer tools preserve these operations with explicit inputs; per-recording paths and historical overlay payloads are not duplicate tool entry points. |
| `demo-review/companion-refinement-control.py` | `bots.companion_cli` already exposes the observation, lease, strategy and chat operations used by this recording-specific wrapper. |
| Intermediate combat, pickup, host/join and companion patch fragments | Their final source is included in `native/bot-client.patch` and `web_bots/engine.patch`; superseded fragments and baseline source snapshots are not separate runtime variants. |
| `current-jkweb-relay.py` | Unmodified upstream relay at the pin documented in `web_bots/README.md`. |
| Object directories, generated JS copies, SDKs and relink scripts inside build outputs | Current runtime files, build instructions and verified relink inputs are already packaged. |

Original helper SHA-256 values, before portability changes:

| Original | SHA-256 |
| --- | --- |
| Native Force harness | `99af029eca3084482f9842086606aef7019e98c9b1b855d01d929ff39a28df9d` |
| Windows/WSL bridge | `9aef0cf3a87094ac31bab1313909140d1a988a93f02bea37802d41dced0262ad` |
| Native pair rebuild | `475fd22c6f4d08608f32b38e531d7e7d00ea79ff3d696e4498ada27ccaa53394` |

The preservation check ran the ported pair builder against the fifth refinement
sources and reproduced the packaged native executable byte for byte:
`862e566209dae8fab218243a47455b5a5616bf98fb8d1f09fa65969f9c8519aa`.
CLI parsing, embedded WSL program compilation, literal argument transport,
allowlisted archive creation, digest rejection and malformed-response handling
were checked locally. The ported Windows bridge was not rerun as a live WSL match.
