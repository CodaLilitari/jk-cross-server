# Experimental ordinary-player bots

Each bot runs its own native client and joins the dedicated server as a normal
player. Its private executable drives ordinary movement, weapon, inventory, and
Force inputs. The stock game handles collisions, pickups, ammunition, mana,
damage, death, respawn, scores, flags, and chat. Human retail, OpenJKDF2, and JKWeb
players use their existing clients; the bots consume ordinary player slots.

This extension adds managed rosters, live combat rules, legal Force character
builds, weapon and pickup decisions, and stock CTF objectives. It remains a
prototype. **Live gameplay qualification of the newly integrated build is
pending.** Configuration and input tests, and a complete stock pickup catalog,
do not establish complete map traversal or successful CTF matches. Read the
[current behavior and evidence report](../docs/BOTS_BEHAVIOR.md) for the exact
build, checks, and outstanding limits. The earlier rank-zero reconstruction and
its mixed-client results remain in the
[historical prototype report](../docs/BOTS_PROTOTYPE.md); those results apply to
that earlier executable.

## Start bots from the server control panel

The packaged bot executable targets Linux x86-64. Use your installed original JK
game data, including the stock CTF episode for CTF sessions. Install Xvfb and the
server's normal display/GL dependencies for a host without `DISPLAY`. Follow
the [server setup instructions](../README.md#start-on-linux) to open the panel.

1. While the session is stopped, select **Jedi Knight: Dark Forces II**, the
   stock episode and map, and a **Force rank** from 0 through 8.
2. In **Bot roster**, check **Add bots when the server starts** and choose one
   to four different characters. Set **Player slots** to at least the bot count
   plus two, allowing one slot for the dedicated host and one for a human.
   Set **Occasional character chat** as desired.
3. In **Combat rules**, choose **Sabers only**, **Fists = peace**, and **Use Force
   powers**. These settings govern the bots in this roster.
4. Save settings, check the files, and start the session. The manager starts
   the bots after the server transports are ready. The roster shows each bot's
   join state and any launcher error.

During a running session, change the combat checkboxes and click **Apply bot
rules**. Running bots read the complete new settings within approximately one
second, and the manager saves them for the next session. Stop the session before
changing the roster, chat setting, rank, map, or team mode. Stopping the session
also stops its bot clients and any display process created for them. If the bot
runner fails, the manager cleans up that roster and reports the error while the
human server keeps running.

### Defaults and saved settings

Existing configurations remain **bots disabled** until explicitly enabled.

| Panel setting | Configuration key | Default |
|---|---|---|
| Add bots when the server starts | `bots_enabled` | `false` |
| Selected characters | `bots_profiles` | `["boba_fett", "jan_ors"]` |
| Sabers only | `bots_sabers_only` | `false` |
| Fists = peace | `bots_fists_peace` | `true` |
| Use Force powers | `bots_force_enabled` | `true` |
| Occasional character chat | `bots_taunts` | `true` |
| Bot client executable | `bots_engine` | Empty: use the packaged client |

**Sabers only** prevents bot gun, explosive, and fist attacks. **Use Force
powers** is independent: turn it off as well for saber combat without Force.
Rank-zero characters have no Force powers regardless of that checkbox. Bacta
use is an ordinary inventory action and remains available with Force disabled.

Live switches affect subsequent decisions and inputs. Projectiles already in
flight and effects already started by the stock scripts retain their normal
lifetimes. The bot suppresses further fire and turns away when an active Deadly
Sight effect becomes incompatible with a changed rule; this cannot instantly
cancel that stock effect.

## Accepted sessions and map coverage

| Mode | Required settings | Stock maps |
|---|---|---|
| Deathmatch | `game: "jk"`, `episode: "JK1MP"`, rank 0–8 | `m2.jkl`, `m4.jkl`, `m5.jkl`, `m10.jkl`, `m_boss15.jkl`, `m_boss17.jkl` |
| Team deathmatch | As above, **Team game** enabled and **Additional game flags** including `256` for stock team skins | The same six JK1MP maps |
| Capture the flag | `game: "jk"`, `episode: "JK1CTF"`, rank 0–8, **Team game** enabled | `c1.jkl`, `c2.jkl`, `c3.jkl` |

Leave the legacy game password and mod folder empty. The launcher rejects MotS,
other episodes, unsupported multiplayer flag bits, passwords, and mod folders.
For advanced configuration, additional flags must be a subset of `0x1bf`;
normally leave them at `0`, except the `256` team-skin bit for JK1MP team games.
Selecting **Team game** alone is insufficient for JK1MP bots. Stock CTF uses its
own lobby and team rules and does not require that team-skin flag.

One to four bots may be selected. `max_players` includes the dedicated host,
so it must be at least the bot count plus two: one bot needs at least three
slots, and four bots need at least six. This leaves a configured allowance for
one human; it does not reserve that place in a live match. The launcher does not
coordinate occupancy with another bot invocation or replace bots automatically
when a human joins. Disabled bots do not restrict a manual session's slot limit.

The read-only [stock map audit](../qa/bots-stock-map-audit.json) classifies all
700 authored pickups across these nine maps and checks the stock CTF bindings.
At runtime, bots locate actual world items and prioritize health, shields,
needed weapons and ammunition, bacta, mana, and useful powerups according to
their current state and combat rules. Saber-only bots omit gun/ammunition
goals. Recognizing every pickup is separate from finding a usable route to it.
Navigation includes collision and floor checks, route recovery, mover handling,
and ordinary jump/Force-jump inputs; complete traversal, reliable use of every
lift, and access to every pickup have not been established for every map.

## Combat and fists-peace behavior

Gun decisions consider distance, ammunition, sight lines, nearby protected
players, and the current weapon. Bots lead moving targets with a bounded aim
prediction, use bursts with the stormtrooper rifle at longer range, and consider
repeater alternate fire at close range. Bowcasters use the immediate alternate
shot: their stock primary attack fires on key release, which would otherwise
make stopping an attack unsafe when a target switches to fists. Splash weapons
need space around the bot and target; shots are withheld when a teammate or
peaceful player lies in the checked firing corridor or blast area. Hand
grenades and planted mines are currently omitted because they need more reliable
arc and trap planning. These precautions reduce accidental hits; moving players,
ricochets, network delay, and projectiles already in flight still matter.

With **Fists = peace**, a bot respects a player visibly holding fists until that
player provokes that particular bot. Detection uses the ordinary synchronized
weapon model, attributed damage, and visible attack events. A nearby armed
player remains a possible combat target.

Detected provocation includes:

- Attributed damage, aimed incoming fire, or a nearby punch attempt at the bot.
- Hostile Force targeting events reported by the stock game.
- Sustained body blocking for about three seconds while obstructing the bot's
  intended movement; brief contact or passing in front does not suffice.
- Four observed weapon changes within three seconds nearby and in sight.

Provocation lifts that bot's peace protection for **15 seconds after the latest
detected event**. Each bot tracks its own relationship with each player. The
memory resets when that player's network or thing identity changes; an observed
death also clears it. Environmental damage, self-damage, and invalid or recycled
projectile ownership are not assigned to a nearby player.

There is a stock-game attribution limit: **Force Throw can accelerate loose
debris without recording its caster as the debris owner or sending a targeted
Force event.** A resulting impact cannot always be attributed to the human who
threw it. The bot does not guess who was responsible. This remains a gap in the
peace rule for that particular form of provocation.

## Force powers and legal characters

Bots create an ordinary saved multiplayer character before joining, using the
rank actually advertised by the server. They follow the stock editor's budget:
three stars per rank, at most four stars per power, neutral powers available
from rank 1, and successive light/dark side powers available at ranks 4–7.
The normal profile-loading and inventory lifecycle installs that character;
Force use does not grant live mana, ammunition, health, or extra stars.

Balanced profiles distribute legal stars among neutral and accessible powers
on their chosen side. Jan and Sariss request a master build: **at rank 8 only**,
they allocate four stars to each of their four side powers, leave eight stars
unspent, and let the stock game derive Protection or Deadly Sight. They have no
neutral powers in that rank-eight build. Below rank 8 they use the balanced
allocation. These are project persona choices, not claims about a character's
canonical abilities.

The controller uses ordinary power hotkeys and lets the stock COG scripts
enforce costs and effects. Decisions check availability, mana, cooldowns,
distance, sight lines, and protected players. Healing, protection, absorption,
seeing, persuasion, movement powers, and hostile powers have situational
policies. **Force Throw and Deadly Sight are not started when fists-peace or
team play is enabled**, because their stock area effects cannot provide the
same target protection as directed attacks. Turning off Force prevents new
casts and releases or cancels held input where the stock script permits it;
already active effects retain the boundary described above.

## Stock CTF behavior

For a team session, the launcher requests alternating red and gold teams in
roster order. In stock CTF, bots must physically enter the normal team-selection
corridors. The original COGs assign the team and teleport the player into play.
Those scripts also apply the stock red/gold team model and saber, so a bot's
roster skin is replaced by the team appearance in CTF. Its name and chat persona
remain recognizable.

The objective policy distinguishes taking the enemy flag, returning a dropped
own flag, carrying the enemy flag home, and escorting or defending as needed.
Captures still require touching the own flag at home while carrying the enemy
flag, through normal movement and the stock scripts. The bot does not write
flag ownership, teams, teleports, or scores to bypass those rules. Catalog and
policy checks are available; complete live CTF match qualification is pending
in the [current evidence report](../docs/BOTS_BEHAVIOR.md).

## Roster and chat

| Profile id | Visible player name | Stock model | Stock sound class | Force build |
|---|---|---|---|---|
| `boba_fett` | `Bot_BobaFett` | `kyh4.3do` | `kybobafett.snd` | Dark, balanced |
| `jan_ors` | `Bot_JanOrs` | `kya10.3do` | `kyfemale.snd` | Light, master at rank 8 |
| `kyle_katarn` | `Bot_Katarn` | `ky.3do` | `ky.snd` | Light, balanced |
| `stormtrooper` | `Bot_Trooper` | `kym13.3do` | `kytrooper.snd` | Dark, balanced |
| `bossk` | `Bot_Bossk` | `kyi14.3do` | `kybossk.snd` | Dark, balanced |
| `greedo` | `Bot_Greedo` | `kya17.3do` | `kygreedo.snd` | Dark, balanced |
| `sariss` | `Bot_Sariss` | `kya9.3do` | `kyfemale.snd` | Dark, master at rank 8 |
| `yun` | `Bot_Yun` | `kya18.3do` | `kyyun.snd` | Dark, balanced |

The `Bot_` prefix identifies the players as bots. The roster contains 128
original fan-written lines, divided into spawn, kill, death, and ambient
contexts. They are not official dialogue or live language-model output. Bots
do not generate replies to arbitrary player chat.

The scheduler uses ordinary multiplayer chat, a per-bot cooldown of 90–150
seconds, staggered first lines, and a shared 35-second minimum between lines
from bots launched in the same invocation. Separate invocations do not share
this gate. Disable **Occasional character chat** before starting, or use
`--no-taunts` for a standalone run.

## Standalone launcher

The CLI remains available. Start the dedicated server first, then use its
configuration file with `game_data` pointing to your original installed JK
data. An explicit CLI invocation launches bots independently of the manager's
`bots_enabled` switch, so avoid also enabling the same roster in the panel.

From the repository root:

```bash
python3 -m bots.run --list-profiles
python3 -m bots.run --server-config examples/jk.json --profiles boba_fett,jan_ors
```

`examples/jk.json` is a template: update its game path and session settings
first. The launcher connects to `127.0.0.1:<native_port>` by default. It does
not start, reconfigure, or stop the server. Without `--profiles`, it uses the
configuration's `bots_profiles` roster and reads the configured combat and chat
defaults.

For a bounded run against another address:

```bash
python3 -m bots.run --server-config /absolute/path/server.json \
  --connect game-server.example:3500 \
  --profiles boba_fett,jan_ors --seconds 300
```

| Option | Effect |
|---|---|
| `--profiles ID,ID` | Select 1–4 different members of the roster. |
| `--engine /absolute/path/jk-bot-client` | Use a separately built bot executable. |
| `--runtime /absolute/path/bot-runs` | Store isolated run directories here. |
| `--seconds 300` | Stop this invocation's bots after five minutes. `0` runs until interrupted. |
| `--no-taunts` | Disable all bot chat for this invocation. |
| `--behavior-file /absolute/path/behavior.cfg` | Read live rules from an existing file managed by the caller. |

A standalone run normally creates `behavior.cfg` in its run directory. To
change it live, atomically replace the complete file with all four lines:

```ini
version=1
sabers_only=0
fists_peace=1
force_enabled=1
```

Only `0` and `1` are accepted. A missing, partial, duplicate, or invalid setting
preserves the last valid rules. Editing the server's JSON during a standalone
run does not update that run's behavior file. The panel handles publication
automatically for its managed bots.

Use Ctrl+C to stop the launched bots. The launcher owns their process groups
and its own Xvfb, if needed, and leaves the running server and unrelated
processes alone. If a component exits, a join is rejected, or a bot has not
joined after 90 seconds, it stops its own roster and returns failure. A bounded
run that ends before all bots join also returns failure.

## Isolation and diagnostics

Standalone runs have timestamp/random identifiers under `runtime/bots`;
managed bot runs live inside the corresponding server session directory.
Every bot has its own player profile, XDG directories, registry, log, and
generated `persona.tsv`. Only `resource` and `episode` trees are staged from
the installed game; human profiles and settings are not imported. Game input
filenames are lowercased for the Linux client, ambiguous case collisions and
directory cycles are rejected, and video directories are skipped. Archives are
normally hardlinked as read-only game inputs, with copying across filesystems.
Never edit staged game archives in place: a hardlink shares the original bytes.

The run's `session.json` records the roster, requested teams and Force builds,
behavior file, model, directory, PID, joined slot/network ID, exit status, and
errors. `requested_team` is the requested team, not evidence that the stock CTF
lobby assigned it; actual team selection must be observed in gameplay or logs.
Each `client.log` contains the native client's detailed output,
including `BOT_LOADOUT`, `BOT_BEHAVIOR`, `BOT_PROVOKED`, `BOT_FORCE_INPUT`, and
status diagnostics when those events occur. `BOT_JOINED` establishes a joined
client; `BOT_FORCE_INPUT` establishes a requested input. Neither alone proves
successful damage, a Force effect, a route, a capture, or client compatibility.
`xvfb.log` is present when the launcher created the display.

Configuration, lifecycle, and catalog regression checks:

```bash
python3 -m unittest tests.test_bots tests.test_bot_manager tests.test_bot_maps -v
```

The process tests use small helper programs. Engine policy tests use controlled
game-state and collision fixtures. Their scope and the separate live evidence
are recorded in [the current behavior report](../docs/BOTS_BEHAVIOR.md).
