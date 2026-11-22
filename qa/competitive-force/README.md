# Native competitive Force observation

`harness.py` runs a bounded rank-eight session on a stock `JK1MP` map with the
packaged dedicated server and two ordinary competitive bot clients. Supply
the repository, owned game-data directory, and a new output directory with
`--repo`, `--data`, and `--output`. The `--duration` option accepts 1 through
120 seconds after both clients join.

The default map is `m2.jkl`. Use `--map` to select `m4.jkl`, `m5.jkl`,
`m10.jkl`, `m_boss15.jkl`, or `m_boss17.jkl`. The harness compares the
selected JKL with its SHA-256 in `qa/bots-stock-map-audit.json` and records
the map name and measured hash in the receipt.

Run it in a private Linux network namespace with loopback enabled. The native
GNS server normally binds all interfaces, so merely connecting the bots to
127.0.0.1 does not isolate the listener. The qualification runner used a new
unprivileged user/network namespace and verified that loopback was its only
network interface. No browser gateway or public server listing is involved.

The harness uses the Python standard library, the checked-in repository
modules, and ordinary native runtime dependencies. It requires software
EGL/OpenGL but no Xvfb or Python networking package. It verifies the packaged
bot binary, GNS library, source patch, original multiplayer GOB, and selected
JKL hashes before play. Only private copies of the four necessary stock input
files are staged. Original archives are opened read-only. No controls, stars,
inventory, effects or positions are written directly into the running game.

The complete budget is 180 seconds, including startup and cleanup. The process
groups owned by this run are stopped on completion, error or a handled signal.
Staged game inputs and isolated player profiles are removed. Raw process logs
remain in the new output directory for private debugging; publish only the
numeric receipt and selected, reviewed trace evidence.

Exit zero establishes distinct native joins and matching live star vectors.
The receipt separates requested inputs from sampled active bins, mana changes,
health changes and immobility. It does not attribute damage or immobility to a
particular caster, prove a short effect was absent between samples, establish
current JKWeb interoperability, or measure strength against humans. The
packaged `BOT_FORCE_STATE` trace samples only each bot's own state.

In each published receipt, `trace_evidence.receipt_sha256` hashes the original
private harness output before qualification metadata was added to the
checked-in JSON. The `trace_evidence.trace_sha256` value hashes the exact
bytes of the published JSONL trace named in `trace_evidence.trace_file`.

### Canyon Oasis water entry and pickups

On `m10.jkl`, the old route planner clipped the rim of a water shaft when it
tested a straight diagonal from the dry ledge. The bot now checks body
clearance across the opening and down into the water, then uses ordinary
movement to enter. The source fixture uses the engine collision routines and
privately supplied stock world surfaces. From sector 41, reachable nodes
increased from 13 to 517 of 552, and reachable items from 1 to 19 of 42.
Both versions anchored 38 items. A current JKWeb match subsequently reported
516 of 554 nodes and 19 of 42 items reachable from sector 41.

The next source revision lets the bot collect a recessed item from a reachable
position where the player and item collision spheres overlap and the stock
touch handler has line of sight. In the same offline fixture, this raised
reachable items from 18 to 36 of 42 from sector 39 and from 19 to 38 of 42
from sector 41. The revised graph has 558 nodes and anchors 40 items. Both
starts have routes to both rail detonators, both repeaters, every rail charge
and every power cell. Sector 41 also has a route to the sole concussion rifle.
Live inventory changes provide a separate measure of actual collection.

With the subsequent water-exit maneuver, both origins reach 523 of 558 nodes
and 38 of 42 items, including the concussion rifle. A separate source replay
tested the exit from a submerged waypoint to the sector 41 ledge at 30, 50,
60 and 120 frames per second, with two stock airborne physics routines and
five Force Speed settings (off and ranks 1–4). All 40 runs reached the
supported ledge after one surface jump. The replay drove the bot's movement
inputs through the stock swim, jump and airborne routines against world
surfaces. It supplied the water-surface flag and checked the landing with a
body sweep. This result covers the maneuver under those fixture conditions.

`native/tests/run_bot_portal_tests.py` exercises water entry, water exit and
recessed pickups on synthetic geometry. It checks closed, hazardous, AI-only
and undersized openings, pickup overlap and visibility, and the player's
final approach to the shelf.
