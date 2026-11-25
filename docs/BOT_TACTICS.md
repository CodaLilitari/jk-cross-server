# Bot movement, tactics and the coach seat

This describes the engine overlay in `native/bot-tactics.patch` and the Python
around it. It builds on the competitive bot branch and changes four things:

1. The bots run. Until now they have walked everywhere.
2. The planner stops sending bots into water for small rewards, and still
   sends them in for a heavy gun.
3. A bot that keeps moving without getting anywhere is detected and made to
   go somewhere else, for longer each time it happens again.
4. The numbers behind those decisions, and a few older ones, are named
   tactics that a file or a live controller can change without a rebuild.

**Status.** The overlay is source. It is not in the packaged binaries, which
still match `native/bot-client.patch` and `web_bots/engine.patch` and their
build receipts. It has passed fixture tests and a check against the engine's
own physics code, and bot clients built from it have played bot-only matches
on Canyon Oasis. It has not been played against people.
See [Evidence and limits](#evidence-and-limits) and
[Building and trying it](#building-and-trying-it).

## The bots have been walking

The stock ground controls double a player's thrust while the run key is held
or the Always Run option is on (`sithControl_PlayerMovement`). The bot client
starts with that option off and its input code never pressed the run key, so
every bot has moved at walking speed. Forward and strafe thrust also add
without being normalised, which is why players who hold both keys and turn
the body about 35 degrees off their path move faster still.

`native/tests/run_stock_ground_tests.py` drives the engine's own ground
physics and movement control with the bot's inputs on flat ground:

| Input | Settled speed (units/s) | Relative |
| --- | --- | --- |
| Walk, as the bots moved before | 0.667 | 1.00 |
| Run key | 1.333 | 2.00 |
| Run key and the forward-plus-strafe diagonal | 1.628 | 2.44 |

Both are ordinary inputs. Neither axis ever exceeds one full key, and the
test asserts it. A player with Always Run on gets the same thrust.

## Movement

- **Run.** With `always_run` (default 1) the bot holds the run key on all
  dry ground and walks only where a running bot could not stop short of
  trouble. It looks one running stop ahead (the coast at the speed about to
  be reached, plus a quarter unit) for a pit, a drop off a ledge of more than
  0.28 units in all, water, a thrust sector or a floor that hurts. A wall, a
  step up or another body ends the look instead, since running into them
  costs nothing, and a ramp down is floor, not a drop. Ice, water surfaces,
  crouching and unknown surface drag are walked. The legacy rule
  (`always_run` 0) ran only where the whole body had a clear, drop-free
  corridor for that distance, so any wall or step down ahead meant walking.
- **Where.** The route follower runs corners and the end of a route, the bot
  runs onto a pickup over the last span and toward a sound it investigates,
  and fights run whenever the check allows. It still arrives walking at a
  jump, drop or lift leg, stopping the run `run_brake` units before one, so
  jump and water-exit timing still start from close to walking speed. The
  legacy route follower also walked into corners sharper than about 25
  degrees and the end of a route.
- **Exact thrust.** The old axes pushed up to 10 degrees off the wanted
  direction whenever the body faced elsewhere, which is most of a fight.
  The new axes put the thrust exactly on the wanted line.
- **Diagonal.** On a straight of at least `strafe_min_leg` units with a
  longer clear corridor, the bot uses both keys and, when no opponent owns
  its aim, turns its body off the path so they add up along it.

Stock Force Speed adds to thrust, so the corridor check asks for a
proportionally longer runway while it is active.

## Water

Three tactics replace the old behaviour, in which unvisited underwater
places and any small pickup counted the same as dry ones:

- `explore_wet` (default 0): underwater places earn no exploration value.
- `dive_min_value` (default 6): a submerged pickup worth less than this is
  not a destination and is not chased as equipment. A missing concussion
  rifle (18), rail detonator (12), repeater (10) or other gun (8), health
  when badly hurt (16) and shields when nearly gone (8) all still qualify.
  Ammunition top-ups and spare mana do not.
- `water_entry_cost` (default 4): added to the path cost of every step
  into water, so a dry route wins unless the swim saves real distance.

Three more came out of the first live matches (see Evidence):

- `swim_pitch` (default 1): stock swimming thrusts along the view, and the
  forward key is twice as strong as the rise and sink keys. The bots sank
  and rose on those keys alone. A steep leg is now swum the way a player
  swims it: look along it and push forward. In the matches the median sinking
  speed went from about 0.25 to about 0.6 units a second.
- `crossing_seconds` (default 17): the engine gives twenty seconds of air.
  The bots turned back after `dive_seconds` (8) whatever they were doing,
  which made any swim longer than that impossible and, on Canyon Oasis,
  trapped them on the concussion rifle ledge: the only way off is a swim
  they kept abandoning at the bottom of the shaft. A swim whose route comes
  out on another bank may now take this long; a dive to a pickup on the
  bottom is still held to `dive_seconds` each way.
- `dive_retry` (default 45): a swim is judged before the bot gets wet, and
  one that cannot fit is refused. If a bot does turn back for air, that way
  into that water and the place it was heading for are set aside for this
  many seconds, so the same dive is not repeated at once.

`water_slip` (default 1): a bot that ends up in water on a leg meant for
dry ground (it walked off a pool edge, or a jump fell short) no longer
presses jump at the surface toward a ledge no hop can reach. In the first
recorded match that loop splashed five times in four seconds. It sets the
leg aside for 15 seconds and replans from the water, which routes it out
through a checked bank exit or a Force Jump from the surface. In a 300 s
match the two bots on the defaults slipped seven times and were out within
2 to 6 seconds each time.

Every step from a bank into water now carries `water_entry_cost`; in the
first version only one kind of entry did, and pool edges were free. The
bank exit itself is unchanged.

## Running jumps

The stock Force Jump script adds its upward speed to whatever velocity the
player already has, so a jump released at a sprint keeps the sprint through
the air. With Force Speed that crosses gaps no standing jump can. The bots'
only Force Jump was a standing one of at most 1.2 units. `run_jump`
(default 1) adds the running kind, from ordinary inputs: the run key, the
movement axes, the jump key and the two Force keys.

- **Solving.** After the ordinary graph is built, each dry node is offered
  the landings that would save it the longest way round (at least three
  times the gap plus four units) across a real gap. For each, the run-up is
  whatever straight level floor lies behind the launch node, from 0.3 units
  up to the length that reaches full speed. Launch speed follows from the
  stock rule that ground speed is thrust over drag: Force Speed adds
  0.5 + rank/2 to a thrust of 2, the run key doubles it, a strafe adds 22
  percent. The Force Jump hold (upward speed 2.5 + hold, hold at most
  0.35 per rank) is then solved so the flight comes down on the landing
  node, at no more than 2.95 units a second, which costs under ten health.
  Three flights at 90, 100 and 109 percent of the launch speed are swept
  through the level and must all find the foothold with room to stop.
- **Jumping.** The bot walks to the start of the run-up, brings up Force
  Speed if the plan needs it, stands and faces the line. The Force Jump key
  and the sprint are both timed back from one release moment, so the key
  comes up as the sprint reaches the launch node. Run-ups are often shorter
  than the stopping distance, so there is no abort once the sprint starts.
- **Using.** The planner takes such an edge only with the ranks it was
  solved for, the mana for both powers, 40 health or more, and no miss on
  that edge in the last minute. Every flight is logged to its end:
  `BOT_RUNJUMP event=edge` (what was solved), `start`, `launch` (speed
  reached against speed wanted), `land` (distance from the foothold, health
  lost), `fail` (why a jump was not attempted or missed).

On Canyon Oasis this finds the way into the concussion rifle alcove that
players use: from the lower centre platform, Force Speed, a strafing sprint
of 0.3 to 1 unit and a nearly full Force Jump, 2.1 to 2.7 units across and
one unit up. It needs Force Jump rank three or four; lower ranks find no
way in.

**Margins.** Two of these jumps go from the temple doorways on Canyon
Oasis up onto the low shelf (one unit up, half a unit of headroom) in
front of the north alcove. Across the recorded matches the south one fell
5 times in 65 and the north one 15 times in 111, each fall a two-unit drop
into the canyon for about 33 health. The south jump's falls launched 7 to
11 percent slow (after two frames of flight, as logged), where the sweep
had still landed at 90 percent; it lands 0.13 past the shelf's lip, and a
heading two degrees off already meets the corner of the shelf's opening.
With `jump_margin` (default 1) a jump is kept only if a flight at 85
percent of the launch speed, and for a Force Jump one at 93 percent with
a tenth less lift (a hold the engine timed a few frames short), still lands.
On Canyon Oasis that drops three of the nine dry jumps (the south shelf
jump and two level ones that land just past a lip), finds one other, and
keeps the north one. Most of the north jump's falls were not slow flights
of a good plan: 9 of the 15 left at under 70 percent of the planned speed.
In the one traced, the jumper was gripped during the run-up; the held
Force Jump went off at its release with no speed, and the flight then
pushed on toward the far side and off the edge. A launch below 70 percent of the planned speed now
thrusts back instead and comes down where it took off; the leg rests for
15 seconds (`event=fail why=slow-launch`).

**Running off.** The same solver handles a ledge above water: walk or
sprint off the lip and fall in, which costs no health because the engine
quarters the vertical speed at the surface. The nearest water below is
tried first, at a walk, a run and a strafing run, once without Force Speed
and once with it, and the plan used is the one solved for the speed the bot
has at that moment. On Canyon Oasis this is the way out of the alcove: off
the south end of the ledge into the canal below. The bots still go down the
shaft when they want the rail detonator that lies in it.

**Out of the water.** The stock Force Jump also fires from the water
surface, and the bots never used it: their only way out was the surface
hop, 0.7 up and 0.6 across. The solver now looks for banks above an open
surface. The swimmer floats at the start of a short swim toward the bank,
holds the jump key for the length of the swim and lets it up a little short
of the wall, so the body is above the lip when it gets there and its
swimming speed carries it over. On Canyon Oasis this finds four exits, from
the oasis pool up to the walkways 1.17 above the water. They need nearly a
full rank-four jump, so the hold is timed to 1.33 seconds.

## Dodging

The bot is told about every shot fired at it, and until now only used that
to turn on the shooter. With `dodge_jump` (default 1), an explosive shot
that will burst within 0.45 units of the bot in 0.3 to 1.6 seconds sets a
short Force Jump: 0.2 seconds of hold, which lifts the body 0.7 units for a
little over a second and lands slower than the speed that hurts. The jump
keeps the ground speed the bot had and leaves its aim free, so it goes on
firing in the air. Each one logs a `BOT_DODGE` line, and `BOT_MOVE` counts
dodges and seconds of firing while airborne.

## Heavy guns

The concussion rifle has two modes in the stock COG. The shell (primary)
flies at 7 units a second and bursts for 80 within 0.8 units, the shooter
included, for 8 power cells. The beam (alternate) is an instant thin ray that
does 80 to the first thing it meets within 5 units, with no splash and no
harm to the shooter, for 4 cells. Either mode needs 8 cells in hand to fire.
The old rule used the beam first anywhere it reached. With `conc_alt_range`
(default 1.4) the bot fires the shell beyond 1.4 units when the shell is
safe, and the beam inside that or when the shell would catch the bot or an
ally; 99 restores the old rule.

A heavy gun (concussion rifle or rail detonator) had to show a safe shot on
every frame to stay selected. No other gun had to. A target stepping behind
a lip, or the muzzle path clipping a wall for a moment, put the heavy away,
and picking it back up costs the switch time twice. A combat jump put it
away too, because heavies may not fire in the air. With `heavy_hold`
(default 1) the heavy stays in hand while the beam reaches, while the target
is out of sight, and while the shot is only blocked, since a blocked path
blocks every gun alike. It is still put away for real reasons: out of ammo,
the target inside its own blast, splash on an ally. A combat jump holds fire
instead of switching. In a dodge hop the bot fires a heavy if the kick (80
force units back along the body) still lands on floor or against a wall.
`BOT_SWITCH` logs every switch away from a heavy with a visible target and
the reason; `BOT_MOVE` counts shells and beams with mean range, seconds with
a heavy in a fight, and those switches.

## Sabers

In the stock saber COG (`weap_saber.cog`) the secondary is a heavy swing:
160 damage, against 40 to 60 for the primary's attacks, and the longest
blade ray, 0.3 against 0.15 to 0.25. The primary depends on how the player
is moving when it fires: a run of three quick slashes walking forward (40,
40 and 60), otherwise a single 50. The heavy swing's blade does damage
0.33 to 0.67 and 0.8 to 1.13 seconds into its animation (a quick slash's
0.17 to 0.4), and the blade cannot swing again for 2 seconds (0.25 to 1
for the primary). Shields (`item_shields.cog`) stop only half of a saber
hit, so one heavy hit kills a player with no shields and leaves one with
full health and 100 shields at 2 health (with 200 shields, at 20).
Pressing either trigger drops the stock autoblock until half a second after
release.

The old rule swung the primary from 0.6 units, or for an elite bot in a
gun match only at contact, with the heavy swing kept for an immobilized
target. With `saber_heavy` (default 1) a bot swings only from contact
(the two bodies plus 0.1), and swings heavy wherever the target will still
be in reach 0.35 seconds on, as the blade comes down; the quick primary
against a target pulling away, beside a protected player (the shorter
blade), and underwater, where the COG has one attack for both triggers.
Out of contact the guard stays up. `BOT_MOVE` counts `saber_heavy` and
`saber_light` presses.

## Force Pull

The stock Pull takes whatever player, actor or item lies nearest the view
centre, in sight, within 0.5 + rank/2 units. A player loses the gun in hand
and drops to fists, unless Absorb is up; fists and sabers cannot be pulled.
Pulls on players were reviewed with a check 0.8 s after each release: in
three matches 128 of 199 checked pulls disarmed (64%), much the same for
both groups. Absorb, which the light-side bots keep up in fights, accounts for
most of the rest; the existing per-opponent retry delay already backs off
after a pull that changes nothing. Pulls cancelled before release (the
stock marker named something else, or sight was lost) were 102. Each cancel
cycles the selected power, which is the scrolling power names seen in the
recording; that is only on the bot's own screen.

Items answer Pull too: the item flies at the puller with gravity off.
Keys, wrenches and CTF flags refuse it. With `item_pull` (default 2; 0 =
never) a bot on dry ground with no enemy in sight pulls an item worth at
least that much (the same value the planner gives it) from 0.75 units out
to just inside its reach. It turns until the item is centred, holds Pull
until the stock marker names that item, and releases. A wrong marker cancels
through deselection; an item that was not caught rests ten seconds before
another try. `BOT_PULL` lines record each item pull and each player pull's
outcome.

Nothing in the stock power needs the puller to stand still. Its pulse picks
the thing nearest the view centre in sight and in reach, and the release
throws that thing at wherever the puller stands at that moment, at 3 units a
second slowing under air drag, gravity off for 1.5 s. The legacy bot stopped
for the whole pull and stood to catch the item, one to three seconds in the
open each time. With `pull_on_move` (default 1) it runs at the item through
the cast where that way is safe, so the item stays centred and in reach and
comes in sooner, and otherwise keeps to its route; a pull under way may close
right in or bounce over uneven ground. After the release it runs onto the
item as it flies in, and where that way is not safe it waits, since the item
is coming to the spot of the release. A fight that starts once the marker
names the item no longer cancels the pull: the bot lets go at once, and its
legs chase the item while its aim and its Force go to the fight. The legacy
bot ended the pull for any enemy in view.

## Dropped packs

A player who dies leaves a backpack (`+backpack`) for 30 seconds holding
every gun and all the ammunition they carried; health and shields stay
behind. A pack has no route node. The planner finds where a bot can touch
it, then a graph node from which a straight walk of at most 2 units reaches
that spot. With trace logging on every bot (one `BOT_PACK` line each time a
bot's verdict on a pack changes), two five-minute four-bot matches showed
three things in the way:

- **No way in.** The planner tried the four nodes nearest the bot, plus one
  more each scan in rotation. Beside a ledge the nodes nearest the bot are
  the ones below it, which never walk up to the pack; the right ones came
  round once in up to 50 scans. 'No way in' was about half of all verdicts.
  One pack with a repeater, a rail detonator and 500 energy sat on a ledge
  for twenty seconds while four bots came within 2.5 to 7 units of it.
  `pack_hunt` (default 1) tries the nodes nearest the pack first, eight a
  scan, and keeps the touching spot and up to three ways in while the pack
  lies still; a pack that moves starts over.
- **Packs in water.** On a pool floor, the height at which the bot checks a
  swimmer can touch the pack left the swimmer's body touching the floor;
  floating just under the surface, the check started in the air above the
  water. Both were taken for out of reach, among them a pack with a
  concussion rifle, a rail detonator and 21 rail charges 0.4 units from a
  bot. `pack_hunt` lifts the check clear of the floor, or makes it level with
  or under a floating pack. A pack whose centre has sunk onto the floor
  itself stays out of reach: the stock pickup needs a line of sight to the
  pack's centre, and that line ends in the floor.
- **Worth.** A pack was worth only what the bot lacked. To a bot holding a
  concussion rifle with plenty of shots, a pack with another one was worth
  its ammunition: 1, or 5 when nearly out. `pack_deny` (default 3) makes a
  pack with a concussion rifle, rail detonator or repeater and a shot for it
  worth at least 3: the ammunition, and nobody else arms himself from it.

## Mines and thermals

The bots used neither. The combat code left thermal detonators and
sequencer charges out of weapon choice, and the planner never collected
them. Canyon Oasis has a thermal pickup and three charges.

`hazard_avoid` (default 1): a weapon thing at rest with an explosion of its
own is a hazard. That is a laid charge (a proximity mine two seconds after
it lands, for sixty seconds, set off by anything inside 0.3 units), a
bouncing thermal on its fuse, or a stuck rail charge. Nodes within reach of
one are avoided, legs that pass one cost as much as an avoided node, and a
bot standing too close steps away. Shots in flight stay with the dodge.

`mines` (default 1): charges are worth collecting up to three. When the bot
takes a guarded item that respawns (a heavy gun, armour, health, a power
boost) and has a charge, it selects the charge, raises it and drops a
proximity mine (the secondary) on the spot, for the next player who comes
for the respawn. Not with an enemy in view, not near another hazard, not
with more than three of its own alive, not in team play or while any
player is peaceful.

`thermals` (default 1): thermals are worth collecting up to four. The
stock throw scales the grenade's launch velocity by the seconds held, 0.7
to 2 for the primary, which bursts on whatever it touches: 0.7 units of
reach at the shortest hold, 3.2 at the longest, with up to a second and a
third of flight. That suits targets guns serve badly: out of sight below or
behind a lip, in the water, or standing still, 1.4 to 3.2 units away. The
bot flies the grenade the way the engine does (template velocity, air drag,
gravity, collision with level geometry) to find the pitch that lands by
the target's feet, chooses the shortest hold that reaches, keeps the arc
updated while holding, and releases once turned onto it. It never throws
at its own feet. `BOT_MINE`, `BOT_THERMAL` and `BOT_HAZARD` lines log each
attempt.

## Use

Every press of the use key plays the stock "use" animation, and the host
sends it to every player, whether or not anything is there to use. The bot
pressed use every 0.8 seconds whenever its way was blocked, in case it was
a door. In a match that came to 30 to 63 presses a minute. With `blind_use`
at its default of 0, it presses only when the engine's own activate test
would find something: a COG-linked surface or a captured thing that is not
an item, within reach along the view. A stall that triggers recovery still
presses once. Measured in the same match: 2 to 3 presses a minute, against
30 and 63 for two bots with `blind_use=1`.

## Level traps

Four of the six stock multiplayer levels have traps a player springs from a
switch. The bots knew none of them: they walked into them, and pressed
their switches by accident whenever one stood in front of them as they
pushed past.

| Level | COG | Switch | Effect |
|---|---|---|---|
| Canyon Oasis | `00_lightning.cog` | one, beside the grated ramp | Arms the ramp: the next player onto it sets three emitters in the far wall firing Force Lightning (13 a bolt, 1.5 units) every half second until someone steps off. Pressed again, it disarms. |
| Nar Shaddaa Loading Terminal | `m2_dettrap.cog` | four | Each throws eight thermal detonators (3 s fuse, 75 within 0.45) from four vents, then resets after about four seconds. |
| Nar Shaddaa Loading Terminal | `m2_turrettrap.cog` | one | Four ceiling turrets fire five auto-aimed volleys over about nine seconds. |
| Bespin Mining Station | `m4_reactorthrust.cog` | one, beside the reactor pad | Thrusts anyone in the reactor shaft straight up for one cycle of the hatches above. |
| Blades of Death | `m5_fandamage.cog` | two | The fan takes 125 every half second from anyone in its pit; a switch stops it for 11.5 seconds. |

Nar Shaddaa also has a force field (`m2_ffieldswitch.cog`) across the
passage by the turret room, a gate rather than a trap; see Force fields
below. The Valley of the Jedi Tower and Battleground Jedi have no traps.

A trap is recognised by the symbol names of its COG, whose values the
level gives every machine: the switch surfaces, the sectors it covers and
the spots it fires from. On a client the COG's messages run on the server,
so the COG's own variables never change there; the switch frames the
server sets do reach every machine, and they say whether a trap is ready
(frame 0) or live (frame 1; the fan runs at frame 0). Each bot logs
`BOT_TRAP event=bind` for every trap it found, with the spot it would press
the switch from, and `event=state` whenever a switch changes.

- **Zones.** A trap's zone is its sectors (the ramp, the reactor shaft, the
  fan pit) and what its emitters reach: inside a turret's or lightning
  emitter's view cone and range with a clear line, or within 1.2 units of
  where a detonator from each vent first meets the level (its throw is
  flown with the template's speed, gravity and air drag).
- **`trap_avoid`** (default 1). The graph nodes in a live trap's zone are
  avoided, so routes and goals leave it alone while it is armed or
  firing; the fan pit counts as live unless the bot saw the fan stop with
  time to spare. A bot caught in one takes the cheapest way to the nearest
  node outside every live zone (`event=escape`). A trap's switch is never
  pressed just to get past, by the blocked-way press or by recovery.
- **`trap_use`** (default 6) and **`trap_chance`** (default 0.6). Every
  half second a bot not in the middle of a jump, a water exit or a
  recovery looks for a ready trap with an opponent in its zone (for the
  lightning, on the ramp or within 2.5 of it), no teammate there, the bot
  itself clear of it, and the spot in front of the switch no more than
  `trap_use` units of path away (a Force Jump leg counts its flight). Such
  an opening is taken with `trap_chance`; one passed up is not looked at
  again for four seconds. The lightning is an ambush as well: a bot passing
  within 1.5 of its switch arms it with half that chance, and then leaves
  it for 20 seconds. The bot routes to the spot (a fight keeps its aim on
  the way), looks at the switch from the eye and presses use once, from
  where the stock activation ray reaches. The switch frame changing is the
  proof (`event=sprung`); the same trap is then left alone for 25 seconds.
  Another player getting there first (`why=taken`), a press with no answer,
  the way there growing half as long again (`why=too-far`: a struck jump
  leg, no Force left for one, a fight that carried the bot off) or the
  time running out ends the attempt (`event=abandon`, with how far from
  the spot it was).
- **`trap_disarm`** (default 1). The lightning stays armed until someone
  presses the switch again. Once the ramp has stood armed ten seconds with
  no opponent on it or within 2.5 of it, a bot takes it back down: from up
  to 1.5 units of path away, plus one more for every ten seconds it has
  stood armed, at most twice `trap_use` (6 after 45 seconds, 12 after about
  two minutes on the defaults; the switch platform is a Force Jump up, so
  most of the level is 6 to 16 units of path from it). A teammate by the
  ramp has it taken down at once (within `trap_use`). No chance is
  rolled; how long it has stood decides. The switch frame going back to 0
  is the proof (`event=disarmed`), and the switch is then left alone for 25
  seconds. The bots read the frame every 0.2 seconds, so whoever disarms
  it, the ramp is part of their routes again within half a second.

The fan is only kept clear of; stopping it opens nothing worth a run.
`BOT_MOVE` counts `traps` sprung, `trap_disarms`, `trap_escapes`,
`trap_open` (looks that found an opening at a switch), `trap_busy` (looks
skipped) and `trap_nearest` (the shortest walk to such a switch);
`BOT_TRAP event=open` logs one such opening per trap every ten seconds,
with `purpose=spring` or `purpose=disarm`, and `event=hurt` damage taken
inside a live zone.

### Force fields

Nar Shaddaa's field (`m2_ffieldswitch.cog`) closes a passage 4.8 units wide
by the turret room. It is on from the start: the COG clears the movement
flag of both faces' adjoins, so nothing passes, and touching it takes 5 to
10 every quarter second. Each of its two switches turns it off, or on
again: one up on the main side (surface 890, reached from the walkway a
floor up) and one at the floor of the strip behind it (surface 939, beside
the turret switch). A player spawn (thing 100) is in that strip. A bot that
spawned there could reach only the strip's 23 graph nodes, and the turret
switch was in reach of no one else. The field's state reaches every machine
with the surface update, which carries the adjoin's flags, so a bot reads
whether it is open directly (`BOT_TRAP event=state kind=field`, `cel=1`
open).

- **The graph.** When the traps are bound the field is learnt once, the
  same whichever state it was in when the graph was built. No ordinary leg
  goes through its face or passes the face's edge closer than a body's
  breadth, and no leg ends at a node standing against it (a body there
  touches the field while it is on). Up to sixteen gate legs cross it,
  spread along it, shortest first: a gate leg joins a node on either side
  straight through the face where the body clears the face's edges, with
  floor just short of the face on both sides, and each half an ordinary
  walk that stops short of it. Nar Shaddaa gets 20 gate legs, 10 each way
  (`BOT_FIELD event=bind` and `event=gate`).
- **`field_switch`** (default 1). An open field's gate leg is an ordinary
  walk. While the field is on, a gate leg costs the walk from it to the
  nearest switch on its side, the walk back, and a second to press it: 2
  to 8 units from the strip, 28 to 31 from the main side, where the switch
  is a floor up and the sure way up goes round by the far end of the level
  (a Force Jump leg up beside it that the bots used to refuse on the spot
  is no longer built; see `fjump_margin`). A switch more than 25 units of
  walk from the gate is not gone for at all: the field is a wall from that
  side. The price is brought up to date every five seconds, so a struck
  jump leg or the Force to make one counts. When a bot's route meets a gate that is
  on, it goes to that side's switch first (`purpose=open`) and presses it
  like a trap's switch. Once the field is seen open (`event=opened`) it
  goes on to where it was headed. It never walks into the field while it
  is on: on a gate leg it waits short of the face until the run starts
  (`BOT_MOVE gate_wait`, in seconds). If the way to the switch grows half
  as long again (and by 3 or more) while the bot is on it, it gives up
  (`why=too-far`) rather than trek round the level. If that side's switch
  cannot be worked (no route to it, none within 25 units, a press with no
  answer, a run given up), the field is a wall from that side for 15
  seconds, then twice as long each time in a row, up to two minutes
  (`BOT_FIELD event=no-switch`); opening it starts the count again. Before,
  every failure rested it 15 seconds, and a bot on the main side went back
  round the level for the switch again and again. A field someone else opens first is good news
  (`why=taken`, with no rest). Field switches count as trap switches for
  `trap_avoid`, so they are never pressed by accident. With `field_switch`
  at 0, a field that is on is a wall.

On the level's own geometry (the offline map probe), with the field on, a
bot that spawned in the strip now reaches 567 of the 640 graph nodes
through the strip's switch, against 23 before; the same 20 gate legs are
built whether the field was on or off when the graph was built.
`BOT_MOVE` counts `fields_opened`.

Limits. A bot does not close the field behind it or use it to cut off an
opponent, and a fight next to a field that is on can still brush it.
Bespin's reactor pad is out of the way and saw no use in the trials.

## Lifts

The graph gives every two-frame path thing named as a lift, elevator or
platform a node on its deck at each stop. The bot waits on the landing
until the deck is at its stop, rides it, and walks off at the other. The
stock elevators move only when told to:

| COG | Levels | What sends the lift |
|---|---|---|
| `00_elev_switch.cog` | Nar Shaddaa (2 lifts) | Crossing one of its threshold adjoins onto it, or its button, sends it up; two seconds after it gets there it comes back down. |
| `00_elev_switch2.cog` | Bespin (5 lifts) | Crossing a threshold adjoin onto it (a quarter second later, if it is standing) or pressing any of its call buttons sends it to its other stop. |

The bots never pressed anything for a lift: while waiting they pressed use
every 1.2 seconds wherever they were looking. A bot that walked onto a deck
crossed its threshold and was carried; one that boarded a deck still
moving, or stood on it when it came back, never crossed one, and the lift
stayed where it was. In the Bespin recording four of Red's five
confinements (`BOT_CONFINED`) were at the foot of one lift, on or beside a
deck that stood still; on Nar Shaddaa she waited at a lift whose button she
could have reached from its deck.

With `lift_call` (default 1) the lift's COG is read when the traps are
bound: the thing it names `elevator`, its `button` and `call0` to `call3`
surfaces, and its `lower_adjoin0` to `lower_adjoin2` thresholds
(`BOT_LIFT event=bind`, with how many of each). A lift that has stood still
for 0.8 seconds away from the stop the bot wants is stuck:

- A rider presses a button at eye height that faces it and that the stock
  use ray reaches from where it stands, or from a step of at most 0.12 (a
  rider must not walk off the deck): it turns to it and presses use once
  (`event=press`).
- With no such button, or one that has not moved the lift in four seconds,
  a rider steps off across the nearest threshold at its level onto the
  landing beyond it (`event=step-off`). Once over it the bot plans again
  from the landing (`event=stepped-off`), and the way back on crosses the
  threshold, which is what sets the stock lifts going. It gives up the
  step after three seconds (`event=step-timeout`).
- On a landing, the bot walks up to the lift's button on that level, within
  0.9 of a press, and presses it.
- A deck that has come to its stop is boarded only once it has stood still
  for 0.3 seconds. Both COGs ignore a crossing while the lift moves, and a
  bot that walked on while the deck settled into its stop rode nowhere.

Bespin's railgun and concussion rifle lie in small alcoves halfway up two
lift shafts, each with a call button, and a player spawn is in each
alcove. The graph had no leg out of either: a deck node is joined only to
level ground at its own stop. A bot that spawned in one stayed there; in
one recording Red spent the last three minutes of the match in the railgun
alcove. With `lift_hop` (default 1) a node beside a shaft, between the
lift's two stops and with a clear line into the shaft, gets a leg onto the
deck at each stop. The bot waits at the alcove's lip facing the shaft and
steps out when the deck stands below within a drop it can take (up to 1.6
units, over 1 only with 50 health or more; with the player's air drag of
0.5 the stock fall rule makes a 1.6 fall cost about 14), or when the
moving deck will be 0.02 to 0.35 under the lip by the
time the bot is over it, judged from the rate the deck has been climbing
or falling. Where the deck stands still out of reach it presses the
alcove's call button. A step under way is called off if the deck rises
past the lip first, so the bot does not walk into the empty shaft
(`BOT_LIFT event=hop`; `BOT_MOVE lift_hops`). The way into the alcoves
from the deck is not built yet.

A lift that is moving is waited for, and with `lift_call` on there are no
blind presses. The 16-second limit on a wait still stands: after it the
node the bot was headed for is avoided for 20 seconds. `BOT_MOVE` counts `lift_calls`
(presses) and `lift_steps`. With `lift_call` at 0, the blind presses
return and nothing else is done.

## Dead ends

Under Bespin's main floor a round pit drops 1.7 units to a pair of floor
doors (`00_door.cog`, things 1 and 2) that open on use and let a player
fall into the room below. The graph has one node down there and no leg out
of it. In one recording Red fell in during a recovery at the rim and stood
on the doors for the last four and a half minutes of the match, jumping and
pressing use at the wall in front of her: no goal could be reached from
there, and the use ray only ever looked ahead.

With `dead_end` (default 1), a bot that has had no goal for two seconds
while the node nearest it reaches no more than a twentieth of the graph (at
least eight nodes) is in a dead end (`BOT_DEADEND event=found`, with the
node and how much it reaches). Standing on a door (a path thing captured by
its COG, not a lift) it first steps over the seam where the door's pieces
part, found from the COG that moves them together (`door0` to `door3`),
to within 0.05, hopping toward it if it has not got there in two seconds.
It never presses from anywhere else: pressed by a bot standing on one
piece near the wall that piece slides into, the door pinned the bot to the
wall and never opened, and in two recordings a bot stood like that for two
minutes. Over the seam it looks straight down, which the stock look code
stops at 80 degrees, and presses use once the use ray meets either piece
(`event=door`); the doors part and it drops through, about 1.7 units to
the room below (about 17 health by the stock fall rule). A recovery jump or a fight with someone above pauses this
without starting the two seconds again. Anywhere else recovery carries on
as before. `BOT_MOVE` counts `dead_end_uses`.

## Lips

On Canyon Oasis's high walkway Red stood still for fifteen seconds with her
feet on the lip of the platform by the lightning switch and her centre over
the grated ramp 0.85 below. With no floor under the centre there was no hop
to fall back on, every heading near the one she wanted ran off the lip, and
the movement code gave up; her nearest graph node was the one down on the
ramp, because only nodes in the centre's sector counted. With `lip_escape`
(default 1) a bot that is standing with no floor under its centre takes the
safe heading nearest the one it wants, even back from the edge, and routes
start from the floor under its feet as well as from the centre's sector.
On the same spot, replayed against the level's geometry, every wanted
direction now steps back onto the platform, and the nearest node is the
platform's own, 0.15 away. `BOT_MOVE` counts `lip_steps`.

## Narrow openings

The bots follow a route by walking straight at its next node, and a move
the ground check finds blocked is replaced by one turned up to 50 degrees
off it. Bespin's upper rooms are left through door alcoves 0.2 units wide
(a body is 0.13 across). In one recording Red stood at the mouth of one for
three minutes: 0.05 off its axis, the straight way to the node inside
clipped the jamb, every turned move led away from it, and the planner kept
sending her back. On the level's own geometry the straight move into the
alcove is refused from where she stood and allowed from 0.02 further over.
With `leg_axis` (default 1), a bot off a walking leg's line by more than
0.015, whose straight way to the leg's node is blocked, first steps back
onto that line a little ahead, which the graph checked when it built the
leg, and goes on from there. The same goes for boarding a lift, walking
off one and stepping off across its threshold: Bespin's lift decks are
reached through openings 0.2 wide, and a bot that stopped 0.09 off the
middle of one on the deck could not get off it for 25 seconds. `BOT_MOVE`
counts `leg_axis` in seconds.

The engine stops a body moving toward a wall wherever the point it would
touch the wall's plane lies within the body's radius (0.065) of a solid
face, corners included, and a body stopped at a corner slides no further.
The steering probe is slimmer than the body (0.052), so beside a narrow
opening it passes moves the body cannot make. In the last Bespin recording
Boba Fett rode a lift to the top and stood 25 seconds in the corner of the
shaft beside the opening, 0.11 off its line, pressed against both walls:
the straight way out and the slant back onto the line both met the jamb's
corner. With `leg_square` (default 1), a bot off the line whose body would
meet something on the straight way or the slant steps square onto the
line, along the wall, and goes straight once the whole body clears the
jamb; on a walking leg it keeps squaring for up to a second once it has
started. Replayed on Bespin's own geometry with the engine's collision
code, a rider stepping off from 21 spots on each of the eight lift stops
got off from every one; with `leg_square` at 0, from 152 of the 168.
`BOT_MOVE` counts `leg_square` in seconds.

## Confinement

`Bot_Recovery` already handles a bot that cannot move. The new check handles
one that moves and still goes nowhere: a bank exit that keeps failing, a jump
that keeps missing, two goals that undo each other. Positions are sampled
over `confine_seconds`. If every sample lies within `confine_radius` of their
centre, and the bot is not waiting for a lift or objective, fighting on dry
ground, or idle for want of a destination, it is confined.

Each escape drops the current goal and avoids the places being tried for
`tabu_seconds`. A repeat within 45 seconds doubles that time, up to two
minutes, and widens it to every place within 0.75 and then 1.5 units, so the
next plan has to lead somewhere else. Avoided places stay usable as
waypoints at a high cost; they are only excluded as destinations. In water
the bot also takes the existing air-and-bank escape and records the dive as
failed. Each escape logs one `BOT_CONFINED` line with position, strike
count and avoid time.

## What the recordings showed

Two four-minute recordings of one bot's own rendered client on Canyon Oasis,
reviewed frame by frame against its logs, were set beside four public Canyon
Oasis matches between people (two Full Force duels, a 2v2 and a permanent
concussion rifle duel). Each fix below is a tactic whose legacy value keeps
the old behaviour.

- `quick_respawn` (default 1). The stock controls ignore the respawn key
  until three seconds after death, then respawn on a press followed by a
  release. The bots pressed for 0.18 s in every 1.4 s from 1.5 s on, so the
  first press that counted came 4.3 to 4.5 s after death; the players in the
  footage were back in about 3.1 s. The bot now presses on alternate frames
  as soon as the stock timer allows. In a match: 3.0 s dead per death
  against 4.5 s for the legacy group.
- `air_health` (default 0; legacy 30). A swimmer under 30 health turned for
  air at once, breath or no breath. The surface heals nothing, and the turn
  set the goal aside and replanned, which on the shaft-top pool put a bot at
  23 health in and out of the same water about ten times in twenty seconds.
  Breath alone decides now. A hurt bot gets to health through the plan, and
  swims still cost more under 40 health, as before.
- `swim_cost` (default 3; legacy 1). A leg swum under water costs three
  times its length in the planner: swimming runs at 0.27 to 0.6 units a
  second against 1.3 to 1.6 for running. The step in from a bank keeps its
  `water_entry_cost`. In 25 minutes of one of the people's matches, sampled
  every 1.5 seconds, no stay in water was longer than about four and a half
  seconds; the recorded bot's single swims ran 7.6 to 11.6.
- `water_fight` (default 1). The climb out of water took the view and never
  fired. In one recording two bots sat in the same small pool for eight
  seconds, on the same exit, each in the other's reach, neither shooting,
  until both were caught as confined. People fire while swimming up a shaft
  and come out of a pool with the gun up: one fired the concussion rifle 0.7
  seconds after dropping out of the bottom of the shaft. Now:
  - The exit no longer demands facing the bank. Forward and strafe together
    push at full thrust along the line to the bank with the body turned up
    to 43 degrees off it, facing either way along it. The climb looks as near
    the shot as that allows and fires when on it. A concussion rifle or rail
    detonator, which kicks its shooter 80 force units back, waits out the
    run-up, the jump and the last settle on the launch spot.
  - A launch spot belongs to the swimmer nearest it. The other gives way,
    sets that way out aside for four seconds and plans another
    (`BOT_WATER event=yield`).
  - On a level swim leg in a fight, the stroke is solved for the view:
    forward along the view, strafe at 0.7 of it, rise and sink at half, so
    the bot keeps looking at its target while it swims.
  - A Grip is answered even in the middle of a climb; other powers wait for
    dry ground.
- `fjump_standstill` (default 1). The bot stops before a Force Jump and the
  stock release adds only upward speed, so the leg is flown on air thrust
  from a standstill. Integrated the way the engine applies thrust in the air,
  that carries the body only 0.1 to 0.2 units across, even at full charge. The arcs that admitted Force Jump legs assumed running speed
  through the air, so they took legs the bot then fell short of, into the
  wall under the ledge; in one recording a bot spent most of 40 seconds in a
  corridor facing its rock wall between Force Jumps. Legs are now checked by
  flying that standstill flight through the level, level and slightly lower
  landings included, which the old check skipped. Ledges that need speed are
  for the running jumps. The route moves on to the landing once the bot is
  within 0.11 of the launch node, and a few hundredths off that spot can be
  enough to fall short, so the bot first steps back onto the spot, still
  facing the landing, and jumps from there. A leg that cannot be made even
  from the spot, or that the bot cannot get back onto in three seconds, is
  struck off and the bot plans again (`BOT_JUMP event=refuse`). Before this,
  the second recording's corridor had the bot walking into the rock wall
  under such a leg for 20 seconds.
- `fjump_margin` (default 1). That flight depends on the frame rate: air
  thrust is applied once a frame, so at a slow rate the body gets less of
  it and flies a shorter jump. The graph was built on whatever frame time
  the bot had while it loaded, and the bots then play at 30.
  On Nar Shaddaa a leg up toward the main-side field switch (graph nodes
  144 to 83) flies at 60 and 40 frames a second and falls short at 30, so
  the planner kept choosing it and the bot kept refusing it on the launch
  spot. A leg is now built in only if it still flies at 25 frames a second,
  and the check on the launch spot flies at the bot's frame time averaged
  over its last ten frames or so, not one frame's. On the level's own geometry
  the graph keeps 83 Force Jump legs whether it is built at 60 or 30, and
  that one is gone.
- `jump_memory` (default 30; legacy 0). A Jump or Force Jump leg that comes
  down somewhere other than its target is struck off for twice this many
  seconds, and every spot on the ledge it aimed at is set aside for this
  long, so the next plan finds another way up or another goal
  (`BOT_JUMP event=miss`). A landing on the target's own level, a short walk
  from the mark, counts as made.
- `speed_upkeep` (default 1). Force Speed costs 20 mana and lasts 5 + 2.5 x
  rank seconds. The players kept it up nearly all the time, recasting every
  few seconds. The bot cast it only for a long straight walk and kept 200 mana
  back for Absorb. It now keeps Speed up on any walking leg and in fights,
  past the Absorb reserve, but never below the mana for a Jump and a Pull,
  and not during jumps, drops, lifts or swims. Within 1.5 units of an
  opponent, where Grip takes hold, it still leaves the mana to raise Absorb.
  In a match the group on the defaults had Speed up about 215 of every 300
  seconds alive, against about 165 for the legacy group. `BOT_MOVE` reports
  the seconds Speed was down by reason (`speed_no`: another power in
  progress, navigation or water state, movement input, a leg with its own
  pace, mana, the ground ahead). In an eight-bot match, before the
  close-range rule, Speed was up 66 to 80 percent of the time alive; water
  and navigation states accounted for most of the rest, mana and blocked
  ground for a few seconds each.
- `resupply` (default 1). A pulled gun is a new pickup (`+fpconcrifle` and
  the like): takeable after 0.2 s, gone after 4 s, never respawned. The bots
  disarm a lot (73 disarms by four bots in one six-minute match) and left
  the guns lying. Now a pulled gun at rest, or sliding to a stop, is worth
  what that gun is worth (a missing concussion rifle 18). A bot with no gun
  holding more than a few shots adds 4 to every real gun, so they keep their
  order, treats ammunition for a gun it holds as worth at least 12, and does
  not go hunting. A pickup just chosen is favoured by half again for 2.5
  seconds (otherwise 15 percent), so near-equal choices do not flip back and
  forth at a waterline, where path costs jump. An opponent left with fists is
  preferred as a target and in the hunt. `BOT_GEAR event=loose` logs each
  pulled gun chased; in one eight-bot match there were eleven.

Watching the latest recording, three more things stood out: the bots still
walked much of the time, stood still to pull items, and seemed to pass up
packs dropped by fallen opponents. The logs bore all three out; the answers
are `always_run` (see [Movement](#movement)), `pull_on_move` (see
[Force Pull](#force-pull)) and `pack_hunt` with `pack_deny` (see
[Dropped packs](#dropped-packs)).

Two earlier tactics came from the first recording:

- `absorb_reserve` (default 1). The bot took Grip damage again and again
  without answering it. Absorb costs 200 and at rank four turns Grip,
  Lightning and Destruction damage into mana. While it is down, optional
  casts leave enough mana to raise it, and a Grip is answered with
  Protection or Absorb before bacta, whose cooldown would delay them. While
  the Grip lasts, nothing optional is cast, only Healing below 60 health, so
  the mana is there when Absorb runs out and must be raised again: in one
  recording the bot spent it on Pulls during a Grip and died when Absorb
  expired.
- `turn_rate` (default 1800). The bot turned through the keyboard axis, which
  the stock code caps at 200 degrees a second for yaw and 90 for pitch. It
  now turns the way a mouse does, through the stock look code, up to this
  many degrees a second straight onto the point; 0 restores the keyboard.

The fists-as-peace setting is taken out for now: bots read `fists_peace` from
their behaviour file but ignore it, so a player with fists out is an
opponent like any other.

## Tactics

`python -m bots.tactics list` prints the table: 64 named values with a
default, a legacy value, and a range. The legacy column reproduces the
behaviour before this change, so one build can play both.

Values come from three places:

1. The compiled defaults.
2. A baseline file named by `JK_BOT_TACTICS_FILE` (`python -m bots.run
   --tactics-file PATH`). It is a complete revision: names it leaves out
   return to the default. The bot re-reads it when its content changes and
   rejects the whole file on any unknown name or out-of-range value.
3. A companion `tactics` command, which merges a few values into the
   current table, optionally after resetting it to the defaults.

The engine refuses a second live adjustment for 8 seconds after the last
one and reports it as `rate_limited`. Tactics outlive a death and a
controller lease, and a coach may set them while the bot is dead. A new
table does not drop the bot's current goal.

## The coach seat

With a companion lease (see the bots README), a controller can read the
table and set tactics:

```bash
python3 -m bots.companion_cli --credentials RUN/companion/BOT.json tactics-info
python3 -m bots.companion_cli --credentials RUN/companion/BOT.json tactics --preset hunter
python3 -m bots.companion_cli --credentials RUN/companion/BOT.json tactics --set gun_far=4 --set run=0
```

Over HTTP it is `GET` and `POST /v1/bots/BOT/tactics` with `preset`, `values`
and `reset`. The JKWeb client passes the same command to the browser bot.

Presets (`default`, `legacy`, `arsenal`, `hunter`, `standoff`, `dry`) are
starting points, not tuned results.

`python -m bots.coach` is a small automatic coach. It holds one preset for a
spell of at least 90 seconds, grades the spell by kills minus deaths per
minute once at least one of either has happened, and picks the next preset
with the UCB1 rule. Results persist in a memory file under a label, so later
sessions start from what earlier ones learned. It is the simplest thing that
adapts without thrashing, and a place for a smarter coach to start.

## Building and trying it

The overlay touches only `src/AI` and applies on top of either patched tree:

```bash
git apply native/bot-client.patch      # or web_bots/engine.patch on the JKWeb base
git apply native/bot-tactics.patch
```

Before a trial:

```bash
python3 native/tests/run_bot_driver_tests.py    --source SRC --build BUILD
python3 native/tests/run_bot_companion_tests.py --source SRC --build BUILD
python3 native/tests/run_stock_ground_tests.py  --source SRC --build BUILD
python3 -m unittest tests.test_bot_tactics
```

For a match, compare two groups in the same game: one on the defaults and
one with `--preset legacy`. Things to read from the logs: `BOT_MOVE` (every
ten seconds: time alive, wet, on foot, running, running refused by the
runway check, swimming pitched), `BOT_WATER` (each entry with its
destination, each exit with its length, each refused swim and each
air-return), `BOT_CONFINED` counts and whether strikes climb, and the score. If running causes
falls on a particular map, raise `run_brake` or set `strafe_run=0` before
turning `run` off.

When a build has been tried, fold the overlay into the two engine patches,
rebuild, and refresh the build receipts in the usual way.

## Evidence and limits

- 88 native fixture groups pass (79 existing, 9 new), also under
  AddressSanitizer and UndefinedBehaviorSanitizer. The 79 existing groups
  pass with the legacy values and again with the new defaults.
- The stock ground check runs `Engine/sithPhysics.c` and the unmodified
  `sithControl_PlayerMovement` at the multiplayer physics rate with control
  updates at 30 to 60 Hz. It confirms the speeds above, that exact thrust
  holds the path at every body angle tried, and that the checked runway
  exceeds the measured coasting distance by at least 0.3 units. It has no
  level geometry, collision or networking.
- Python: tactic registry against the engine table, hub route, command
  line, launcher plumbing and the coach, including a session against a real
  hub with a simulated engine.

- Live matches: a dedicated host on Canyon Oasis with four bot clients
  built from this overlay, two on the defaults and two on `legacy` in the
  same game, positions sampled five times a second.

  | match | length | speed, new / legacy | time wet | standing still | kills |
  | --- | --- | --- | --- | --- | --- |
  | first build, 1 | 300 s | 0.48 / 0.55 | 41% / 17% | 28% / 13% | 5 / 6 |
  | first build, 2 | 240 s | 0.51 / 0.56 | 41% / 18% | 31% / 12% | 5 / 7 |
  | this build, 1 | 300 s | 0.58 / 0.47 | 25% / 31% | 12% / 21% | 6 / 8 |
  | this build, 2 | 300 s | 0.68 / 0.50 | 12% / 23% | 10% / 14% | 10 / 11 |

  The first build lost. With the concussion rifle valued properly the bots
  went and got it, and then could not leave its ledge (see `crossing_seconds`
  above). In those two matches the old bots never picked it up; in later
  ones they did, and were caught the same way. The three swim tactics are
  the answer to that. The bot profiles were swapped between the two matches
  of each pair.

- Running jumps, same host and map, every bot with Force Speed and Force
  Jump at rank four. Each bot solved six or seven jump edges. In five
  matches (about 21 minutes; four jumping bots in three of them, two in the
  others) twelve jumps were launched and all twelve landed: the ten with a
  logged landing came down 0.04 to 0.27 units from the foothold with no
  health lost, eleven of the twelve went into the concussion rifle alcove
  and one up onto a walkway. Launch speed was within 9 percent of the speed
  solved for. Fourteen more times a jump was planned and not started:
  seven with a run-up the bot could not walk, five where it was not at the
  launch platform at all, one out of mana, one knocked off the platform
  while charging. Those cost three to sixteen seconds each; the two common
  causes are now caught at once and the edge set aside. In the two matches against `legacy` the groups with
  running jumps moved at 0.59 and 0.56 against 0.47 and 0.44, were wet 22%
  and 27% of the time against 37% and 35%, and scored 6 and 10 kills
  against 6 and 6.
- Four later matches (20 minutes, four bots) with run-offs added: thirteen
  more jumps, twelve landed. The miss was Force Speed running out during
  the charge: the bot launched at half speed, fell two units and lost 23
  health. A guard against that was added afterwards and has not been run
  live. Seven run-offs from the alcove ledge all landed in the canal with
  no health lost. Each bot solved 85 to 89 jump and run-off plans.
- Eight further matches (40 minutes): 48 jumps and run-offs launched, 46
  landed. One jump reached only two thirds of its sprint speed and fell
  short; one run-off was thrown aside in the air by a blast. Out of the
  water, two attempts with an earlier timing showed the Force Jump does
  fire from the surface, and both fell back. The present timing has not
  yet been tried in a match: the bots were rarely in that pool.
- A four-minute recording of one bot's own rendered client, third person,
  against two bots on the same build: 3 kills, 3 deaths, about a third of
  the time in water, six dodges, three seconds of firing in the air, no
  running jumps. Reviewing it frame by frame found the blind use presses
  and the surface-hop loop above. It also shows the Force power names
  filling the top of the bot's own screen. That comes from the bot cycling
  its selected power to stop Pull, which only the bot itself sees, and from
  36 Pull casts in 277 seconds alive. The video also shows the bot taking
  Grip damage repeatedly without answering it.
- The match after both fixes, 300 s, defaults against `legacy`: speed 0.63
  against 0.38, time wet 21% against 40%, kills 7 against 3, use presses
  1.9 to 5.5 a minute against 9 and 27.
- Three matches (16 minutes) of the defaults against the defaults with
  `conc_alt_range=99`, `heavy_hold=0` and `item_pull=0`. The new group
  fired 26 shells at a mean range of 3.0 to 3.2 units and 2 beams where the
  shell was not safe; the old group fired only beams, 12 of them, at a mean
  of 1.2 to 2.8. Both fire the rifle less often than it is in hand. In the
  last match, the one with
  the blocked-path rule built in, the new group put a heavy away 9 times
  (5 out of ammo, 4 too close) and the old group 29 times, 13 of them for a
  path that was only blocked. Kills over the three were 28 to 23 and deaths
  21 to 31. The first of the three had no blocked-path rule yet, and one
  match of this size cannot rank two settings (see below). 32 item pulls
  were cast and 23 items caught, among them a full shield, a repeater, a
  crossbow and a stormtrooper rifle. An earlier match caught a concussion
  rifle.
- The driver suite (73 groups) passes with the legacy values, with the new
  defaults and under the sanitizers; it now covers the shell and beam rule,
  holding a heavy through a blocked path, firing in a dodge hop, an item
  pull from aim to catch, hazards, laying a mine and a thermal throw from
  selection to release.
- The fixes from the recordings: the driver suite (82 groups, 7 of them new)
  passes with the legacy values, with the new defaults and under the
  sanitizers. Running the older groups on the new defaults needs a few of
  them to pin a tactic whose change is deliberate: swim pricing in one graph
  with hand-set edge costs, the running-arc Force Jump model in two arc
  tests, and an armed bot in one pickup-value test.
- Running, pulls on the move and packs: the driver suite (85 groups, 3 of
  them new) passes with the legacy values, with the new defaults and under
  the sanitizers. The new groups cover the running stop check (pit, wall,
  step up, small and big steps down, footing), running onto a pickup, a
  pull run through from cast to catch (waiting where the way is unsafe,
  closing in, bouncing, letting go when a fight starts), the denial worth,
  the way onto a pack on a shelf found from the node nearest it, and packs
  on a pool floor and just under the surface. Two older groups now say
  which they test: the item pull standing still, and the wall that ends a
  run only under the legacy rule.
- Three matches on Canyon Oasis with eight bots (16 minutes). Defaults
  against `legacy`, six minutes: 60 kills and 42 deaths against 40 and 58;
  3.0 s dead per death against 4.5; 80 seconds of firing while wet against
  23; two exit spots given way. Defaults against the defaults with
  `water_fight=0`, bot profiles swapped, six minutes: 43 and 49 against 48
  and 46, time wet 15% against 17%. That match does not show water fighting
  changing the score or the time in water; most firing in water already
  happens outside the climb out (33 against 38 seconds). An all-default
  match of four minutes: eleven pulled guns chased.
- Five more four-minute recordings of the bot's own client, each reviewed
  against its log before the next change. They found the corridor wall
  (above, `fjump_standstill`), a bot dithering at a pool's edge right after a
  respawn while its pickup choice flipped between near-equal guns (the
  resupply ordering and hold), Pulls spent during a Grip (above,
  `absorb_reserve`) and Speed down for long stretches with mana spent on
  Absorb. The last recording, with everything above, still shows long swims
  through the canal tunnel after a run-off from the alcove ledge, and a death
  under Grip once Absorb was down and mana was short.
- Four matches on Canyon Oasis with mines on (23 minutes): 12 mines laid,
  14 steps away from a bot's own fresh mine, none from anyone else's. The
  charges lie on a ledge the planner does not reach; five of the six bots
  that laid mines got them with Item Pull. Whether a mine killed anyone is not measured. No thermal was thrown:
  the map's one thermal lies in the pool where the planner has no node, and
  no bot picked it up. On m5, which has four of each, the bots barely move
  (fifty confinement escapes each in six minutes) and its heavy guns are
  unreachable to the planner, so it was no test.
- Running, item pulls and packs. In the last recording's match the bots
  ran 16 to 22 percent of the time they moved on foot. Four five-minute
  matches on Canyon Oasis, two bots on the defaults against two with
  `always_run`, `pull_on_move`, `pack_hunt` and `pack_deny` off, profiles
  swapped between matches, trace logging on every bot:

  | match | speed, new / old | running, share of time on foot | standing still | time wet | packs taken | kills / deaths |
  | --- | --- | --- | --- | --- | --- | --- |
  | 1 | 0.72 / 0.63 | 50-55% / 14-21% | 9% / 12% | 26% / 13% | 10 / 15 | 18/22 against 22/18 |
  | 2 | 0.76 / 0.59 | 48-56% / 12-25% | 11% / 13% | 13% / 15% | 15 / 6 | 19/18 against 16/17 |
  | 3 | 0.72 / 0.55 | 44-51% / 15-27% | 8% / 14% | 17% / 24% | 12 / 7 | 23/15 against 11/19 |
  | 4 | 0.74 / 0.59 | 51-55% / 13-24% | 12% / 13% | 26% / 14% | 9 / 12 | 11/15 against 18/14 |

  Over the four, kills and deaths are level (71/70 against 67/68). Among
  the pack verdicts, 'no way in' came up once for the new group against 152
  times for the old, and 'out of reach' 14 times against 40; after the fix
  for packs floating under the surface (matches 2 to 4), five of the new
  group's six were packs still moving. The new group went into water after
  packs 18 times, for a rail detonator, a repeater or a concussion rifle;
  the old group never could, and was wet less in two of the four matches.
  Item pulls: the new group started 64 and caught 27, the old group started
  127 and caught 47; a bot that runs reaches more items by touch. What still
  keeps the new group walking, in seconds per bot per match (`run_no` in
  `BOT_MOVE`, matches 3 and 4): a pit, ledge or water's edge within a
  running stop 9 to 15, no ordinary footing (in the air, wading, crouched) 4
  to 17, arriving at a jump, drop or lift leg 5 to 13. The edge was always
  found before any water or ledge drop beyond it.

- Lips, traps and jump margins: the driver suite (88 groups, 3 of them
  new) passes with the legacy values, with the new defaults and under the
  sanitizers. The new groups cover a bot on a lip with its centre past the
  edge (stepping back, the hop kept for a bot with floor under it, the
  nearest node from the floor underfoot), a lightning trap found from its
  COG symbols (spot in reach of the use ray, zone nodes, avoidance, walking
  off an armed ramp, one press on an opponent's approach, the server's
  frame as proof, legacy leaving it alone) and a detonator throw, and the
  shelf jump refused 0.1 past its lip but kept 0.4 past it, with the slow
  launch coming back down. The Canyon Oasis walkway perch, replayed against
  the level's own geometry: every wanted direction now steps back onto the
  platform (legacy: no movement in half of them).
- Two eight-minute matches on Canyon Oasis, two bots on the new defaults
  against two with `lip_escape`, `trap_avoid`, `trap_use` and
  `jump_margin` off, profiles swapped (`trap_use` was 2.5 then): kills and
  deaths 51/52 against 52/52; running jumps 11 landed and none fell for
  the new group, 19 landed and 3 fell for the old; nobody sprang a trap.
  With traps every bot's: on Nar Shaddaa, four bots with `trap_use` 8 and
  `trap_chance` 1 for two minutes, a detonator switch and the turret switch
  were each sprung once, from 0.33 and 0.10 away, each with an opponent in
  its zone, and the others walked out of the turrets' cones. With
  `trap_use` 4, a later 150 s check had one turret spring with two
  opponents in the zone: one walked out, the other lost 38, 33 and 26
  health to three volleys inside it. On Canyon Oasis with the eager values
  two bots went for the lightning switch; one armed it and the other was
  beaten to it. In the recording that goes with this (Red on `trap_use` 8
  and `trap_chance` 1, three opponents on the previous release), Red armed
  the ramp 38 seconds in. Off her screen Katarn died twice with no killer
  named ("Bot_Katarn died"), once logged on the ramp at 0 health, and the
  other two were logged on it at 22 and 4 health. Natural use is rare: on
  the defaults, a 180 s four-bot check on Canyon Oasis had two attempts
  that ran out of time in fights (the switch platform is reached from
  below by a Force Jump), and a 200 s one, after the time allowed grew with
  the walk, had none.
- Trap disarm and the force field: the driver suite (90 groups, 2 of them
  new) passes with the legacy values, with the new defaults and under the
  sanitizers. One new group takes an armed ramp through being left alone
  while new and while an opponent is near it, being taken down from
  farther the longer it stands, the press with the frame as proof, the
  ramp back in the routes within half a second, and legacy leaving it
  armed. The other finds a force field from its COG (a switch and a spot
  to press it from on each side), checks that no ordinary leg goes through
  the face or ends against it and that one gate leg crosses each way, and
  prices a gate while the field is on. It then takes a route through the
  field to the switch on the bot's side, waits short of the face, presses,
  goes on to the goal once the field is open, treats the field as a wall
  when its switch cannot be worked, and has legacy treat it as a wall. On
  Nar Shaddaa's own geometry (offline): 20 gate legs, the same whether the
  field was on or off when the graph was built, and with the field on a
  bot that spawned in the strip reaches 567 of the 640 nodes, against 23.
- Live, five minutes each, four bots on the defaults. Nar Shaddaa, three
  matches, each with the field opened once and then every bot through it
  and back (11 to 15 of each bot's ten-second position samples were behind
  it); no bot waited at the field. In the first, the field's price counted
  only the way down from the switch above it: bots went for that switch
  eight times, two runs timed out on the long way round the level, one
  lost its route, one was beaten to it, three ended when the bot died or
  the match did, and one opened it. With the way up priced too, the second had four runs,
  one opening it and three given up as `too-far`, two of those from right
  below the switch in the middle of the Force Jump up, when the bot looked
  for the nearest node in the air. Runs now hold their way through a jump.
  In the third, a bot that spawned in the strip opened the field from
  inside within ten seconds, and the turret trap behind it, out of
  everyone's reach before, was then sprung three times. Canyon Oasis: with
  `trap_use` 8 and `trap_chance` 1, Boba Fett armed the ramp about eight
  seconds in; it stood armed about 55 seconds, with opponents near it at
  times, and then Katarn walked 6.4 units of path to the switch and
  disarmed it with one press. On the defaults, one match before runs held
  their way through a jump had nobody arm it in five minutes; the match
  after had Boba Fett arm it in passing at 171 seconds, and it stood about
  100 seconds, everyone 7 to 16 units of path from the switch, until Jan
  Ors came within 6 and disarmed it. Every bot read each change. The reach
  for taking it down was then allowed to grow past `trap_use`, to twice
  it, which has not been run live.
- Lifts, Force Jump margins, field treks, dead ends, narrow openings and
  the lift-shaft ledges: the driver suite (95 groups; five new, the force
  field's extended) passes with the legacy values, with the new defaults
  and under the sanitizers, as do the collision, companion, hearing,
  portal, stock ground and loadout suites and the 251 Python tests. On Nar
  Shaddaa's own geometry (offline) the graph keeps 83 Force Jump legs
  whether it is built at 60 or 30 frames a second, and leg 144 to 83 is
  gone; a gate in the field costs 2 to 8 units from the strip and 28 to 31
  from the main side.
- Live, five minutes each, four bots on the defaults, Red's own rendered
  client recorded. Nar Shaddaa: Red refused none of the legs under the
  main-side field switch (six refusals of two of them in the recording
  before) and one leg elsewhere once, as did two other bots; she opened the
  field once, from 0.14 away, and no two of her ten-second position
  samples were the same. Bespin took eight recordings, each turning up a
  way to stay stuck that the one before had not: the pit (four and a half
  minutes on its hatch), a door alcove (three minutes at its mouth), a lift
  deck 0.09 off its opening (25 seconds), a lift wait left over from a
  death that kept the stuck checks off, the railgun alcove spawn (three
  minutes), and the hatch pressed from beside the wall (two minutes, twice).
  Each has its fix above. In the last, no bot had two ten-second samples in
  the same place or more than one in the pit; across the four bots there
  were 4 hops off the alcoves, 11 lift calls, 21 step-offs and 10 hatch
  presses. Five step-offs timed out, all Boba Fett's in one 25-second
  stretch on a deck at the top of a lift, pressed into the corner of the
  shaft 0.11 off the middle of the opening: the move back onto its line met
  the jamb's corner. `leg_square` (under Narrow openings) is the fix.

Read the table with care. Two groups on identical settings in one 240 s
match differed by 0.48 against 0.63 in speed and 36% against 19% in time
wet, so a single match of this size cannot rank two settings. What the
matches do show: the walking, the slow sinking and the eight-second air
rule were real, and the kills are level. Nothing here shows the new
defaults winning fights.

Not established: any map but Canyon Oasis, any match with a human in it,
Full Force play, and the presets' value. With `always_run` the bots run
about half the time they move on foot; the rest is near pits and water's
edges, in the air, and arriving at jumps. Running has not made them fall
into water more often in these matches (13 entries from walking legs
against 22 in the first three), but nobody was trying to knock them in.
Whether pulling on the move or the pack changes win fights is not
measured: the kills above are level.
The swim pre-check and the jump controller have no fixture test; their
parts do. Twelve jumps is a small sample: nobody was shooting at most of
them, a missed jump into that alcove is a two-unit fall, and there is no
abort once the sprint starts. Running jumps have only been seen at rank
four; the solver reports a way into the alcove at Force Jump rank three
and none below. No jump across a level gap at full speed has been tried
live. Run-offs have no fixture test for their geometry, only for the choice
of plan, and neither have the jumps out of water. Dodge jumps and firing
in the air are built and happen, but whether they save health is not
measured: in one 300 s match four bots dodged 17 times and two of them fired
for 3 seconds in the air. After one jump fell short at 9 percent under its
sprint speed, jumps must now land at 90 and 109 percent of it, which halves
the ways into the alcove at rank four (three are left). Behaviour on moving platforms is untested.
Thermal throws are tested only in fixtures so far. Mines are laid only on
item spots, not on a retreat. Grip is now answered with Protection or
Absorb, also mid-climb out of water; whether that saves health is not
measured. Whether the beam's 0.8 degree aim tolerance is what
keeps beam counts low has not been checked. Item pulls have not been seen
reaching the concussion rifle in its alcove from below.

## Human footage

Two public Full Force Canyon Oasis duels with the same camera player were
sampled as single stills: about 28 frames across the first ten minutes of
[Spidey versus Durham](https://www.youtube.com/watch?v=_tTWrQepvn4), and ten
frames between 2:00 and 30:20 of
[Spidey versus WD_Shinji](https://www.youtube.com/watch?v=XfU43kYxC88).

In every sampled frame the player is on dry ground: rock ledges, the upper
metal walkways, the canal edge. None shows the player swimming. Force
Seeing is active in nearly all of them. A long gun is in hand within about
40 seconds of the first video, and a concussion blast is visible near 6:00.

That supports treating water as a route of last resort while still going
for the heavy guns, which is what the water tactics above encode. It does
not establish how those players reached the concussion rifle, how fast they
moved, or what one player's habits say about others. Stills show no inputs.
