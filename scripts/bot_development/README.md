# Bot development tools

These tools preserve the development and measurement work behind the competitive
bot refinements. Their inputs and output directories are explicit command-line
arguments so they can be used from another checkout or machine. Each directory
has its own setup instructions, commands and limits.

| Directory | Purpose |
| --- | --- |
| [capture](capture/README.md) | Run bounded browser trials, retain observations, transcode recordings and verify or transfer local candidate artifacts. |
| [analysis](analysis/README.md) | Analyze fresh observations inside the recorded clip, compare trials and inspect repeated supply approaches or water-column confinement. |
| [verify](verify/README.md) | Check the packaged browser source against its pinned base and independently reproduce the shipped runtime from relink inputs. |
| [legacy](legacy/README.md) | Preserve the earlier native Force observation harness, Windows bridge and limited incremental rebuild helper, with their original scope documented. |

## Custom browser game build

The arena runs a customized **JKWeb game engine in an ordinary installed Chrome**.
The project does not contain a modified Chromium distribution. The source changes
and runnable game-engine outputs are preserved together:

| Artifact | Repository location |
| --- | --- |
| JavaScript and WebAssembly runtime | `bin/bots-jkweb/openjkdf2.js`, `bin/bots-jkweb/openjkdf2.wasm` |
| Complete patch against pinned JKWeb source | `web_bots/engine.patch` |
| Source identity, changed-file hashes and runtime hashes | `web_bots/BUILD.json` |
| Independent relink inputs | `web_bots/engine-relink.tar.gz` |
| Full source build and package helpers | `web_bots/build.sh`, `web_bots/package_engine.py` |
| Arena host, browser controls and Chrome launcher | `web_bots/serve.py`, `web_bots/client.js`, `web_bots/launch_chrome.py` |
| Optional native bot runtime, source patch and build inputs | `bin/bots-linux-x86_64/`, `native/bot-client.patch`, `native/BOT_BUILD.json`, `native/bot-relink-linux-x86_64.tar.gz` |

The November 22 checkpoint audit verified all 28 changed browser-engine source
files against the build manifest. The development checkout's complete binary Git
diff matched the packaged patch byte for byte, and its built JavaScript and
WebAssembly files matched the shipped runtime. The upstream relay is fetched at
its recorded pin by `web_bots/fetch_relay.py`.

## Existing tests and replay tools

The concrete AI tests remain under `native/tests/`. The
[stock movement replay](../../native/tests/stock_water_replay/README.md)
uses a caller-supplied map to test bank escape, water entry and charged jumps.
Python arena and companion regressions remain under `tests/`. Packaging uses
`scripts/build_release.py`; new distributable files must be staged before
refreshing the managed-file manifest and checksums.

See [the continuation record](../../docs/BOTS_CONTINUATION.md) for the trial
sequence, exact runtime identities and next experiment. The fifth refinement
passed four-seat capture checks but failed sustained-movement qualification.
Source regressions and video capture checks establish their stated conditions;
they do not establish reliable navigation through every route or competitive
strength against human players.

## Inputs and generated output

Use local copies of the game data and any optional cosmetic assets. Map geometry,
recordings, raw observation traces, runtime credentials and machine-specific
candidate installations are generated or supplied locally. Consolidated tools
replace the repeated per-trial scripts; the measured trial summaries and build
receipts are retained under `qa/`.
