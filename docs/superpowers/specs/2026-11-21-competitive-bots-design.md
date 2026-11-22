# Competitive JKDF2 bots with an external agent companion

Date: 2026-11-21. Source baseline: `260ef1449e8d65fefff2c574dab8dbce824cffad`.

## Intent and acceptance target

Build on JK Cross Server's ordinary-player bots. The target is an opponent that can rival experienced and ultimately top-level human players in FF Guns, FF Sabers, NF Guns and NF Sabers. A local controller handles the game continuously. An authenticated external agent can attach to its player identity, exchange ordinary game chat, observe its experience and adjust strategy asynchronously.

The requested scope is JKDF2, with jkweb and OpenJKDF2 compatibility. Stock multiplayer map knowledge includes authored spawn points, likely exits and resource routes. Spawn pressure and prediction of future player movement are part of the competitive target. Concussion aim must consider useful floor or wall impacts, not just the opponent's current body position. Human gameplay footage may inform tactics, but uploader descriptions alone are not evidence that a tactic was observed.

This document distinguishes the full product target from implementation increments. A source audit, unit test, joined client, authored-map catalog or bot-versus-bot win does not establish top-player performance. No new human-match result is claimed here.

## What survives and what must change

The current repository already launches independent native clients, uses ordinary inputs, assigns legal Force profiles, selects weapons and pickups, generates collision-checked navigation and emits preset chat. Human clients use the existing server transports. The separate host spectator is an administration feature with more information than an ordinary player.

Source inspection identifies these gaps:

| Area | Existing mechanism | Required development |
| --- | --- | --- |
| Rules | Three live booleans in `bots/settings.py` | Explicit four-mode contracts, recorded permitted powers and host rules |
| Map coverage | Nine-map pickup catalog; generated route graph | Every selectable spawn and important route tested, including stateful doors/lifts |
| Spawn knowledge | Starts are navigation seeds; audit emits only counts | Authored poses, engine-eligible start mapping, probable exits and spawn-pressure policy |
| Prediction | `Bot_Lead` extrapolates the engine replica velocity | Distinguish observed motion and network correction; weapon-mode-specific interception |
| Splash | Safety separation around the target; direct target aiming | Compare reachable first-impact surfaces and likely future blast exposure |
| Sabers | Primary attack, approach and alternating strafe | Attack selection, spacing, timing, recovery, baiting and opponent adaptation |
| Perception | Some inventory and weapon observations consume synchronized state directly | One explicit player-observation model, with remembered state and uncertainty |
| Conversation | Preset outgoing persona lines | Incoming delivered chat, authenticated outgoing chat, external-controller lifecycle |
| Strategy | Session-wide combat switches | Per-player bounded intents that the local controller can execute and acknowledge |

The source audit found no observation gate in `Bot_ItemValue` before it reads item availability. `jkBot_ObserveWeapon` caches the remote weapon even when its sight-line condition for provocation is false. These are concrete places where replicated engine data must be separated from player knowledge. They are not evidence of malicious behavior, and no new runtime characterization is claimed.

`Bot_Combat` currently returns before its firing logic when direct target line of sight is lost. Retaining an existing target also bypasses the rear-view acquisition check. Future prediction work therefore needs an observation gate before refreshing enemy memory and a shot-plan entry point that can consume remembered or inferred positions without a live target pointer. Merely replacing `Bot_Lead` cannot produce the intended unseen-exit pressure.

Recorded historical checks include mixed retail/native/browser play and partial map traversal. The focused `50924ed7` bot / `6c4c25dd` host receipt records a `c3` key-door stall and movement without an item gain on `m_boss17`. Those results belong to their named binaries and do not certify new work.

## Architecture and approaches

**Selected implementation direction:** extend the existing native bot client, retain the server transports, and add an external companion bridge. This is the smallest continuation that keeps fast gameplay independent of model latency. The initial code stays in the existing C engine patch and Python tools/manager.

