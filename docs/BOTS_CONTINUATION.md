# Competitive bot continuation

The [development tools](../scripts/bot_development/README.md) preserve the capture,
analysis, source verification and native observation helpers used for this work.
The packaged custom JKWeb runtime includes its complete source patch and build
inputs; the tool guide maps each artifact to its repository location.

## Packaged fifth refinement candidate

The Linux and JKWeb packages include the reviewed correction for optional dry upgrades through a
recently failed water approach, alongside the earlier supply and bank-landing repairs. Independent
relinks reproduced each runtime file byte for byte. Candidate 5 passed four-seat capture checks
and failed sustained-movement qualification. The preceding trials remain documented below.

| Packaged runtime | SHA-256 | Verification |
| --- | --- | --- |
| Linux x86-64 bot | `862e566209dae8fab218243a47455b5a5616bf98fb8d1f09fa65969f9c8519aa` | 205 translation units scanned, one rebuilt (`jkBot.c`), 223 source and 218 link-input hashes verified. The patched source passed 79 named groups and 54 legal loadouts. [Native build receipt](../qa/bots-refinement-native-build.json) |
| JKWeb WASM | `9e802daf1ebeb808cf3822bd63e9b58506c34be4126a7ce5bdc26c9295751542` | All 28 changed source hashes verified against the patched, pinned JKWeb source. [Browser build receipt](../qa/bots-refinement-web-build.json) |
| JKWeb JavaScript | `dd348b7f5dace28a4cd387eca7942eb30e25ef78b091e87217937a39cf2a2cd7` | Matches the same browser relink. |

## Fifth refinement trial

Runtime `5ed040735bfd1ef57448a47aa063453d6b53ef18` completed 240.0305 seconds in the four-seat
arena. The capture verified Lily’s third-person model, red saber side and tip, and game audio.
All seats ran autonomously. The trace contained seven failed-approach markers and three nearly
complete retry windows with an observed bank return. During those windows no identified dry
railgun or repeater upgrade drew a healthy, heavily armed bot back into the marked shaft.
One pack’s contents were unknown, and the trace omits the planner’s rejected options.

| Seat | Wet / living samples | Total time confined horizontally | Longest interval | Sampled opening → closing kills/deaths |
| --- | ---: | ---: | ---: | --- |
| Lily | 489 / 800 | 127.79 s | 16.78 s | 0/0 → 2/2 |
| Boba | 426 / 789 | 64.76 s | 13.61 s | 0/1 → 3/5 |
| Jan | 257 / 801 | 53.88 s | 38.23 s | 0/0 → 4/4 |
| Yun | 520 / 810 | 150.31 s | 23.98 s | 1/1 → 3/4 |

Useful pickups still cost too much time. Yun went back through the shaft for two dry shield
recharges. Across 115 living samples spanning 31.695 seconds, he held concussion with 80 cells,
reported no target and stayed at 100 health and 70 shields. Lily also returned for dry Bacta
with full health and shields. Her carried Bacta count was unavailable. All seats had other
periods of at least 39 seconds on mapped dry ground. These unseeded matches establish neither
a consistent score advantage nor an improvement attributable to the policy alone.
[Four-build comparison and capture verification](../qa/bots-refinement5-live.json)

The next test is forward traversal from supported bank 41 through the deep shaft to an eligible
shield. Reproduce Yun’s inventory, offer a reachable alternative, and measure route progress,
time to an actual shield gain and the cost of an air return. Include a low-health or imminent-
combat case and a case where the shaft is the only route. The existing 27 stock replays measure
escape to the bank. Forward traversal still needs its own measurement.

## Fourth refinement trial

All four seats ran autonomously on local runtime commit `097b361eed588cbe1eb543778218b489f0aa49a0`.
The capture verified Lily’s third-person model, both red saber materials and game audio. Lily
spent 23.15 seconds in intervals of little horizontal progress, down from 189.06 in candidate 3.
She had no sampled positions in the problem shaft, so this round gave no direct test of her
response at that bank. These three matches were unseeded.

| Seat | Wet / living samples | Total time confined horizontally | Longest interval | Sampled opening → closing kills/deaths |
| --- | ---: | ---: | ---: | --- |
| Lily | 103 / 815 | 23.15 s | 5.37 s | 0/0 → 2/2 |
| Boba | 387 / 826 | 125.81 s | 21.83 s | 0/0 → 2/2 |
| Jan | 547 / 819 | 150.68 s | 25.37 s | 1/0 → 1/3 |
| Yun | 300 / 826 | 61.00 s | 12.93 s | 0/1 → 5/3 |

Boba returned through the failed sector 41→54 crossing for a railgun and repeater on dry ground.
Across 62 and 61 consecutive shaft samples those trips showed 100 health, 100 shields, a selected
concussion rifle, 88 cells and no target. Jan also returned for a dry railgun while armed.
She had zero shields, which makes her separate trip toward shield recharge a different decision.
The packaged correction targets optional dry upgrades that call for another costly dive while
preserving necessary recovery, pursuit and objective transit. Controlled route tests and independent
review passed. The fifth refinement trial above records the live result. [Dry-detour regression receipt](../qa/bots-dry-supply-detour.json) [Four-seat comparison and private video verification](../qa/bots-refinement4-live.json)

## Third refinement trial

