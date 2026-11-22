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

Weapon choice considers the bot's inventory, ammunition, range, line of sight and nearby protected
players. The stormtrooper rifle fires in bursts at longer range. Elite bots use the repeater's
three-bolt secondary at close range when they have three cells, the spread fits the target at the
current aim angle and the wider firing corridor is clear. Otherwise they use its single-bolt primary.

The concussion primary leads moving targets and can aim at the floor for splash. Elite bots keep a
clear, predictable floor shot when they have at least 16 cells and enough separation from the blast.
For a crossing target, unsafe splash, or a tighter cell reserve, they can take a direct secondary shot.
The stock beam reaches five world units, requires eight cells to activate and spends four per shot.
The bot checks that both the planned line and its current barrel would reach the intended opponent
first. A wall, moving lift or intervening player can block the shot. Rail uses its impact primary.

Against a nearby, facing Bryar or stormtrooper rifle, an elite gun bot can draw its saber and keep
both attack buttons up so stock bolt defense stays available. At contact it uses a primary swing.
It reserves the slower heavy secondary for a grounded, dry attack on an immobilized opponent,
with a clear area around the bot.

The bowcaster uses its immediate secondary. Its charged primary fires on key release, including when
a target becomes peaceful. The bot also leaves thermal throws, sequencer placement and delayed rail
traps to strategies that can account for their eventual detonation. Movement, ricochets and network
delay still affect projectiles after they leave the weapon. The optional `BOT_FIRE_INPUT` trace
records changes in requested firing mode at most twice per second. See the
[weapon mechanics and alternate-fire checks](../qa/bots-alt-fire.json).

### Competitive guns: equipment and movement

In elite gun modes, acquiring useful supplies remains a movement goal during an engagement. The bot
can follow graph routes toward weapons, ammunition, health and other useful pickups while aiming and
firing at an eligible opponent. An existing E11 or a single rail charge no longer ends equipment
seeking. A disarm leaves the actual stock inventory unchanged and can trigger a route to a replacement.
Close contact, breathing, committed traversal, recovery and CTF objectives retain their own priorities.
Companion resource and recover directives keep the ordinary mode-aware route planner active in combat;
pressure retains its requested engagement behavior.

Dropped backpacks are evaluated from their replicated contents, available weapons, ammunition and
remaining capacity. A destination is bound to its thing index, GUID, signature and position, and is
discarded when the drop moves, changes identity, expires, becomes useless or reaches contact. Existing
graph nodes supply approach routes, including the closest node when it is the only approach. Both
the leg to that node and the final span to the pack must be traversable. Temporary drops do not
become permanent graph nodes. The controller cannot award a pickup. The stock contact and multiplayer
acknowledgment paths perform that action. See the [equipment routing receipt](../qa/bots-equipment-routing.json).

An underwater supply attempt yields to the air threshold. After at least 4,000 ms on the stock
endurance counter, touching the planned item also starts a return to air. The bot observes the stock
collision handler immediately before it sends `TOUCHED`. At that point the item has passed the
handler’s contact checks, and the host may still be deciding whether to award it. The bot can
therefore leave for air even if the acknowledgment arrives later or the drop disappears on touch.

The bot remembers up to eight abandoned supply identities, each for 45 seconds. A ninth outstanding
failure defers further underwater supply selection for 45 seconds while dry supplies remain eligible.
Each entry matches the item slot, GUID and signature. A respawn or world change clears the history.
After its breathing counter resets, the bot can continue toward a checked bank for six seconds.
See the [supply recovery tests](../qa/bots-supply-recovery.json).

The source revision tested after the third trial also remembers the last supported bank and the
first wet sector of a failed supply dive. After at least four seconds on that attempt, a return for
air can defer optional underwater pickups and exploration through that entry for 45 seconds.
This applies in autonomous elite gun play at 40 HP or more with four heavy primary shots in reserve
(32 power cells and an available concussion rifle, or four charges and an available rail detonator).
A dry pickup, pursuit or an air route can still cross the water there. A different bank can still
reach the same submerged item. Underwater equipment rescans keep the destination of a transit trip,
and cached optional descents are checked again before entry. During the retry a projectile sound
that only turns the bot can yield movement to navigation while on dry ground or traversing the
known crossing. [Supply approach regression](../qa/bots-supply-approach-retry.json)