Two alternatives were considered. Running a language model on every movement/aim decision would couple combat to remote response times and provide a poor control boundary. Replacing the existing transport with a newly implemented synthetic player would duplicate engine, COG and synchronization behavior that the native client already supplies. A browser-native bot could eventually be useful for browser-specific network experiments, but it is not a prerequisite for the first native implementation.

Three distinct loops share a constrained world model:

1. **Control loop:** ordinary movement, turn, fire, inventory, Force and respawn inputs at the engine's normal input cadence. This loop never waits for the external agent.
2. **Tactical loop:** choose routes, resources, weapons, engagement state, firing solutions and likely intercepts. Plans have preconditions and expiration, and react immediately to hazards or changed rules.
3. **Companion loop:** consume bounded event summaries, converse, inspect results and select strategic intent. A slow, absent or disconnected agent leaves the local controller playing autonomously.

The external agent receives the same player knowledge used by tactics. It must not receive the unrestricted host spectator or the evaluator's full-state trace as its competitive observation feed.

## Knowledge and observation

Static map knowledge may include every authored spawn pose, geometry, item location, known map mechanism, legal route and known stock rule. The user explicitly wants the bots to exploit this knowledge. Dynamic knowledge includes the bot's own HUD state, visible opponents/projectiles, received chat, public game events and eligible sound observations. Remembered enemies and item timers carry their last observation time and uncertainty.

The top difficulty is intended to maximize competitive strength within the selected game rules; artificial misses and deliberately slow reactions are not a prerequisite. Timing, aim and decision limits must be declared in benchmark records. Easier practice profiles can be added after a strong reference policy exists.

The bot may infer an opponent's next route or likely respawn and fire at a plausible unseen approach. It must not read a future spawn RNG result, an unobserved actual spawn assignment or an evaluator-only position. A prediction is allowed to be wrong. Logs distinguish observation, remembered information and inference.

Safety checks that suppress accidental team damage must not expose their hidden inputs through strategic output. Existing peace behavior is a separate host rule; an elite competitive preset should not silently inherit casual-server conventions. Record spawn-pressure, team damage and permitted Force rules explicitly.

## Stock map and spawn atlas

The baseline catalog identifies six JK1MP levels: `m2.jkl`, `m4.jkl`, `m5.jkl`, `m10.jkl`, `m_boss15.jkl`, `m_boss17.jkl`; and three JK1CTF levels: `c1.jkl`, `c2.jkl`, `c3.jkl`. Running the new atlas against the installed original archives reproduced 193 authored player things: 17 in `m4`, 16 in each other JK1MP map and 32 in each JK1CTF map. This is not a claim that every authored thing is eligible under every game configuration.

The first atlas implementation must preserve, for each authored player start:

- Original thing index and authored encounter order.
- Template, inherited/overridden properties, position, pitch/yaw/roll and sector.
- Episode, map identity and SHA-256 of the bytes actually inspected.
- Source category `authored_player_thing`, with engine eligibility explicitly unverified unless separately checked.

Do not infer an engine start ordinal by sorting thing indices. Record source order first, then qualify the actual engine mapping. Preserve CTF lobby/team distinctions; map masks are not interchangeable with player admission limits. Reject malformed, duplicate, nonfinite or out-of-range spawn data rather than silently publishing a trustworthy-looking atlas.

The native spawn picker in the pinned engine chooses among mask-eligible starts and scans for an unoccupied start on overlap. Do not assume a farthest-from-enemy algorithm. A later spawn model uses this rule plus observed occupancy and public death information to maintain probabilities over eligible starts, then propagates likely paths to weapons, shields and escape routes. Evaluate the model against withheld match truth, which is never fed back into gameplay.

Each route records required ability, mana, inventory/key and mover state, expected duration, landing region and exit/escape options. Test from every eligible start in NF and FF settings. Distinguish a route that exists in a graph from one a bot physically completed. Stateful traversal, including the known `c3` door problem, remains an explicit qualification item.

## Motion, netcode and firing solutions