The 240.002-second recording on local runtime commit `536d293` captured four hardware-accelerated
seats, all autonomous, with Lily’s third-person model and red saber side and tip verified.
Lily repeatedly reached a dry sector and then selected another underwater supply. Across 840
fresh living states, 659 were wet, 178 dry and three ambiguous. She spent 189.055 seconds in
17 intervals of little horizontal progress, compared with 52.756 seconds in the preceding run.
Her sampled score went from 0/1 to 1/2 kills/deaths. After 43.4 seconds, she held the concussion
rifle in 700 of 706 remaining living observations and had a target in only ten.

The trace showed eight returns for air by Lily and 19 across all four seats. No confidently
same-life replan for the identical failed item occurred inside its 45-second cooldown. Choosing
another supply in the same area still led back to water. [Live trial and video verification](../qa/bots-refinement3-live.json)

## Supply choices after an unsuccessful dive

A source fixture reproduced the loop with two distinct submerged items reached through the same
bank. The revised planner gives an adequately armed bot 45 seconds to pursue other destinations
after an unsuccessful dive there. Water can still be the only way to a dry shield, a backpack or an
opponent. The fixture verified that the bot keeps that destination through its underwater equipment
rescan. On the tested Canyon Oasis bank the ordinary graph still reaches 483 of 558 anchors.

Independent review accepted the revision after rerunning all 55 driver groups against each source
configuration. All 27 bank replay results matched the preceding build. The fourth refinement trial above exposed a remaining failure when the
chosen item was dry and the route crossed the failed bank. [Source fixtures and baseline exceptions](../qa/bots-supply-approach-retry.json)

## Four-minute Canyon Oasis baseline

The second refinement candidate ran a four-seat full-Force guns match on `m10.jkl`.
Its JKWeb base was `7a6f95c9a3399e59acbf019dc6b25f9981d29dff`. The recorded WASM SHA-256
was `ea56c2215d2d644170f475516d28fa99694fc85cbea60fbd96f5f698b610608d`.

Lily went from 0/0 to 6/2 kills/deaths, planned six backpack approaches and had 20 same-life
sample intervals with an ammunition increase. The trace recorded concussion, repeater, bowcaster
and saber alternate-fire requests. Stock input requests cannot establish a kill’s cause.
Boba’s longest interval of horizontal confinement near the pool was 54.087 seconds, and Lily’s
final interval was 10.072 seconds. See the [trial summary](BOTS_BEHAVIOR.md#four-minute-canyon-oasis-equipment-trial).

## Supply recovery after the baseline

Both engine source configurations passed independent driver checks for three corrections. The bot
now turns for air on stock contact with the intended underwater supply despite a delayed grant.
Separate failed dives retain their own retry deadlines. A single checked intermediate node can
connect a player to a backpack beyond direct reach. The native companion transport passed. A
POSIX-only harness applied to the browser fork reproduced its existing chat assertion failure on
both the baseline and corrected sources. See the [test matrix](../qa/bots-supply-recovery.json).

## Bank landing under stock physics

Two recorded approaches timed out before the fix at all four tested headings. The corrected
predictor permits a walk of up to 0.16 world units from supported touchdown to the dry anchor.
At a 74 ms control interval, the swimmer reached sustained dry support in 5.133–5.207 seconds
with 100 HP. At 87 ms it took 21.127 seconds with 90 HP. All 27 cases passed on both source
configurations. One previously successful 79 ms control slowed from 25.573 to 29.940 seconds
and still finished with 60 HP. The third refinement trial above shows how these physically
reachable banks can coexist with an unproductive choice of the next supply route.
[Bank replay matrix](../qa/bots-bank-landing.json)

## Next navigation test

The source check identifies two separate questions. The bot starts urgent air recovery at eight
seconds of endurance or continuous immersion (or below 30 HP), while the pinned engine first
requests drowning damage after 20 seconds and resets endurance at a dry sector or the water
surface. The controller also derives forward swimming from horizontal waypoint error, so a
nearly vertical route can lose pitched forward thrust. The observed shield trips turned back
before reaching the deeper continuation. Neither fact establishes that a longer dive is safe.

The next replay must use ordinary inputs and stock collision to measure actual forward portal
passage, time to the next breath, damage and confirmed item gain. The existing 27-case suite
checks supported dry-bank escape; its seeded dive age and wet-to-dry setup cannot prove forward
wet-to-wet transit. Compare baseline steering and breathing decisions with isolated candidates
before changing a production deadline. Primary implementation references are `sithActor_Update`
in `src/World/sithActor.c`, `Bot_NeedsAir` in `src/AI/jkBotNavigation.inc`, and swimming controls
in `src/AI/jkBotNavigate.inc`. All use the pinned source identities in the build receipts.

## Competitive work still open

| Capability | Evidence needed |
| --- | --- |
| Time and contest important pickups | A route-time estimate in seconds, stock respawn and touch eligibility, and contested runs showing who actually got the item. The current weighted routing cost includes penalties as well as distance. |
| Disengage, re-kit and re-enter a fight | An autonomous decision that breaks exposure when supplies or health are poor, reaches a viable pickup under pressure and resumes combat after recovery. |
| Fight while moving vertically | Replay heavy-weapon recoil, muzzle clearance and predicted landing together. The checked combat hop currently withholds concussion and rail during committed flight. Validate safer lead against airborne opponents. |
| Judge results against human opponents | Repeat on named builds and compare recorded engagements with human play. A single four-bot scoreboard cannot establish elite human performance. |

The [review dispositions](reviews/2026-11-22-elite-bot-feedback.md) cover stock mechanics, surge
eligibility, enemy state, Force timing and remaining questions in more detail.