Candidate 5 extends the same 45-second retry to optional equipment on dry ground. A spare gun,
surplus ammunition or pack without a needed refill can still justify a route via another bank.
Ammunition below 15% of its stock capacity for an available, owned gun can justify the original
crossing. A duplicate rack can supply that refill. Needed dry health and shields, pursuit and air
retain the full route search. The planner rechecks a cached descent after the bot’s reserves
change and keeps a necessary destination through an underwater rescan. If the bank offers no
productive alternative, it can choose a dry waypoint across the water for exploration using
distance and visit age, without giving the weapon a bonus. Independent review accepted these
source decisions. Their effect in a four-player match awaits a candidate-5 recording.
[Dry supply detour regressions](../qa/bots-dry-supply-detour.json)

Shoreline routes use a checked water entry or bank jump. A short swim to a
nearly level bank requires full-body clearance to supported floor in the dry sector directly above
the swimmer. In Canyon Oasis, all seven retained shallow exits reached their destination floor in
15 and 30 Hz replays. One 12 Hz gear run recovered air but did not reach sustained dry support within
70 seconds. See the [underwater gear replay](../qa/bots-underwater-gear.json).

For a bank jump, the predicted touchdown must have a dry floor or supported rim. The remaining
walk to the anchor may span up to 0.16 world units and must have continuous support. This recovered
two approaches whose final walk exceeded the previous 0.14-unit limit. The host replay of each
engine source reached sustained dry support in all 27 cases. One older approach took an additional
4.367 seconds and reached the bank with the same 60 HP. See the [bank landing matrix](../qa/bots-bank-landing.json).

The Bryar yields to loaded ranged upgrades, and an available heavy gun is readied between contacts.
Against a recognized concussion or rail user, the bot keeps a usable gun instead of voluntarily drawing
a saber. A saber remains an equipment fallback or a close, same-height opportunity. These decisions do
not make the bot immune to disarms or remove ordinary movement and turning costs. In particular,
simultaneous aiming and pickup travel is implemented; an instantaneous turn-and-fire maneuver is not.

## Legal Force builds and power strategy

Before joining, the bot writes a normal multiplayer character using the actual advertised rank. The
stock budget is three stars per rank, up to four per power. Neutral powers become accessible at rank 1;
successive side powers at ranks 4–7. The normal profile-loading path installs the saved allocation. The
driver does not inject mana, stars, ammunition, or health during play.

All eight shipped profiles now request `competitive`. Kyle and Jan are light; the other six are dark.
At rank 8 both sides put four stars in Jump, Speed, Seeing and Pull. Dark adds Grip and Destruction;
light adds Absorb and Healing. Lower ranks allocate one level at a time across the eligible powers.
The dark allocation follows historical BGJ guidance; the light allocation is a legal engineering
baseline to measure, not a claim about a champion's exact build. See the
[Force source audit](../qa/bots-force-source-audit.json).

Custom profiles retain `balanced` and `master`. At rank 8, a master spends 16 stars on the four side
powers and leaves eight unspent so the stock editor rules derive Protection or Deadly Sight. Its lower
ranks use balanced allocation. An omitted custom style remains balanced. The
[loadout tests](../native/tests/test_bot_loadout.c) cover all 54 rank/side/style combinations.

In range formulas, `L` means stars in that power (1–4), not the session rank.

