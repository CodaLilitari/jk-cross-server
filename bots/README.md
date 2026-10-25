# Experimental ordinary-player bots

Each bot runs its own native client and joins the existing server as a normal
player. The private bot executable drives normal player inputs. The game still
handles movement, collisions, pickups, ammunition, weapons, damage, death,
respawn, scores, and chat. Human retail, OpenJKDF2, and JKWeb clients do not need
this executable or a client patch.

This is a reconstructed prototype. The earlier unpushed implementation was lost
when the working environment was reset. Source recovered from the design record
has been reconstructed and must be judged by the validation receipts shipped
with this revision. Earlier test outcomes are not proof of this revision's
runtime behavior.

## Run

The packaged executable currently targets Linux x86-64. Start your usual
`jk-cross-server` session first. Use the same server configuration file, with
`game_data` pointing to your installed original JK data. Xvfb must be installed
and available on `PATH` when `DISPLAY` is unset.

From the repository root:

```bash
python3 -m bots.run --list-profiles
python3 -m bots.run --server-config examples/jk.json --profiles boba_fett,jan_ors
```

`examples/jk.json` is a template: update its game installation path and server
settings before using it. The bot launcher connects to `127.0.0.1:<native_port>`
by default. It does not start, reconfigure, or stop the server.

For a bounded run against another address:

```bash
python3 -m bots.run --server-config /absolute/path/server.json \
  --connect game-server.example:3500 \
  --profiles boba_fett,jan_ors --seconds 300
```

Useful options:

| Option | Effect |
|---|---|
| `--profiles ID,ID` | Select 1–4 different members of the roster. |
| `--engine /absolute/path/jk-bot-client` | Use a separately built bot executable. |
| `--runtime /absolute/path/bot-runs` | Store isolated run directories here. |
| `--seconds 300` | Stop this invocation's bots after five minutes. `0` runs until interrupted. |
| `--no-taunts` | Disable all bot chat for this invocation. |

Use Ctrl+C to stop the launched bots. The launcher owns their process groups
and its own Xvfb, if one was required. It leaves unrelated processes and the
running server alone. If a component exits, a join is rejected, or a bot has not
joined after 90 seconds, it stops the rest of its own roster and returns failure.
A bounded run that ends before all bots join also returns failure.

## Supported scope

The launcher currently accepts **stock JK1MP, rank 0, free-for-all, game flags
zero, no password, and no mod directory**. MotS, Force-rank sessions, team/CTF
objectives, and custom content are not qualified. A bot is a normal player slot,
so each selected bot consumes one configured place. The launcher requires fewer
bots than `max_players` as a static allowance for a human. This is not a live
reservation: it does not inspect current occupancy or coordinate separate
launcher invocations.

Initial AI behavior includes ordinary navigation, item seeking, combat inputs,
and respawn input. Full-map traversal, elevators, special objectives, complete
weapon strategy, and human-level competitive play are beyond this prototype.
Actual native/retail/browser interoperability and AI performance must be assessed
from the current build's live QA record, not inferred from these launcher tests.

The recovered build has a local mixed-session test with four bots and unchanged
retail JK 1.00, native OpenJKDF2 and JKWeb clients together on `JK1MP/m2.jkl`.
The final executable also has live evidence of escaping the low spawn tunnel
that trapped the preceding build. See [qualification and exact build hashes](../docs/BOTS_PROTOTYPE.md)
for the observed gameplay, runtime details and limits of this test.
Subsequent DirectPlay adapter corrections have separate receipts from the
frozen bot executable's mixed gameplay test.

## Roster and chat

| Profile id | Visible player name | Stock model | Stock sound class |
|---|---|---|---|
| `boba_fett` | `Bot_BobaFett` | `kyh4.3do` | `kybobafett.snd` |
| `jan_ors` | `Bot_JanOrs` | `kya10.3do` | `kyfemale.snd` |
| `kyle_katarn` | `Bot_Katarn` | `ky.3do` | `ky.snd` |
| `stormtrooper` | `Bot_Trooper` | `kym13.3do` | `kytrooper.snd` |
| `bossk` | `Bot_Bossk` | `kyi14.3do` | `kybossk.snd` |
| `greedo` | `Bot_Greedo` | `kya17.3do` | `kygreedo.snd` |
| `sariss` | `Bot_Sariss` | `kya9.3do` | `kyfemale.snd` |
| `yun` | `Bot_Yun` | `kya18.3do` | `kyyun.snd` |

The `Bot_` prefix makes their identity explicit. The character associations are
project personas attached to retail skins; they grant no character-specific
powers. The roster contains 128 original fan-written lines, divided into spawn,
kill, death, and ambient contexts. They are not official dialogue, live language
model output, or a response to arbitrary player chat.

The native scheduler uses ordinary multiplayer chat, a per-bot cooldown of
90–150 seconds, staggered first lines, and a shared 35-second minimum between
lines from bots launched in the same invocation. Separate launcher invocations
do not share this gate. The TSV parser and launcher validate printable ASCII,
bounded line lengths, and known event names.

## Isolation and diagnostics

Each run has a timestamp/random identifier under `runtime/bots`. Every bot has
its own `player`, XDG, registry, log, and generated `persona.tsv` files. Only
`resource` and `episode` trees are staged from the original game installation;
human profiles and settings are not imported. Game input filenames are
lowercased for the Linux client, with ambiguous case collisions and directory
cycles rejected. Video directories are skipped. Archives are normally
hardlinked and treated as read-only game inputs; cross-filesystem staging falls
back to copying. Never edit staged game archives in place, because a hardlink
shares the original bytes.

The run's `session.json` records each bot's selected model, directory, PID,
normal joined slot/network ID, exit status, and any error. `client.log` contains
the native client's detailed output. A `BOT_JOINED` marker establishes that a
client joined; it does not by itself establish navigation quality, damage,
respawn, or cross-client gameplay correctness. `xvfb.log` is present when the
launcher created the display.

To run launcher regression tests without game assets:

```bash
python3 -m unittest discover -s tests -p test_bots.py -v
```

These tests use small helper programs for process lifecycle and file isolation.
They do not substitute for live-game testing.