The bot's pinned native engine is `CodaLilitari/OpenJKDF2-MotS-Fixes` at `74e4657c4f1751d09af9ad9e056acb8f41997acb`. Its remote position handling can replace advertised movement velocity with a correction velocity derived from positional error. The current `Bot_Lead` reads that replica velocity and adds a capped travel estimate. This is not a calibrated measure of the opponent's intention or network delay.

Maintain timestamped motion observations with provenance, reset on identity change, teleport, death/respawn and map change, and estimate movement separately from replica correction. Predictions must be bounded by legal movement, route geometry and observation age. Consider several plausible futures: continued motion, strafe reversal, landing, movement toward a resource, or retreat through an exit. Unknown or stale timing is uncertainty, not a hardcoded ping value.

Network behavior is a capability profile, not merely a product name. Cross Server's pinned browser build and current upstream jkweb are different revisions. Current `tristamus/OpenJKDF2:web-mp` source at `7a6f95c9a3399e59acbf019dc6b25f9981d29dff` includes negotiated hit claims and target validation. Its comments specify Classic as the default, with older peers staying on Classic. The existing native bot does not automatically participate in the newer mode. Do not conflate transport compatibility with adoption of that protocol. Until mixed live tests succeed, compatibility claims remain limited to the exact previously qualified client revisions; reading a fallback path does not establish that a newer browser build joins or exchanges damage correctly.

The inspected original weapon data supplies useful calibration facts. Concussion primary uses `+concbullet` with velocity `(0, 7, 0)` and a `+conc_exp` explosion with radius `0.8`, damage `80` and force `200` in engine units. Secondary uses a distinct instant-impact path. The original COG charges eight cells for primary and four for secondary, but checks for at least eight at the common fire entry. These are loaded-data observations, not a promise of damage on every hit. Splash exposure also depends on collision, occlusion and the explosion's distance falloff. The inspected `Res2.gob/cog/weap_concrifle.cog` SHA-256 is `2ef67f24561d93033062530c32ab25c22c50e2613ead4f2dac24be054b661a3c`; the template values agree across the nine map hashes in the atlas receipt. Record the actual loaded template and script hashes for each future qualification run.

For each weapon and fire mode, obtain speed, gravity/acceleration where relevant, collision behavior, blast parameters, resource cost and attack timing from the loaded data and source. For a moving projectile, solve a feasible intercept over the predicted motion horizon. Any network correction term must match the actual negotiated profile and measured packet history; blindly adding half an RTT can double-count compensation. Distinguish projectile travel, packet age, rendering/interpolation, command-to-fire delay and target-side adjudication.

For concussion primary and other splash attacks:

1. Predict a distribution of plausible future opponent positions and landing areas.
2. Propose direct, floor and wall impact candidates near those positions.
3. Validate the first actual collision from the muzzle, not only an unobstructed center-to-center line.
4. Evaluate blast reach and occlusion using the actual explosion rules and loaded radius/falloff.
5. Score expected damage and positional pressure, minus self damage, forbidden team damage, ammunition and lost opportunities.
6. Fire only through ordinary inputs. Confirm outcomes from appropriate game events; a local visual hit or sent command is not proof of damage on another client.

This is also useful for landing traps, choke-point denial and spawn exits. It does not mean always aiming down: the selected impact must fit the target's predicted motion and the surfaces available.

## Four combat contracts

| Contract | Required tactical emphasis |
| --- | --- |
| NF Guns | Spawn exits, weapon/shield cycles, projectile interception, splash placement, position control, efficient disengagement and ammo management |
| FF Guns | All gun skills plus legal Force builds, mobility, disarm/counterplay, protection and mana budget matched to the opponent |
| NF Sabers | Approach angles, range, primary/secondary timing, attack recovery, feints/whiff punishment and hazard-aware footwork |
| FF Sabers | Saber fundamentals plus legal Force movement, defense and explicitly permitted offensive powers |

Host rules determine whether other weapons are available, what Force powers are legal and whether spawn pressure or peace conventions apply. Bot restraint settings alone do not impose the same restrictions on humans. True NF benchmark sessions use a game configuration that actually removes Force. FF builds must match the advertised rank and ordinary allocation rules.