| Power | Decision and ordinary-input behavior |
|---|---|
| Jump | A validated route gap or first-anchor approach with sufficient rank/mana. Full charges reach the stock rank limit. A sustained grounded movement stall can consider up to four nearby higher footholds using actual body clearance, stock air movement, current control cadence and a supported landing. Ordinary hotkey hold and release perform the jump. |
| Speed | Competitive bots can use Speed while closing distance, backing away, strafing or following a pickup or walking route. They check the ground and body clearance in the direction they will actually move. Balanced and master bots use Speed on verified walking segments longer than two world units when they have no eligible target. |
| Seeing | Current local Blind, or an eligible hostile player's synchronized Persuasion effect within the normal forward view, range and line of sight. Both the twinkle and actor invisibility flags must identify Persuasion; Force Jump's twinkle alone does not count. Ordinary combat, damage and generic Force threats do not trigger it. Stock Seeing prevents subsequent Blind effects; it does not cure an existing Blind timer. |
| Pull | Disarm an eligible gun user within `0.5 + L/2` world units. |
| Healing | Low health, with the stock mana and availability gates. |
| Persuasion | Very low health after higher-priority defensive opportunities. |
| Blinding | Eligible target within `1 + L` world units. |
| Absorption | Recent attributed hostile Force threat; competitive style can also prepare during a visible engagement. Urgent healing remains first. |
| Protection | Recent damage and reduced health, when the master power exists. |
| Throw | Nearby debris and an eligible target within four world units; restricted as below. |
| Grip | Eligible target within one world unit; release initiated by the controller requires the intended identity and local COG victim to match. A valid ongoing Grip permits weapon/Bacta input and prevents automatic Force switching. |
| Lightning | Short held burst with clear aim and protected-player checks. |
| Destruction | A distant target with conservative splash clearance. |
| Deadly Sight | Multiple nearby enemies, only outside peace/team play. |

Availability, cooldown, control/blindness state, mana, sight, range, and target eligibility gate
requests. Competitive style uses a 0.15-second guard between power requests; legacy styles retain
2.4 seconds, and all styles respect COG-owned per-bin waits. Surge pickups waive some stock
consumption while most powers still require nominal mana to activate. Protection is an exception:
its stock script deducts mana without a minimum-mana gate. A requested hotkey is not proof of a
successful effect; `BOT_FORCE_INPUT` records the request only.

Competitive bots consider Speed after selecting their movement, weapon fire and other Force input.
A ground cast needs 0.60 world units of dry, supported ground ahead and a clear sweep for the player's
whole body. A selected walking waypoint or pickup must also be at least that far away. A bot can
keep firing while it presses the Speed hotkey. It defers Speed during Grip, jump preparation or
flight, water exits, lift waits and obstacle recovery. On a direct underwater supply leg, the bot may
use Speed when the pickup is ahead in the same sector, the full body can reach it, and the first
0.40 units have extra clearance. It also requires good health, breathing time and a control interval
of at most 70 milliseconds.

Stock Speed costs 20 mana. A competitive bot normally waits until it has at least 60, leaving at least 40
for Jump and Pull. Either stock Force surge waives the debit while retaining the 20-mana minimum.
At four stars the stock script adds 2.5 thrust and sets a 15-second timer, then fades the sound for
0.75 seconds before clearing the effect. During a committed precision jump the bot eases its
ordinary movement inputs while Speed is active, so its landing plan also applies if the effect
expires in flight. See the [Force Speed checks](../qa/bots-force-speed-followup.json).

The new full-charge prediction models the repeated scaling of airborne thrust
between browser control frames. It may reject a ledge at a slow control rate
that is reachable at a faster one. Recorded-pose replay verifies one Canyon
Oasis recovery at 30 and 60 Hz; this does not establish every jump or frame
rate. Recovery excludes water, active objectives and other pending powers.
Charging and committed flight retain navigation's heading, and a loss of
support ends the held key. No change is made to the stock jump script, mana,
cooldown, collision or physics. See the
[movement and Force follow-up](../qa/bots-movement-force-followup.json).

The controller cannot suppress the stock inventory handler's own forced release when actor controls
become disabled during a held power. That handler sends `DEACTIVATED` before a next-skill cancellation
can be processed; Grip can then act on its stock-selected eligible victim. This differs from turning
off the bot's Force setting while ordinary controls remain available. Target-verified release describes
the controller's initiated action, not an override of every stock engine release path.

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

An elite competitive guns bot already moving toward a pickup can also tap Force Jump when a visible
opponent points a concussion rifle toward it. The bot checks its momentum, body clearance and landing
on the same dry floor. It can turn and fire a Bryar, stormtrooper rifle, bowcaster or repeater while
coasting, then resume the pickup route after landing. Rail and concussion shots push the shooter, so
the bot defers this hop with either heavy mounted and defers drawing or firing them during the hop.
In paired synthetic floor-shot replays, raw splash fell from 78.34 to 20 at 13 Hz and to zero at 15,
20, 30 and 60 Hz. The jump also reduced progress toward the pickup over the three-second comparison.
The [combat jump receipt](../qa/bots-combat-jump.json) records the shot, timing, landing and input results.

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

