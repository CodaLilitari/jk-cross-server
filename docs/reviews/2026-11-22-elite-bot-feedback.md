# Competitive bot review follow-up

This follows three external reviews of PR #1 at `3c223b7`, including observations from the earlier Canyon Oasis recordings. A review observation, a source-level defect, a controlled stock-engine replay and an outcome in a live match are different kinds of evidence. The follow-up keeps those distinctions explicit.

The intended configuration permits privileged game-state perception. Actions still use ordinary player controls, inventory eligibility, Force costs, cooldowns, damage, collision and movement physics. Conditional Seeing remains deliberate: no upkeep cast without Blind or an observed hostile Persuasion effect.

## Changes and evidence

| Finding | Disposition | Evidence and limits |
| --- | --- | --- |
| Guns matches devolve into stationary Bryar or distant saber duels | Improve equipment choice and preserve supply routes through combat | Loaded ranged upgrades take priority, and recognized heavy weapons discourage a voluntary saber duel. Equipment travel continues while the bot aims and fires. Actual stock-control replays test enemies initially off the route bearing, rather than assuming aim and travel agree. A disarmed bot can still have only its saber. |
| Backpacks are not deliberate supply goals | Add dynamic, contents-based backpack goals | A dropped pack is identified by index, GUID, signature and position; it does not become a permanent graph node. A separate stock-handler fixture checks that inventory changes follow the authoritative take/ACK path. A plan trace is not proof that a pack was collected in a match. |
| Little useful secondary fire | Add specific fire-mode decisions | Concussion secondary uses the stock finite first-impact ray and its distinct ammo gate/debit; repeater secondary requires a close spread opportunity. Both planning and firing check the actual first contact. Mode traces record input requests, not successful shots or damage. Sticky rail traps and charged bow release need separate policies. |
| Repeated underwater weapon attempt and reversal at first breath | Add failed-dive memory and a committed return to dry ground | A recorded entry pose was replayed with stock controls, collision, drowning and actual control cadence. Ordinary Speed can make the rail contact feasible; a failed attempt causes an identity-scoped cooldown and another supply choice. Regaining air does not immediately cancel the checked bank approach. This does not prove every shoreline works. |
| Thin shoreline ray accepts a route the player's body cannot traverse | Correct the measured edge-classification defect | The existing graph contained mixed wet/dry links that passed a thin ray but failed a full-body sweep. Dedicated entry/exit motion and representative stock-physics traversal must be checked before such edges are accepted. |
| New world/life events precede the state that introduces their epoch | Publish transition state first | A real tick emitted SOUND before STATE on world entry. State now precedes the associated sound, and death/respawn/world changes schedule immediate publication. Event sequence numbers remain continuous. Lossy transport can still lose packets. |
| Cancelled Pull skips per-opponent retry | Track cancellation against the attempted identity and weapon | A failed marker/visibility check could clear the held power without entering the normal retry delay. A bounded retry must not suppress a different opponent, a changed weapon or a replacement player identity. An unchanged gun is not labelled Absorb. |
| Windows companion credentials cannot pass their own CLI checks | Fix fresh directory permissions at creation | The production host creates private directories before writing credentials. An actual Windows integration test reads all credential depths and a lease with the unchanged CLI validator, and rejects a synthetic file made readable to another principal. |
| Crashed recording leaves its handle and slot occupied | Add a capture watchdog and restart handling | Ten seconds without chunks closes the partial capture; a new browser instance also releases it. Late chunks and finish requests cannot alter a replacement capture. The incomplete file is retained for inspection. |

Detailed receipts accompany the changes in `qa/`; they identify the exact source and runtime tested. Private owned game assets and raw external reviews are not part of the repository.

## Follow-up on the four-minute trial

