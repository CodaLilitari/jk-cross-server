# Platform downloads and setup

JK Cross Server 0.4.0-dev packages the same server, bot client and host spectator
implementation for each download. The compiled engines target **Linux x86-64**.
Windows and macOS run those engines in a Linux container. They are not native
Windows or macOS server ports.

| Download | Execution route | Start here |
| --- | --- | --- |
| `JK_Cross_Server_0.4.0-dev-linux-x86_64.zip` | Native Linux x86-64; Docker optional | Native Linux instructions below |
| `JK_Cross_Server_0.4.0-dev-windows-docker.zip` | Linux x86-64 through Docker Desktop | `Start-Server.ps1` |
| `JK_Cross_Server_0.4.0-dev-macos-docker.zip` | Linux x86-64 through Docker Desktop | `Start-Server.command` |
| `JK_Cross_Server_0.4.0-dev.zip` | Common updater/source payload | Existing in-place updater or manual setup |

Every platform archive contains the complete common payload, including both
compiled engines and their libraries, plus a `PLATFORM-README.md` entry guide.
Each ZIP has a `.zip.sha256` checksum file. Platform names identify the setup
route, not a separate feature branch or a claim that every host has been tested.
Read [Qualification](QUALIFICATION.md), [Bot behavior](BOTS_BEHAVIOR.md), and
[Browser spectator](BROWSER_SPECTATOR.md) for the actual evidence and open limits.

## Before starting

- Extract the whole ZIP into a writable folder. Run commands from the extracted
  `jk-cross-server` folder; do not run an individual file inside the ZIP.
- Supply your own installed JK or MotS game-data directory containing `resource/`
  and `episode/`, including the original `resource/jk_.cd` marker. No commercial
  game archives, retail executables, original DirectPlay DLLs, or ISOs are included.
- For the Docker route, install and start Docker Desktop on Windows/macOS, or
  Docker Engine and the Compose v2 plugin on Linux. Use **Linux containers**.
  The launchers check these prerequisites; they do not install software or change
  host firewall/router settings.
- The first Docker start builds an Ubuntu 24.04 image, installs pinned Python
  dependencies, and fetches the hash-verified public browser client. It needs
  Internet access and sufficient disk space for Docker's image and volume data.
- Apple Silicon uses `linux/amd64` emulation. This is not a native ARM build;
  performance and graphics compatibility require validation on the actual host.
  Configure Docker Desktop's supported x86-64 emulation if it reports an
  architecture error. Windows ARM also depends on a working Linux amd64 runtime.

## Windows with Docker Desktop

Open PowerShell in the extracted folder. Pass literal paths in single quotes:

```powershell
.\Start-Server.ps1 -GameData 'C:\Games\Jedi Knight' -StateDir 'C:\JK Server State'
```

`-StateDir` is optional; it defaults to `.jk-cross-server` under your user home.
If PowerShell blocks a downloaded script, inspect it and use your normal local
script approval process. The package does not change execution policy.

Open **http://127.0.0.1:8765**. The container starts the administration panel;
select the game mode and map, save, check the files, and start the match there.

```powershell
.\Start-Server.ps1 -Command logs
.\Start-Server.ps1 -Command stop
```

Stop/logs target the existing `jk-cross-server` container and do not need the
game-data path again. Stop preserves both settings and application updates.

## macOS with Docker Desktop

Open Terminal in the extracted folder:

```sh
sh ./Start-Server.command --game-data '/Users/you/Games/Jedi Knight' \
  --state-dir '/Users/you/JK Server State'
```

`--state-dir` defaults to `$HOME/.jk-cross-server` when omitted. Explicit path
arguments avoid a file picker and work with spaces. Double-clicking the command
without a configured `JK_GAME_DATA` environment variable does not select data;
use Terminal and the explicit path instead.

Open **http://127.0.0.1:8765**, select the game mode and map, and start from the
panel. The same package includes bots and image/geometry spectator code; the
graphics work still runs inside the Linux container.

```sh
sh ./Start-Server.command logs
sh ./Start-Server.command stop
```

## Native Linux x86-64

The supplied engines were built against Ubuntu 24.04 x86-64. They are not
advertised as portable to every distribution. See [Native build](../native/README.md)
for recorded dependencies, provenance and rebuilding for another host.
The runtime needs OpenGL/EGL and the listed multimedia libraries even on a
headless server. Bots need Xvfb and xauth when a display is unavailable.

Use Python 3.11 or newer. Keep environments, fetched client files and runtime
state outside a source checkout:

