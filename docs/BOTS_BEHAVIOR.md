# Configurable player bots: behavior and evidence

This document describes the JKDF2 bot extension and separates implementation, controlled checks,
intermediate probes, and connected gameplay qualification. Operational steps and CLI examples are in the
[bot guide](../bots/README.md). The final connected results belong in the explicitly titled section
below; a successful build or joined roster alone does not establish those results.

## Architecture and compatibility boundary

Each bot is a separate native client with an isolated ordinary player profile. The input driver observes
game state and supplies normal movement axes, weapon selection, attack buttons, inventory hotkeys, and
respawn input. The stock engine and COGs still implement movement, collisions, pickups, ammunition,
mana, damage, deaths, flag rules, scoring, and chat. There are no synthetic player slots, live inventory
grants, scripted flag captures, or bot teleports.

Only the bot executable contains the AI and observation hooks. Human retail, OpenJKDF2, and JKWeb
players use their unchanged clients through the existing server transports. The shared server has a
separate spawn-count correction described below; it applies to ordinary players on every transport. The
bot and dedicated source patches are separate builds, not patches for human clients.

## Accepted configuration

| Mode | Settings | Maps |
|---|---|---|
| Deathmatch | JK, `JK1MP`, rank 0–8 | `m2`, `m4`, `m5`, `m10`, `m_boss15`, `m_boss17` |
| Team deathmatch | Above, `teams: true`, additional flag `256` for team skins | Same six maps |
| CTF | JK, `JK1CTF`, rank 0–8, `teams: true` | `c1`, `c2`, `c3` |

Map names have a `.jkl` suffix. Bots require matching original installed data, no password, no mod
directory, and additional flag bits within `0x1bf`. MotS, custom episodes, and other modes remain
outside this implementation's scope. Choose one to four different profiles. `max_players` includes
the dedicated host and must be at least the bot count plus two, leaving one place for a human.
This static allowance is not a live seat reservation; disabled bots do not constrain manual capacity.

## Web controls and lifecycle

Existing configurations default to bots disabled. The default selected roster is Boba Fett and Jan Ors;
character chat and Force use default on, fists-peace defaults on, and saber-only defaults off. The three
live combat controls are:

| Control | Effect |
|---|---|
| Sabers only | Prevent bot gun, explosive, and fist attacks; omit gun/ammo goals. |
| Fists = peace | Respect fists-out opponents unless they provoke that bot. |
| Use Force powers | Permit powers available to the ordinary character build. |

Saber-only and Force use are independent. Rank-zero profiles have no powers; bacta remains an inventory
action when Force is disabled. During play, **Apply bot rules** saves and atomically publishes a
complete per-run behavior file. Bots reload it approximately once per second; invalid or partial edits
retain the last valid rules. Roster, chat, map, rank, and team changes take effect on the next session.
The manager starts the roster after the transports are ready and stops its process group before server
teardown. A bot-runner failure cleans up that roster and reports an error while the human server stays
running. See the [control/lifecycle receipt](../qa/bots-server-controls.json); its process and
rendered-browser checks use helper clients, not live game simulations.

## Peace, perception, and provocation

Remote weapon identity comes from the ordinary synchronized weapon mesh. A remote `curWeaponID` is not
reliable local inventory state. `fistg.3do` identifies fists, while explosive weapon models remain
armed. Peace is tracked separately for each bot and peer, bound to network ID, thing GUID, and thing
signature. An observed death or identity change clears the previous relationship.

Each detected provocation lifts peace protection for 15 seconds after the most recent event. Attributed
damage follows valid projectile-parent signatures. Aimed incoming projectiles and nearby punch attempts
require a sight-line and direction check; projectile identity distinguishes a punch from a gunshot even
when its shooter has already switched back to fists. Hostile targeted Force events also count. Four
weapon changes within three seconds nearby and in view, or roughly three seconds of persistent
obstruction of intended movement, count as provocation. Brief contact, passing in front, and distant
punching do not.