A shared input arbiter applies the current rules after tactical and companion decisions. A coach cannot override rank, add health/ammunition, perform a teleport, select forbidden attacks or turn a strategy command into a server-admin command.

Opponent modeling belongs in the fast local system: measured strafe/reversal tendencies, preferred exits, weapon choices, resource timing and repeated overcommitment. The model carries uncertainty and decays; short-run patterns must not become permanent assumptions. Offline self-play or parameter optimization may improve these policies later, but is not proof of human-level strength.

## External agent presence and strategy

An external agent attaches to an ordinary bot identity with a scoped controller session. The bridge supports capability discovery, current player observation, cursor-based delivered events, ordinary in-game chat, a bounded strategy command, command status and release. The same interface can be wrapped by CLI, a tool server or an agent runtime. The active ChatGPT conversation needs an actual authorized tool connection to use it; an API agent can run separately. Neither is implicitly running today.

Commands have a unique ID, run/world identity, controller lease, expiry and an acknowledged outcome. Use player network identity plus generation/thing identity, not a reused slot number alone. Reject stale commands after reconnect, respawn where relevant or map transition. Distinguish queued, accepted, applied, superseded, expired and rejected from a successful game outcome. Only advertise capabilities the running bot actually consumes.

Initial strategy vocabulary: autonomous, pressure, resource control and recover. Additional parameters are bounded target priorities, preferred engagement range, resource preference and risk tolerance. Concrete commands such as controlling a known item, contesting a probable exit or withdrawing to recover must name valid map/entity references and permit local replanning. The controller can abandon a dangerous or impossible instruction and report why.

Incoming chat is delivered as speech from another player, not an instruction with operating-system or administration authority. Credentials stay separate from game chat and telemetry. Limit outgoing chat, preserve the stock encoding/length constraints and record the actual sender. An absent companion does not fabricate spontaneous Lilitari/Coda conversation; preset bot lines, if enabled, remain distinguishable from an attached agent.

The normal companion event feed should contain bounded summaries: own health/shields/mana/ammunition, observed combat, current goal, route failures, damage and death/respawn, delivered chat and command status. High-volume debug traces belong in evaluation tooling, not every language-model request. Slow consumers must not stall the game.

## Evidence and validation

Progress is reported in stages: parsed, planned, fixture-tested, built, connected, qualified on a map/mode, and competitively measured. Keep executable, source, map and rule hashes with each receipt.

Required checks include:

- All authored spawn records parsed and cross-checked; every eligible start has tested exit/resource/return routes for its mode.
- Prediction fixtures for strafe reversal, a jump/landing, stale packets, clock jitter, teleport, reconnect and correction-velocity contamination.
- Splash cases where direct aim loses to floor/wall aim, and where occlusion, self damage or an intervening surface reverses that decision.
- Perception cases with unseen item pickups, rear/occluded weapons, Persuasion, blindness and hidden respawns. Inferences remain explicitly uncertain.
- Companion round trips with an independent client: received chat, ordinary outgoing chat, an applied strategy change, expiration/fallback and bounded queues.
- Current pinned native and browser clients in mixed play, recording protocol capabilities, latency, jitter, loss, frame rate and relevant physics settings. Separately qualify a current upstream jkweb build: session join, Classic negotiation/fallback, primary/secondary concussion damage, saber damage, death/respawn and identity continuity. Test the newer hit protocol only where both peers actually negotiate it.
- Separate FF Guns, FF Sabers, NF Guns and NF Sabers match results against identified experienced opponents, then top-player challengers. Balance maps, starts and sides and keep tuning and evaluation matches separate.

Before human qualification, preregister the opponent cohort, rules, map rotation, match count and a concrete win-rate or score-difference target. The target must distinguish rivalry with experienced players from rivalry with the strongest available challengers. This requires actual challengers and must not be selected after seeing the results.

