# Handoff to Coda: tactics and movement (PR #3)

From Red (Claude), 24 November 2026, branch `feature/tactics-and-movement`.
Andrei asked for this note with the push. The detail for each item is in
[BOT_TACTICS.md](BOT_TACTICS.md); this is the map.

## What this push adds

Seven tactics since the last push, 64 in all. Each has a legacy value that
restores the old behaviour (`python3 -m bots.tactics list`).

- `lift_call`: a lift that will not come is called with a button in reach,
  or a rider steps off across the threshold, since crossing it is what
  starts the stock elevators. A deck is boarded only after it has stood
  still for 0.3 s.
- `lift_hop`: a ledge partway up a lift shaft is left by the deck, stepped
  onto as it passes or dropped onto where it stands below. Bespin's railgun
  and concussion rifle alcoves each hold a spawn and had no way out.
- `fjump_margin`: a Force Jump leg goes into the graph only if it still
  flies at 25 frames a second, and the launch check uses the averaged frame
  time.
- `dead_end`: with no route out from a floor door (Bespin's pit hatch), the
  bot steps over the seam where the two pieces part, looks down and presses
  use.
- `leg_axis`: off a leg's line with the straight way blocked, the bot gets
  back onto the line first. Bespin's door alcoves and lift openings are 0.2
  wide.
- `leg_square`: pressed against the wall beside such an opening, the bot
  steps square onto the line until its whole body clears the jamb.
- `saber_heavy`: the saber's heavy secondary from contact wherever the
  target will still be in reach as it lands; the quick primary at a target
  pulling away, near a protected player, or underwater; no swing out of
  contact.

Force-field switch runs are also capped at 25 units, with a back-off of 15,
30, 60, then 120 s on a field whose switch cannot be worked.

## Where it lives

- `src/AI/jkBotNavigate.inc`: `Bot_LiftMove`, `Bot_LiftPress`,
  `Bot_LiftThreshold`, `Bot_LiftHop`, `Bot_BodyClear`, `Bot_AxisMove`, and
  the leg-axis block at the end of `Bot_Navigate`.
- `src/AI/jkBotNavigation.inc`: the nav state (`liftStep`, `hopUntil`,
  `squareNode`, the dead-end fields), lift and hop legs in `Bot_EdgeMode`,
  and the `fjump_margin` check.
- `src/AI/jkBotTraps.inc`: `Bot_BindLifts`, which finds buttons and
  thresholds through the `00_elev_switch*.cog` symbols; field reach and
  back-off.
- `src/AI/jkBot.c`: `Bot_DeadEnd`, `Bot_DoorSeam`, respawn resets, and the
  `BOT_MOVE` counters (`lift_calls`, `lift_steps`, `lift_hops`,
  `dead_end_uses`, `leg_axis`, `leg_square`, `saber_heavy`, `saber_light`).
- `src/AI/jkBotCombat.inc`: `Bot_SaberHeavy` and its use in
  `Bot_FireGunShot`.
- The overlay also changes `src/Devices/sithControl.c` (from an earlier
  round: `sithControl_GetAxis` returns the bot's own look delta).
  BOT_TACTICS.md still says it touches only `src/AI`.

## Engine and stock-data facts the code leans on

Checked against the OpenJKDF2 source and the stock GOBs.

- Bodies: `walkplayer` has size and movesize 0.065. The steering probes are
  slimmer: `Bot_NavDirectMove` sweeps 0.052 and the ground corridor 0.055.
- Sphere sweeps (`sithIntersect_CheckSphereFaceIntersectionEx`): a body is
  stopped where it first touches a wall's plane if that point lies within
  its full radius of the solid face, edges included. A body already across
  the plane and moving into it is stopped at distance 0. Moving along a
  wall or away from it is free. Beside a 0.2 opening this leaves the body's
  centre a band 0.07 wide. `Bot_Clear` ignores hits within 0.008 of the
  sweep's end.
- Lifts: `00_elev_switch.cog` (Nar Shaddaa) sends the lift on a crossing or
  a button and brings it back after 2 s. `00_elev_switch2.cog` (Bespin)
  toggles it on a crossing while it stands still (after 0.25 s) or on a
  call button. Lifts move about a unit a second. `e3x3` decks are 0.296
  square, their top 0.0137 above the frame.
- Saber (`weap_saber.cog`): walking forward, the primary is three quick
  slashes of 40, 40 and 60 (waits 0.25, 0.25 and 1.0 s; blade ray 0.15 to
  0.2). Standing, it is 50 (ray 0.25, wait 0.8); strafing or backing, 50
  (ray 0.15, wait 0.8). The secondary is the heavy swing: 160 damage, ray
  0.3, wait 2.0. Underwater both buttons give one attack (50, wait 1.0).
  Damage frames come from the `.key` markers (4 on, 5 off) at 15 fps: the
  heavy swing (`kycharge.key`) 0.33 to 0.67 and 0.8 to 1.13 s, a quick
  slash 0.17 to 0.4 s. Either trigger clears the autoblock flag 0x2000
  until 0.5 s after release. A target with 0x2000 set blocks a hit that
  arrives within its fov (0.71, about 45 degrees either side) with chance
  1.0.
- Shields (`item_shields.cog`) take half of a saber hit (type 16) until they
  are down to 50; the other half always reaches health.
- Falls: (v − 2.5)² × 45 with air drag 0.5, so 1.6 units costs about 14 and
  1.7 about 17.

## How it was checked

- `native/tests`: 97 driver groups pass with the legacy baselines, with
  `-DJKBOT_TEST_NEW_DEFAULTS`, and under the sanitizers. The collision,
  companion, hearing, portal, stock ground and loadout suites pass, and so
  do the 251 tests from `python3 -m unittest discover -s tests`.
- New groups in `test_bot_tactic_fixes.inc`: lift call, lift hop,
  fjump_margin, dead end, leg axis and leg square. The saber_heavy cases
  are in `test_bot_altfire.inc`; the older saber cases there pin
  `saber_heavy` to 0. The slot wall in `test_bot_plain_geometry.inc` now
  judges a sweep where the body first touches the wall's plane, as the
  engine does, as well as where the body is centred on it.
- Offline, on Bespin's own geometry with the engine's collision code: a
  rider stepping off from 21 spots at each of the 8 lift stops gets off
  from all 168 with `leg_square`, and from 152 without. The harness was a
  scratch one built on `test_bot_portal_collision.c`'s fixture and is not in
  the repo.
- Live: one five-minute match each on Bespin and Nar Shaddaa, four bots on
  this build, with Red's client recorded. No bot stood in one place for two
  10-second samples running, except the reactor-rim case below. Bespin had
  31 lift step-offs and 2 timeouts: one a single 3-second wait, the other
  cut short by a death. The recording before had 5, all one bot pinned in a
  shaft corner for 25 s. Red killed Boba with a heavy swing while he held
  her in a Force Grip. One match per map says nothing about win rates.

## Open, roughly in order

1. Bespin's reactor rim. The bacta tank (thing 69 at 0.338, −0.462, 1.782)
   sits on the rim of the reactor shaft's floor opening (surface 1835, a
   5.5-unit drop). After picking it up Red stood 11 s with every heading
   refused as a drop, her centre 0.012 outside the opening's edge, until
   `BOT_CONFINED` moved her on.
2. The weapon alcoves from a lift. `lift_hop` gives legs out of Bespin's
   railgun (sector 75) and concussion rifle (sector 61) alcoves but none in,
   so a bot cannot fetch those guns from a deck.
3. Saber timing. Frontal hits on a guarding opponent are blocked whichever
   button is pressed. A bot can read each opponent's 0x2000 flag and facing,
   so it could swing while the opponent attacks (flag clear) or from
   outside its block cone. Tapping the trigger rather than holding it would
   also bring the bot's own guard back 0.5 s after release.
4. Nar Shaddaa: single refusals of the Force Jump legs from 17 to 409 and
   410, launched 0.03 to 0.10 off the leg.
5. Walking legs, not lifts: the leg-axis block judges the straight way with
   the 0.055 corridor. A body entering a 0.2 opening 0.035 to 0.045 off the
   line can still catch the jamb's corner unless it was already squaring.
   Not seen live.

Thank you for the groundwork all of this stands on.

Red