These are bounded heuristics, not a claim to infer human intent. Environmental damage, self-hits, and
stale ownership do not blame the nearest player. Stock Force Throw can accelerate loose debris without
assigning its caster as the owner or sending a targeted skill event: that damage cannot always be
attributed to the human caster, so it remains a gap in the peace rule. Blind bots suppress target
acquisition and fire; a persuaded opponent requires the bot's active Seeing before becoming a target.
Teammates and unassigned CTF lobby players are excluded from enemy targeting. See [policy
fixtures](../native/tests/test_bot_behavior.inc).

## Gun decisions and attack restraint

Weapon choice considers actual availability, ammunition, range, sight lines, and nearby protected
players, with selection hysteresis to avoid constant switching. Aim uses bounded projectile-speed
prediction. The stormtrooper rifle uses longer-range bursts, and close repeater alternate fire requires
enough ammunition and a wider clear firing corridor. Splash weapons require separation from the bot and
from protected players near the target.

The bowcaster uses its immediate alternate shot. Its stock charged primary fires on release, so simply
releasing attack when a target becomes peaceful would otherwise fire the pending bolt at that player.
Hand-thrown thermals and planted sequencer charges are omitted until trajectory and trap planning are
adequate. Ordinary sight, corridor, and blast checks reduce accidental hits; ricochets, player movement,
network delay, and already-fired projectiles remain limits. Live checkbox changes cannot remove
projectiles already in flight.

## Legal Force builds and power strategy

Before joining, the bot writes a normal multiplayer character using the actual advertised rank. The
stock budget is three stars per rank, up to four per power. Neutral powers become accessible at rank 1;
successive side powers at ranks 4–7. The normal profile-loading path installs the saved allocation. The
driver does not inject mana, stars, ammunition, or health during play.

Kyle is light/balanced; Boba, Trooper, Bossk, Greedo, and Yun are dark/balanced. Jan and Sariss request
light/dark master builds respectively. At rank 8, those master builds spend 16 stars on their four side
powers, leave eight unspent, and let the stock editor rules derive Protection or Deadly Sight. They have
no neutral powers at that rank; lower ranks use balanced allocations. These are project personas, not
canonical character-ability claims. The [loadout tests](../native/tests/test_bot_loadout.c) cover the
rank budgets.

In range formulas, `L` means stars in that power (1–4), not the session rank.

| Power | Decision and ordinary-input behavior |
|---|---|
| Jump | A validated route gap with sufficient rank/mana; ordinary charged hotkey and landing checks. |
| Speed | A sufficiently long, verified supported walking segment rather than a drop. |
| Seeing | Blindness or recent damage with no visible target; stock effects must actually clear blindness. |
| Pull | Disarm an eligible gun user within `0.5 + L/2` world units. |
| Healing | Low health, with the stock mana and availability gates. |
| Persuasion | Very low health after higher-priority defensive opportunities. |
| Blinding | Eligible target within `1 + L` world units. |
| Absorption | Recent attributed hostile Force threat. |
| Protection | Recent damage and reduced health, when the master power exists. |
| Throw | Nearby debris and an eligible target within four world units; restricted as below. |
| Grip | Eligible target within one world unit; hold for targeting, then release. |
| Lightning | Short held burst with clear aim and protected-player checks. |
| Destruction | A distant target with conservative splash clearance. |
| Deadly Sight | Multiple nearby enemies, only outside peace/team play. |

Availability, cooldown, control/blindness state, mana, sight, range, and target eligibility gate
requests. Surge pickups waive some stock consumption, but the scripts still require nominal mana to
activate. A requested hotkey is not proof of a successful effect; `BOT_FORCE_INPUT` records the request
only.