```sh
python3 -m venv "$HOME/.local/share/jk-cross-server/venv"
. "$HOME/.local/share/jk-cross-server/venv/bin/activate"
python -m pip install -r web_gateway/requirements-lock.txt
python -m web_gateway.fetch_client \
  --destination "$HOME/.local/share/jk-cross-server/browser-client"
python app.py --config "$HOME/.jk-cross-server/config/server.json" \
  --state-dir "$HOME/.jk-cross-server/runtime"
```

At **http://127.0.0.1:8765**, set the engine to this extracted package's
`bin/linux-x86_64/openjkdf2`, the game-data folder to your installed game, and
the browser client folder to the absolute destination used above. Save, read the
episode catalog, select the map, check files, and start. Set game mode to MotS
when using its resources; a JK session and a MotS session are distinct.

If your ZIP extractor did not preserve Unix executable permissions:

```sh
chmod +x bin/linux-x86_64/openjkdf2 bin/bots-linux-x86_64/jk-bot-client
```

For the optional Linux Docker route:

```sh
sh ./start-server.sh --game-data '/home/you/Games/Jedi Knight'
sh ./start-server.sh logs
sh ./start-server.sh stop
```

## Container data, updates and network endpoints

The launchers resolve the selected game directory and state directory to absolute
paths and pass them as `JK_GAME_DATA` and `JK_STATE_DIR`. They invoke the exact
packaged `packaging/compose.yaml`; the current working directory does not choose
another Compose project.

| Host resource | Container path | Purpose |
| --- | --- | --- |
| Selected game-data directory | `/game-data` (read-only) | Your installed game resources |
| Selected state directory | `/data` (writable) | Saved settings, credentials, runtime logs and updater state |
| Named volume `jk-cross-server-app-0.4.0-dev` | `/app` (writable) | Seeded server application and verified in-place updates |

The first start creates `/data/config/server.json` with container paths and
`/data/runtime` for state. Subsequent starts preserve the saved configuration.
Keep the panel's game-data path as `/game-data`, engine paths under `/app/bin`,
and browser client path as `/opt/jk-web`; host paths are meaningful only to the
launcher and Docker mount configuration. To change your host game installation,
stop the container and rerun the launcher with the new `--game-data`/`-GameData`.

The existing panel updater can update the writable `/app` installation while
the game is stopped. It does not rebuild the image or replace the external
container entrypoint/system dependencies. A later platform release may require
extracting its new package and running its launcher. Rebuilding the same image
does not overwrite an existing application volume; retain that volume to keep
in-place updates. Do not delete the application volume or the state directory
as part of an ordinary stop/restart.

The launchers use one Compose project and container named `jk-cross-server`.
Concurrent instances need deliberately separate project/container names,
application volumes, state directories and ports; these launchers do not provide
automatic multi-instance allocation.

| Published host endpoint | Purpose |
| --- | --- |
| `127.0.0.1:8765/tcp` | Local administration and host spectator view |
| `3500/udp` | Native OpenJKDF2 clients |
| `8787/tcp` | Browser client/gateway |

The administration endpoint is bound only to host loopback. Its internal proxy
preserves Host/Origin and authentication checks. The native and browser endpoints
are published on host interfaces; reachability still depends on Docker Desktop,
host firewall and router configuration. Internet hosting, browser HTTPS/WebRTC
and NAT traversal require the deliberate setup in [Networking](NETWORKING.md).
The launcher does not modify those settings.

## Optional retail DirectPlay transport

The Windows/macOS package name does not mean that original DirectPlay is
automatically available. Retail support remains optional and disabled by
default. The container does not include Wine or original DirectPlay runtime
files. A manual Wine environment and appropriate legacy networking are required
for that route; Docker Desktop's NAT is not qualified as a transparent replacement
for the documented retail setup. Follow [DirectPlay setup](../directplay/README.md)
and keep successful host/container launch separate from a verified retail match.

## Building the platform archives

First build the ordinary updater ZIP using `scripts/build_release.py`, with its
tracked-file inventory and refreshed manifest. Then use an output directory
outside the checkout:

```sh
python scripts/build_platform_releases.py \
  --input /path/to/releases/JK_Cross_Server_0.4.0-dev.zip \
  --output-dir /path/to/platform-releases
```

The platform builder verifies the updater's manifest, every file checksum,
required engine/launcher files and executable modes before writing three
reproducible ZIPs and their checksums. It rejects unsafe paths, duplicate names,
symlinks and unmanifested payload files. It preserves the common payload bytes
and adds only each platform's entry guide. It never packages files by recursively
scanning a personal directory or source checkout.