### Third refinement trial on Canyon Oasis

**The build failed the sustained-movement check.** Four hardware-accelerated clients ran for
240.002 seconds without directed commands or observed chat. Lily’s third-person model rendered
with side material `saberred1.mat` and tip material `saberred0.mat`. She reached dry sector 41
on multiple occasions, chose other underwater supplies and dived again. Her trace contained 659
wet states among 840 living observations, with 189.055 seconds across 17 intervals confined
within a horizontal radius of 0.13 units. Those intervals allow vertical motion.

Across all 19 returns for air, the trace showed no same-life replan for the identical failed item
within its 45-second retry interval. Lily nevertheless spent much of the clip already armed with
concussion and rarely had a target during the long final life. Yun requested concussion and repeater
secondary during the clip. Lily’s retained trigger changes in the clip showed Bryar and fists
primary. These changes measure requested inputs. They cannot establish hit or kill attribution.
[Full match comparison and capture verification](../qa/bots-refinement3-live.json)

### Four-minute Canyon Oasis equipment trial

In a four-bot, full-Force guns match on Canyon Oasis (`m10.jkl`), the second refinement candidate
ran autonomously. Lily’s sampled score went from 0 kills and 0 deaths to 6 kills and 2 deaths.
Across 810 distinct fresh living states, she had a target in 298 and used eight weapon bins.
The trace recorded six backpack plans, 20 same-life samples with increased ammunition, and
secondary-fire input for bowcaster, repeater, concussion rifle and saber. The sampling cannot tie
each ammunition gain to a particular pack or each attack request to a shot, hit or kill.

The same recording exposed prolonged confinement near the pool. Boba stayed within 0.13 horizontal
world units of one point for the final 54.087 seconds of his sampled interval. Lily had a similar
10.072-second interval at the end. Both moved vertically. Brief crossings into an air sector were
insufficient evidence of a supported bank landing. In stock-physics replays on the recorded build,
two Boba poses timed out at 74 and 87 ms control intervals. At both poses the landing predictor
rejected a supported final walk longer than its 0.14-unit limit. The recording preceded the
[supply recovery changes](../qa/bots-supply-recovery.json).

### Competitive Force candidate (`fc533197`)

The candidate was run against the unchanged packaged dedicated server in two
isolated native sessions using the original stock data. Both sessions loaded
the intended rank-eight builds through the ordinary character path: all 736
post-join state samples matched the selected six four-star powers. The tests
used normal weapons, enabled Force, disabled fists peace and disabled chat.

On `m2.jkl`, the clients remained joined for 105 seconds after the second join.
Both requested Jump and showed stock mana changes and sampled active Jump
state. No other Force input or player target appeared in those records. This
run verifies native join and loadout integration, not combat proficiency.

The additional 75-second `m_boss17.jkl` run sampled mutual player targets.
Both clients showed active Seeing. The light client showed active Absorb and
requested Pull and Healing; the dark client requested three Destructions, one
Pull and one Grip. The dark client's Grip bin was sampled active ten times;
the separate light-client trace sampled immobility nine times and recorded
health changes. These are paired observations from ordinary play. They do not
isolate exact damage attribution or prove every requested offensive effect hit.

The receipts are [m2](../qa/bots-competitive-force-native-m2.json) and
[m_boss17](../qa/bots-competitive-force-native-m_boss17.json). The
[bounded harness](../qa/competitive-force/README.md) records the packaged and
stock-map hashes, uses private copies of the required inputs, and stops its
owned process groups. Neither run used current upstream JKWeb, a human player,
simulated network latency, or every supported mode/map. Elite player strength,
reliable encounter routes, predictive splash and the external companion remain
unqualified by this evidence.

Each receipt identifies the executable actually observed. Later navigation fixes do not retroactively
qualify an earlier binary as the current package. The [competitive Force build receipt](../qa/bots-competitive-force-build.json)
records the current package and its relink verification. The [historical build receipt](../qa/bots-feature-build.json)
covers bot `50924ed7`.

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