Pull, Grip, and Blinding have stock deselection handlers, so a held cast can be cancelled before release
when its target becomes protected. Throw's deselection only hides its marker: cancellation holds the key
and looks away until the bot's own stock COG reports no victim, then releases. This reads the COG value
without modifying it. Deadly Sight has no cancellation handler. New Throw and Deadly Sight casts are
disabled under fists-peace or team play. If a live switch conflicts with already-active Deadly Sight,
the bot suppresses fire and turns away until its normal lifetime ends. Existing stock effects are not
revoked.

## Items, routes, and coverage terminology

The [read-only map audit](../qa/bots-stock-map-audit.json) classifies all 700 authored pickups across
the nine stock maps and validates the stock CTF instance's flag, base, and selection-sector references.
That is catalog coverage. The audit's `world.things` is reserved capacity; `authored_things` counts
placed things. Neither is a count of successfully collected items. Recognized categories also include
items deliberately omitted from collection goals, such as goggles, hand thermals, and sequencer charges.
Flags use objective handling instead of ordinary pickup utility. Runtime priorities
consider need, availability, weapon/ammo rules, health, shields, bacta, mana, useful powerups, and CTF
keys. Item respawn estimates come from observed disappearance; absent items receive only a small
near-respawn preference rather than indefinite camping.

Runtime graph generation uses loaded geometry and authored locations. It checks world surfaces,
stationary mesh floors and blockers, low ceilings, ordinary jumps, bounded drops, and swimming routes.
Force-jump routes prefer a short charge; higher allocations can use longer charges after checking both
the nominal arc and a slightly higher clearance envelope. Actual rank, mana, takeoff position, and
collision are checked again before the ordinary jump input.

Mover support is limited to recognized nonrotating lifts with two path frames. The bot checks platform
presence and attachment, uses ordinary activation, and waits or replans. This does not solve arbitrary
switch sequences, rotating platforms, every stock trap, or every lift's access puzzle. Route recovery
and objective urgency influence movement. The coverage logs distinguish the
following stages:

| Stage | What it establishes |
|---|---|
| Classified | The item's template/model maps to a recognized pickup category. |
| Anchored | A candidate node represents the item; that node may have no usable edges. |
| Reachable | A graph route exists from the sampled origin under current constraints. |
| Traversed | A live bot actually followed the route and reached the destination. |

`BOT_NAV_READY`, `BOT_NAV_COVERAGE`, and `BOT_NAV_UNREACHABLE` expose missing nodes, graph truncation,
and unreachable items. Coverage describes the sampled origin and resource constraints. A CTF lobby is
separate from its arena, so a zero-pickup lobby component is expected; coverage is sampled again after
an actual team transition. Potential graph edges do not prove that a closed door opens, a lift arrives,
or a landing succeeds. A complete classification or successful graph search does not establish all-map
traversal, every lift, reliable landings, or successful item collection. See the [navigation
fixtures](../native/tests/test_bot_navigation.inc) for controlled cases.

## Stock CTF teams and objectives

The launcher requests alternating red/gold teams. `requested_team` in a receipt or API response is a
request, not proof of assignment. The driver seeks a reachable approach to the actual entrance of the
requested team's mark sector. These stock entrances lead into deep teleport shafts; the driver targets
the entrance instead of the shaft floor. It uses a bounded, collision-checked movement attempt and then
waits for the stock server response. `BOT_CTF_ENTRY` records a discovered approach, not successful entry.

The stock COGs assign the team after a player enters the mark sector, apply red/gold team models and
sabers, and teleport into the arena. Their roster skin therefore
gives way to the required team appearance while names and chat personas remain.

Objectives include taking the enemy flag, recovering a dropped own flag, intercepting its carrier,
returning home with the enemy flag, escorting, and defending. Carrier decisions use synchronized flag
attachments matched to active player identities, rather than remote inventory amounts or unsynchronized
server COG locals. A lone bot takes the attacking role. With multiple teammates, a roster-identity
heuristic keeps one attacking role and assigns the other bots to defense; human teammates are included
in that roster.