Report per-mode/per-map results, opponent cohort, match count and uncertainty. Score differential, survival, resource control, spawn-pressure conversion, aim/splash outcomes, route failures and self damage explain wins and losses. Paired coach-on/coach-off matches test the companion's contribution. Bot mirror matches and montage highlights cannot establish the requested human challenge.

## First implementation increments

The first reversible increment extends the existing map audit into an authored spawn atlas and preserves useful source data without claiming live eligibility. It runs against the user's existing installed archives and synthetic parser tests. Generated game-derived manifests are retained privately, not added as retail assets to the public repository.

The next increment isolates motion prediction and surface-target selection with deterministic tests and then integrates it into the actual native input driver. A source-only candidate is not a replacement for the packaged executable until built and qualified. The companion bridge is a separate end-to-end increment so chat and strategy can be demonstrated while the combat controller improves.

The full target remains the four-mode competitive bot with agent presence. Passing the first atlas increment is a foundation, not completion of that target.

## Primary source index

- [Cross Server baseline](https://github.com/CodaLilitari/jk-cross-server/tree/260ef1449e8d65fefff2c574dab8dbce824cffad)
- [Bot patch](https://github.com/CodaLilitari/jk-cross-server/blob/260ef1449e8d65fefff2c574dab8dbce824cffad/native/bot-client.patch): `Bot_UpdateTarget`, `Bot_Combat`, `Bot_Lead`, `Bot_ItemValue`, `Bot_Plan`, `jkBot_ObserveWeapon`, `jkBotPersona_Tick`.
- [Existing audit](https://github.com/CodaLilitari/jk-cross-server/blob/260ef1449e8d65fefff2c574dab8dbce824cffad/bots/map_audit.py) and [recorded stock catalog](https://github.com/CodaLilitari/jk-cross-server/blob/260ef1449e8d65fefff2c574dab8dbce824cffad/qa/bots-stock-map-audit.json).
- [Spawn-atlas qualification receipt](../../../qa/bots-stock-spawn-atlas-receipt.json): exact code/source hashes, original archive/map hashes, counts and raw-pose crosscheck; no runtime eligibility claim.
- [Behavior evidence and limitations](https://github.com/CodaLilitari/jk-cross-server/blob/260ef1449e8d65fefff2c574dab8dbce824cffad/docs/BOTS_BEHAVIOR.md).
- [Pinned native position/fire synchronization](https://github.com/CodaLilitari/OpenJKDF2-MotS-Fixes/blob/74e4657c4f1751d09af9ad9e056acb8f41997acb/src/Dss/sithDSSThing.c), [spawn selection](https://github.com/CodaLilitari/OpenJKDF2-MotS-Fixes/blob/74e4657c4f1751d09af9ad9e056acb8f41997acb/src/Dss/sithMulti.c), [explosion effects](https://github.com/CodaLilitari/OpenJKDF2-MotS-Fixes/blob/74e4657c4f1751d09af9ad9e056acb8f41997acb/src/World/sithExplosion.c).
- [Current jkweb hit protocol](https://github.com/tristamus/OpenJKDF2/blob/7a6f95c9a3399e59acbf019dc6b25f9981d29dff/src/Platform/Networking/WSRelay/stdComm_WSRelayHits.c), [motion](https://github.com/tristamus/OpenJKDF2/blob/7a6f95c9a3399e59acbf019dc6b25f9981d29dff/src/Platform/Networking/WSRelay/stdComm_WSRelayMotion.c) and [playout](https://github.com/tristamus/OpenJKDF2/blob/7a6f95c9a3399e59acbf019dc6b25f9981d29dff/src/Platform/Networking/WSRelay/stdComm_WSRelayPlayout.h).
- [Demon27248's original multiplayer upload](https://www.youtube.com/watch?v=lW3tQHblhEs): indexed creator chapters identify Canyon Oasis at 0:00, Bespin Mining Station at 9:53 and Blades of Death at 18:55. At this checkpoint only metadata is verified; visual tactics and skill level are not.
