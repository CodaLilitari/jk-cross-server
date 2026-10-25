# Native dedicated server

The server is built from [codalilitari/OpenJKDF2-MotS-Fixes](https://gitlab.com/codalilitari/OpenJKDF2-MotS-Fixes), pinned to **74e4657c4f1751d09af9ad9e056acb8f41997acb** (v0.9.9), plus `crossplay-dedicated.patch`. All engine changes are on the server. The ordinary native client still uses its existing Valve GameNetworkingSockets transport. The Python supervisor adds original DirectPlay and browser endpoints through a local transport bridge.

The bundled `bin/linux-x86_64/openjkdf2` and `libGameNetworkingSockets.so` were built on Ubuntu 24.04 x86_64 with GCC 13.3.0. `BUILD.json` records exact source/dependency commits, hashes, sizes, and system library dependencies. This binary is not advertised as portable to every Linux distribution. Rebuild on the intended host when its libc or multimedia dependencies differ.

## Build

Install the following Ubuntu 24.04 build dependencies, then run `bash native/build.sh` from the project directory. The script clones the pinned source, obtains the pinned submodules, applies the full server patch, builds with at most four jobs, and installs the engine, GNS library, licenses, and relinking materials into this project. A separate build directory can be supplied as the first argument.

```sh
sudo apt-get install build-essential git cmake pkg-config python3-venv bison zsh \
  libgtk-3-dev libopenal-dev libglew-dev libssl-dev libcurl4-openssl-dev \
  libpng-dev libx11-dev libxcursor-dev libxrandr-dev libxi-dev libxss-dev \
  libxext-dev libxfixes-dev libwayland-dev libxkbcommon-dev libasound2-dev \
  libpulse-dev libudev-dev libdbus-1-dev libgl1-mesa-dev libegl1-mesa-dev \
  xvfb xauth
bash native/build.sh
```

The build requires network access to the source repositories and PyPI. `cogapp==3.6.0` is pinned for generated globals. The pinned engine's own CMake logic applies its existing GameNetworkingSockets 1.4.1, PhysicsFS, SDL_mixer and Ogg build adjustments. Those resulting submodule worktree changes are expected; the crossplay patch does not replace their pinned gitlinks or conceal unrelated dependency changes. Source, dependency commits, and build steps are pinned; byte-identical builds across different compiler/distribution versions are not claimed.

For the bundled executable, runtime packages include `libgtk-3-0t64`, `libopenal1`, `libgl1`, `libcurl4t64`, `libsndio7.0`, `libssl3t64`, `xvfb`, `xauth`, and a working Mesa/OpenGL implementation, plus normal C/C++ runtime dependencies. The manager sets `LD_LIBRARY_PATH` to the engine directory. The engine's headless mode still creates an initial SDL/OpenGL context; the manager can use Xvfb if no display is set.

## Optional bot client

`bash native/build_bots.sh` builds `bin/bots-linux-x86_64/jk-bot-client` from the
same pinned base with **only** `bot-client.patch`. It does not replace the
dedicated engine. Run bots through `python3 -m bots.run`; see `bots/README.md`.

`BOT_BUILD.json` records the separate executable. The bot relink archive
contains its exact objects, static libraries and LGPL libsmacker source. Extract
it into an empty folder, edit the included library if desired, and run
`python3 relink.py`. The result is `jk-bot-client-relinked`; make the packaged
GNS shared library available at runtime. Existing dependency notices apply.

The recovery build reused the published unchanged objects/static dependencies,
recompiling changed client units and restoring every existing server-modified
unit to the client source. New dedicated-only units are excluded from the bot
link. A fresh full dependency rebuild is not claimed by its receipts. See
[Bot behavior](../docs/BOTS_BEHAVIOR.md) for current qualification and limitations;
[Bot prototype](../docs/BOTS_PROTOTYPE.md) preserves the earlier milestone.

## Server changes

The patch adds an authenticated, bounded loopback TCP transport bridge. It accepts one supervisor and exposes session metadata, external peer creation/removal, canonical player IDs, and Sith packet delivery. It preserves the original GNS transport for native clients. Detailed framing, message types, ID-pool rules, and packet layouts are in `protocol.md` and the patched engine's `docs/crossplay-gateway.md`.

Dedicated startup uses its isolated working directory and requires the original game-data marker. Redirected stdin is handled without repeatedly logging a prompt. The public GNS packet source is bound to its actual connection's assigned identity. Session metadata counts fully joined active human players, excluding the dedicated host and unused DirectPlay surrogate slots.

Two existing serialization inconsistencies are corrected inside the server: UpdateState's light value is written as float32 to match the existing reader, and MotS absolute CreateThing's sector is read as int32 to match the retail/browser representation and existing sender.

### Chat administration

The manager issues and revokes persistent administrator credentials independently
of the game process. `src/Dss/sithAdmin.c` accepts only a small set of typed host
actions from the authenticated supervisor, checks the actor's current transport
identity and connection generation, and executes ordinary kick or episode
progression messages. It exposes no arbitrary console or script operation.

Players use ordinary chat and an offline proof helper. The downloaded `.cog`
file is an inert credential container kept outside game content; it is never
loaded as a world script. Retail, OpenJKDF2 and JKWeb retain their ordinary
clients and game checksums. See [Chat administration](../docs/CHAT_ADMIN.md) for
issuance, login, revocation and the limits of manually copying challenges.

### MotS native reader profile

The pinned native client has an asymmetric absolute CreateThing implementation: it sends a 32-bit sector ID but reads 16 bits. The dedicated server therefore sends this particular field as 16 bits only to native GNS destinations. The Sith header, reliable sequence, coordinates, and object ID are preserved. Retail and browser destinations use the 32-bit representation. This conversion is a server transport operation; clients install no engine changes.

If every native client connecting to the session uses a later build with the corrected 32-bit reader, launch the manager with `OPENJKDF2_GNS_MOTS_SECTOR_BITS=32` in its environment. GNS does not advertise the client's source commit or this capability, so both native reader variants cannot be inferred automatically on one endpoint. The default profile targets the inspected pinned native version. This setting affects MotS absolute CreateThing only.

JK and MotS use separate session modes and corresponding assets. A JK executable cannot enter a MotS session merely because both endpoints use the same gateway. Matching episode, map, resource, and mod data remains necessary.

## Validation evidence

`qa/native-jk-synthetic.json` and `qa/native-mots-synthetic.json` record actual engine world loading, an authenticated synthetic peer, full synchronization and WELCOME, and joined-human metadata changing 0 → 1 → 0. These are engine/transport checks, not retail or browser gameplay certification.

`qa/native-client-provenance.json` proves that the native test client was built from the exact unmodified base: all four modified translation units were rebuilt from their original git contents and linked with the remaining unchanged base objects and dependencies. No server changes are included in that client. Its SHA-256 is recorded in that receipt.

The unchanged native client discovered and joined the mixed server's stock JK `JK1MP/m2.jkl` session through GNS, was assigned a real reserved DirectPlay identity, and entered the live world alongside the original JK1.00 retail executable and published browser client. `qa/native-jk-live.json` records the simultaneous active roster and deliberate movement from all three clients reaching the native client, with reciprocal native movement observed in original retail. In the recorded snapshots, native versus original retail views differed by 0.127451 world units for the native player and 0.038729 world units for the retail player; exact coordinate convergence is not claimed. Both source implementations use thresholded velocity smoothing, but its role in these observed offsets was not isolated. These local checks do not certify every map, force power, mod, network condition, or engine release.

The same unchanged native executable, launched with its existing `-motsCompat` option, also joined original retail MotS and the unchanged published browser build simultaneously on `JKM_MP/mdm02_freezer.jkl`. This check used free-for-all, rank 7, and the default Jedi personality. `qa/native-mots-live.json` records active rosters, applied movement, chat, and actual projectile entities in both directions between native and retail, and between native and browser. The browser independently observed six distinct native pistol projectiles; native independently observed five distinct browser pistol projectiles. A native world death and ordinary respawn during normal movement propagated to original retail, including health 100 after respawn and deaths 1 / suicides 1 / score −1. The recorded native-versus-retail position offset after respawn was 0.105607 world units; its cause was not isolated. Initial across-room shots did not reduce browser health or shields, so this evidence does not establish direct player-to-player damage or kill credit. MotS team/class models and other maps remain outside the qualification.

The standalone `src/Tests/gateway_bridge_test.cpp` passes under AddressSanitizer and UndefinedBehaviorSanitizer: fragmented authentication, 200 coalesced frames, replies, length bounds, wrong token rejection, and disconnect callbacks. Compile from the patched checkout with:

```sh
g++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -Isrc src/Tests/gateway_bridge_test.cpp \
  -o gateway_bridge_test
./gateway_bridge_test
```

## Licenses and relinking

The engine's exact original license and bundled dependency notices are under `licenses/native/`. Original game archives, game executables, ISOs, Microsoft runtimes, and player data are excluded from this package. The server patch retains the engine license; new integration/build scripts use the project license.

`relink-linux-x86_64.tar.gz` includes the exact application object files, linked static libraries, the statically linked LGPL libsmacker's corresponding source, and a `relink.py` utility. To modify libsmacker and relink the supplied application, extract this archive to an empty folder, edit the included library source, and run `python3 relink.py` on a matching build environment. It produces `openjkdf2-relinked`. Run it alongside the supplied `libGameNetworkingSockets.so` through the same manager or with its directory on `LD_LIBRARY_PATH`. Full native source can also be rebuilt using the pinned source and patch above.