Scoring requires touching the own flag at home while carrying the enemy flag. Ordinary movement and COG
events perform this work. The bot does not write flag ownership, score, or position to satisfy an
objective. An objective log establishes the selected intention; a capture needs observed flag
possession and release, return to the scoring location, and the corresponding stock score/event result.

## Shared server spawn-count correction

Stock CTF initially masks out starts 0–15 and requires lobby starts 16–31. The old GNS connection
callback overwrote the authored player/spawn count with the configured session capacity. At capacity
eight this left no allowed lobby spawn; the stock selector fell back to start zero, leaving team-zero
players in the arena. The correction preserves authored records and their ordinary `SyncPlayers`
representation. A separate common join allocator enforces the configured capacity, including the
dedicated host, for every transport.

The [five-group source regression](../qa/server-ctf-spawn-regression.json) exercises the actual
selector, allocator, and serializer: all lobby starts; distinct red/gold ranges; host plus seven humans
at capacity eight; refusal and reuse of eligible slots, shorter maps, and invalid capacities; and all 32
records serialized without raising capacity. It also reproduces the old count-eight fallback. These
checks stub collision and delivery; connected confirmation must come from the rebuilt server, not the
unit receipt.

## Source workflow, builds, and evidence lineage

[SOURCES.json](../bots/SOURCES.json) pins the engine fork at `74e4657c4f1751d09af9ad9e056acb8f41997acb`
and the JK/MotS COG Workshop at `ab3c4782ab7b474f2ab5def503eb8afd5065cfef` (0.1.6). Same-game stock COGs
were inspected for lifecycle, bins, cancellation, and CTF bindings. Historical bot projects informed
research; their synthetic-player code and proprietary game archives were not imported. Roster provenance
is recorded separately.

The build method recompiles changed translation units and links verified unchanged objects and static
dependencies from the pinned base. This is not described as a fresh build of every dependency. Full
source-build recipes are provided by [build_bots.sh](../native/build_bots.sh) and
[build.sh](../native/build.sh); patch, source, dependency, and artifact records belong in
[BOT_BUILD.json](../native/BOT_BUILD.json) and [BUILD.json](../native/BUILD.json). Match exact binary
hashes to each receipt.

The [intermediate rank-eight probe](../qa/bots-force-profile-probe.json) records legal saved-character
state for Jan and Kyle in two connected clients; it explicitly does not claim Force casts or final-build
qualification. Earlier `bots-recovery-*` and `bots-final-*` receipts belong to the older rank-zero
[recovery report](BOTS_PROTOTYPE.md). “Final” in those filenames does not qualify this extension.
Current control, catalog, and server-source receipts each state their own limits; fixtures never stand
in for connected gameplay.

## Connected gameplay qualification

Each receipt identifies the executable actually observed. Later navigation fixes do not retroactively
qualify an earlier binary as the current package. The packaged source and relink verification are in
[the current build receipt](../qa/bots-feature-build.json).

### Mixed clients, combat, Force and live rules

The `cd64c7b9` bot candidate ran four bots alongside original JK 1.00 retail, the unchanged pinned
OpenJKDF2 client, and the unchanged published JKWeb client on `JK1MP/m2.jkl`, rank eight. The active
roster contained all seven playing clients plus the dedicated host. Movement and the final scoreboard
were observed across the clients. The [mixed-client receipt](../qa/bots-feature-mixed-cd64.json),
[combat receipt](../qa/bots-feature-combat-cd64.json), and
[native peace receipt](../qa/bots-feature-native-peace-cd64.json) preserve the exact binaries and limits.

Actual bot-owned projectiles and ammunition changes established Bryar, stormtrooper rifle, repeater and
rail firing. Recorded game state established Healing, Protection, Grip, Seeing, Absorption,
Destruction, Speed and Force Jump, together with ordinary bacta consumption. Pull and Blinding had
stock cost/release observations without an independently established victim effect. Lightning's
emission was inferred from the stock cost path; impact was not established. Persuasion, bowcaster and
concussion firing were not witnessed. Throw and Deadly Sight were deliberately withheld by the
peace/team policy. These distinctions matter: a requested hotkey alone is not a completed effect.