The second refinement candidate showed active equipment planning, ammunition gains and alternate-fire
requests. It also left two bots climbing and sinking near the same bank. Boba spent 54.087 seconds
within a horizontal radius of 0.13 world units. Lily spent 10.072 seconds in a similarly confined
area at the end. A stock replay reproduced a missed launch at two of six sampled poses. Those poses
isolate a landing-prediction issue. The live trace also showed fresh underwater supply plans and
lacked floor-attachment telemetry. The [match summary](../BOTS_BEHAVIOR.md#four-minute-canyon-oasis-equipment-trial)
identifies which evidence came from the recording.

Three source corrections passed independent driver checks after the trial. Stock contact with a
planned supply can trigger an immediate return to air despite a delayed host response. Separate
failed dives retain their own retry deadlines. A dropped pack is reachable through a single
intermediate node when both legs are traversable. The [regression receipt](../../qa/bots-supply-recovery.json)
records the original failures, the final fixture results and the browser-source chat harness limitation.

The bank predictor now permits the last 0.16 world units of a checked walk after supported touchdown.
Both formerly failing poses reached sustained dry support at all four tested headings. All 19
previously successful cases still reached their intended sector. At 79 ms, one control took
4.367 seconds longer with the same final health. The [normal-dispatch bank replays](../../qa/bots-bank-landing.json)
measure the source correction with a single swimmer and a constant control interval.

## Repeated dives for different supplies

The third recording showed an armed swimmer cycling among different racks after the individual
item cooldowns worked. A stock graph check from the sampled bank found that all three rack routes
used the same first water crossing. A design that blocked the crossing for every goal reduced
reachable anchors from 483 to 13 and was rejected before packaging. The revised source restricts
only optional submerged destinations for a healthy, well-armed bot after a verified failed dive.
A far-bank pickup or an opponent can still justify that crossing through successive equipment
rescans. The 27 bank replay outcomes stayed identical. The recorded multiplayer failure belongs
to the preceding build. [Source checks and limits](../../qa/bots-supply-approach-retry.json)

In candidate 4, Boba and Jan also crossed the failed entrance for guns located on dry ground.
Boba was at full health and shields with 88 cells and a concussion rifle. The accepted candidate-5
source gives an optional dry upgrade the same route restriction as a submerged supply. Needed
ammunition, defensive recovery and pursuit retain the complete graph. In the dispatcher fixture
the stocked bot changed its movement from inward slide toward a dry railgun to patrol along the
bank. All 483 reachable anchors remained available. A crossing can still be the only way to
explore onward, without a weapon bonus deciding the route. These checks cover decisions and
inputs. The separate bank-escape replays retained all 27 prior outcomes. Four-player movement
remains to be measured. [Dry supply detour tests](../../qa/bots-dry-supply-detour.json)

## Stock mechanics that change the recommendations

The owned stock pickup handlers distinguish touch denial from positioning or item Pull:

| Item | Stock touch eligibility | Consequence for denial |
| --- | --- | --- |
| Concussion rifle | Weapon missing, or power cells below 500 | A player who already owns it with 500 cells cannot remove it by touching it. |
| Shield recharge and vest | Shields below 200 | At 199 either can be taken; at 200 neither can. |
| Bacta pickup | Fewer than five carried | Full Bacta inventory cannot touch-deny another. Using Bacta requires health below 100, heals 30 and consumes one. Emergency healing should not be delayed solely to find cover. |
| Light surge | Alignment at least zero | Same-side refresh is eligible even while already active; opposite-side touch is not. |
| Dark surge | Negative alignment | Same-side refresh is eligible even while already active; opposite-side touch is not. |

The surge handlers refill mana according to rank and start or refresh a 20-second effect. Low mana and verified reachability should influence the goal value. Raising a goal's score does not repair a missing route: the checked Canyon graph has a light-surge anchoring gap and a dark-surge reachability gap from the audited origin.

Stock item Pull has a distinct code path that may permit moving or denying an item even when touch eligibility fails. It is a candidate for separate validation, not an implemented denial strategy. It needs item-target identity, ordinary press/release, and two-client evidence distinguishing marking, taking, moving, despawning and respawning. The current offensive targeting code validates player victims.

Stock Grip's broad candidate enumeration is followed by a victim distance limit of **1.0 world unit**. The driver's close-range initiation and release checks follow that limit. Holding the key acquires a marker; the actual Grip starts on release. An established Grip already permits ordinary weapon fire and Bacta. The targeting hold's opportunity cost is a separate policy issue.

Rapidly tapping the dedicated Grip binding does not accelerate that ordinary channel: reselecting the power cancels it. At rank four, an intact stock channel requests an immediate hit, another after about 0.10 game seconds, then one every 0.50 seconds, for ten requests of eight raw magic damage over 4.1 seconds. Protection and Absorb affect the received result. The generic selected-power binding follows a different re-entry path; source inspection supports the historical binding-dependent Supergrip report, including another mana debit and front-loaded damage. There is no matched two-client damage-rate benchmark for that path in this build, and it is not enabled by this follow-up.

Max-rank Pull's 2.5-unit range is not inside concussion primary's 0.8-unit explosion radius. Sampled footage with no visible Pull messages cannot establish an optimal cast rate for stock full-Force play. Likewise, `kyle.cog` does not treat six offensive powers as one blanket immunity: Absorb vetoes disarm and mitigates damage carrying the magic bit; Seeing blocks Blind; Protection blocks Grip control. The disarm veto itself does not award mana, and damage absorption does not by itself remove Grip control.

### Tactical decisions to verify in stock play

- **Respond to Grip.** The victim’s `kyle.cog` handles skill bin 31. Protection gates immobilization, while Absorb mitigates incoming magic damage. Even full damage absorption can leave the victim immobilized. Lily’s competitive dark build has no Absorb. In a paired-client test, record the victim’s skill event, caster identity, actual control flag and health/shield/mana changes alongside the caster’s channel. Chat and a generic damage flash cannot establish the effect. Compare loss of sight and damage to the caster’s health, both of which the active `force_grip.cog` checks.
- **Choose the mode by impact.** On stock Canyon Oasis the concussion primary has a 0.8-unit blast radius. Its secondary is a five-unit first-hit beam without splash. Both require eight power cells to activate and spend eight or four respectively. A blanket two-unit prohibition would discard legal beam shots. Rail primary can also injure the shooter within its 0.5-unit blast radius. Test each mode’s predicted first impact against walls, doors and moving players using the loaded templates. See `weap_concrifle.cog`, `weap_raildet.cog` and `jkBotCombat.inc`.
- **Start the supply run before empty.** Estimate shots remaining at the expected pickup time from current fire mode, travel time and usable backup weapons. Compare inventory actually gained, combat time lost and exposure en route. The existing four-shot thresholds and replicated pack contents supply inputs for this test. [Equipment routing](../../qa/bots-equipment-routing.json)
- **Protect teammates from displacement as well as health loss.** Team flags can suppress health damage while an explosion still applies impulse. For an attempted rescue, require an observed caster and test an ally near a ledge. Record team flags, ally displacement and health separately. See `sithExplosion.c`, `sithActor.c` and `sithPlayer.c`.
- **Test corner fire and explosive traversal separately.** A proposed corner shot needs a recent sighting or eligible sound cue, a plausible first impact and a clear path around allies. Let the prediction expire and include trials without a cue. For a recoil- or blast-assisted jump, use stock-physics replays over multiple starting poses and compare landing, remaining health/shields/ammo and travel time with an ordinary crossing. The existing combat hop withholds heavy fire during committed flight. [Competitive bot design](../superpowers/specs/2026-11-21-competitive-bots-design.md) · [Combat jump tests](../../qa/bots-combat-jump.json)

## Strategic work still required

The reviews correctly identify a larger gap between reactive combat and elite map control. This follow-up does not claim to close it.

1. **Arrival time and respawn control.** Prefer the stock replicated item timer over the time a scoring pass first noticed an item missing. Client timers reaching zero do not prove the host has respawned an item. Current weighted graph costs combine distance and movement/survival penalties; they are not seconds. An ETA needs separate estimates for travel, staging, water and charged jumps.
2. **Legal denial and surge routes.** Consider pickups the bot can actually take, the opponent's evidenced need and the route's opportunity cost. Refresh an eligible own-side surge when worthwhile. Validate item Pull and positional contests separately. Do not fabricate remote inventory or mana that the current wire state does not reliably expose.
3. **Autonomous disengagement.** Add a bounded recovery decision using health, shields, mana, usable ammunition, threat and route safety, with hysteresis. Existing companion `recover` and equipment routes do not constitute a complete autonomous retreat policy.
4. **Opponent and projectile prediction.** Better vertical trajectories, likely landing points, conc pressure, multiple opponents and spawn/exit interception need replayable outcome tests. Hearing a projectile-related event does not automatically provide a usable time to impact. A candidate spawn is not the actual next spawn until the stock selection and occupancy rules support that conclusion.
5. **Combat Force opportunity cost.** Compare a new Pull/Grip targeting hold against an already validated gunshot. Preserve the distinction between targeting failure, an unchanged outcome, known protection and actual absorption. Do not infer exact health/shield changes from absent or stale remote data.

The moving combat-jump increment is deliberately narrow: a checked short stock Jump over a suitable dry, supported route while facing concussion pressure. Heavy-gun recoil changes the flight, so this version does not select or fire concussion/rail during that committed hop. The controlled splash comparison is not a live dodge rate or proof of the requested jump-and-concussion maneuver.

## Companion and host architecture

The fixed event-order defect preserves v1. It does not reset sequence numbers on every life, invent an engine acknowledgment in JavaScript, or remove epoch/identity checks. A browser-side pre-delivery failure should eventually have its own attributed result. Calling it a native `expired` acknowledgment would incorrectly claim the engine inspected the request. A dispatched request without a native reply can remain `unconfirmed` until its bounded deadline.

The hub already pumps during a browser frame exchange. CLI acknowledgment polling happens after submission, so it is not another delay before the engine receives the command. Five-Hz observations create phase-dependent age; a universal 300–450 ms latency or frequent stale-focus rate requires measurement. Focus validation intentionally rejects a target that is no longer current.

Sector, attachment, water, endurance, recovery and Force outcomes would be useful diagnostics. They need named, bounded, versioned fields with an identified truth source. A visible-peer list and a 10–20 Hz stream should follow measured need and overhead. Programmable high-level strategy can remain external while the engine continues its ordinary per-frame controls.

A declarative policy profile with strict validation, replay and last-valid fallback is a sensible next interface. An AST/import/builtin allowlist is not a security sandbox for arbitrary Python. Such scripts should be explicitly trusted or isolated with actual operating-system and resource controls, separate credentials, and validated brokered outputs. Replay and watchdogs help correctness; they do not make code isolation unnecessary.

The host lock surrounds bounded nonblocking datagram work and in-memory request handling; HTTP body reads and response writes occur outside it. The lock-contention hypothesis merits measurement before a threading redesign. Relay TCP/HTTP upgrade is now bounded without imposing a match-duration timeout on an established WebSocket.

## Build portability

The reviewed nested navigation stack allocations are about 209 KiB. The shipped WASM link uses a 100 MiB stack and 200 MiB initial memory with growth, so the cited 64 KiB default is not the configuration being distributed. Smaller-stack ports may still need a redesign. Moving nested calculations into one shared static workspace can introduce aliasing; either reuse already-computed distances or provide distinct scratch ownership.

`COG_CRC32_SYMBOL_NAMES` is a real portability concern for string-based victim/reference lookup. It is enabled for the retro-homebrew configuration, not the shipped web or native builds. Supporting that target should cover both Force victims and CTF references with the engine's existing CRC lookup convention and its own build tests.

The web source remains pinned to the audited JKWeb gameplay/network revision. The subsequent upstream commits checked on 2026-11-22 add optional HD menu assets and credits; they do not change the gameplay or relay code used by this qualification. Build manifests identify the pin instead of claiming an untested upstream HEAD.