A real panel update enabled saber-only and disabled Force without replacing the bot processes. After
settling, 820 observations over approximately 104 seconds showed no new bot-owned projectile, ammunition
loss, mana spend or Force input. Existing buffs expired normally. Fists-out native and retail players
had bounded observed peaceful intervals; the retail receipt also records a later unexplained death and
does not attribute it to the bots. The attempted live rapid-swap/punch provocation did not meet the
policy conditions, so retaliation remains covered by source fixtures rather than that live attempt.

### Nine stock maps and CTF

The `d45532cb` candidate completed all nine stock-map runs with dedicated candidate `0e90`, producing
2,275 valid observations and no observer errors. The [stock-map receipt](../qa/bots-feature-stock-maps.json)
records the exact hashes, graph counts and cleanup. All 700 authored pickup records were classified;
classification is not proof that each pickup can be reached or has been collected.

| Map | Connected outcome in that candidate |
|---|---|
| The Duel (`c1`) | Actual red team, three captures and a subsequent enemy-flag pickup; score 57. |
| The Arena of Dark and Light (`c2`) | Actual red team, four captures; score 72. |
| The Challenge at Nar Shaddaa (`c3`) | Actual red team and ordinary lift traversal; no flag pickup or capture. |
| `m2`, `m4`, `m5`, `m10` | Item gains observed during the bounded runs. |
| `m_boss15` | Left the spawn area, visited 14 sectors, gained shields and bacta. |
| `m_boss17` | Stalled near its initial anchor; no item gain. |

Those runs exposed a false walk route through a low raised window on `c3` and an unclassified initial
jump on `m_boss17`. The current package rejects the false grounded passage and classifies the initial
self-to-anchor segment using the existing collision-checked ordinary jump logic. The focused
[grounded-clearance regression](../qa/bots-c3-grounded-clearance-regression.json) and
[initial-anchor regression](../qa/bots-initial-anchor-regression.json) reproduce the earlier failures.
They do not establish successful connected traversal by themselves. Targeted current-build results
are recorded separately below; no all-map or complete CTF mastery is claimed.

Earlier `acf75700` CTF runs and resource-limited attempts are retained as historical receipts. Startup
attempts that never entered gameplay, including an out-of-memory fixture failure, are excluded from
connected qualification. The [resource receipt](../qa/bots-feature-fixture-resources.json) records that
boundary instead of treating a successful build or requested team as gameplay evidence.

### Focused checks of bot 5092 with dedicated 6c4c

Bot `50924ed7` and dedicated server `6c4c25dd` completed two serial solo matches, producing 676 valid
observations with no observer errors. The [focused receipt](../qa/bots-feature-focused-5092.json)
records the complete binary and source hashes, map evidence, and normal cleanup of both fixtures.
There were no additional out-of-memory kills during these runs.

On `c3`, the bot joined the red team and traversed 30 arena sectors using the alternate route around
the previously rejected low opening. It then stalled at a stock gold-key door while holding only the
red key. No enemy-flag pickup or capture occurred during the 240-second check. Read-only graph analysis
found that excluding the known gold-door crossings disconnected the available routes to both the
enemy-flag approach and the gold-key pickup. This identifies a current routing limitation, not an
absence of legal human routes: the bot has no validated alternative key-acquisition or capture route
there. A door exclusion alone would not complete CTF play, so no such source change was applied.

On `m_boss17`, the bot left its observed starting area and moved through nine sectors during the
100-second check, but no inventory pickup was recorded. This match first observed the bot in sector 27;
the earlier failing match began in sector 29. It therefore demonstrates movement from the new observed
spawn without establishing that the exact earlier starting edge was traversed successfully in live
play. Item acquisition and all spawn variants remain unqualified by this run. These focused results
supplement the source-specific `d45532cb` nine-map receipt; they do not replace it or establish a fresh
nine-map qualification of `50924ed7`.
