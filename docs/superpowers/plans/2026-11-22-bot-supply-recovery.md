# Bot supply recovery continuation

## Goal

Finish the reviewed equipment and underwater recovery increment, then qualify its exact browser build in a private four-player, four-minute Canyon Oasis recording. This is an increment toward the existing competitive-bot specification, not a claim of elite human performance.

Spec: `docs/superpowers/specs/2026-11-21-competitive-bots-design.md`. Review dispositions and larger strategic work are in `docs/reviews/2026-11-22-elite-bot-feedback.md`.

## Global constraints

- Actions use ordinary player controls and stock inventory, collision, costs, damage and physics.
- Keep equivalent bot behavior in the native and browser source patches.
- Match item slot, GUID and signature. Clear transient state on world/life reset; a replacement item must not inherit another identity's outcome.
- Physical contact, an input request and a confirmed inventory grant remain distinct evidence.
- Do not include retail assets, private credentials, raw private reviews or personal machine paths in the public repository. Compiler-generated build paths may remain in executable or relink inputs; do not claim that packaged binaries are path-free.
- Preserve the completed candidate-2 recording as earlier evidence. A later build needs its own hash-qualified recording.

## Task 1: Repair reviewed equipment recovery edge cases

Own the bot source changes in `src/AI/jkBot.c`, `src/AI/jkBotNavigation.inc` and a narrowly justified item-contact hook if required, in both source trees. Own the corresponding native test additions. Do not change build manifests, packaged binaries, release metadata or unrelated behavior; the coordinating agent integrates those after review.

- [x] Reproduce the delayed-ACK defect: after at least 4000 ms of underwater endurance, measured contact with the currently planned underwater supply must cause the intended return to air even when a host acknowledgment is delayed or a nonrespawning drop is destroyed. Do not credit a pickup merely from proximity. If a contact hook is required, use the ordinary stock touch path before the identity disappears, rather than manufacturing an inventory event. Preserve identity and reset guards.
- [x] Reproduce A-fails, B-fails, A-again: remember independent failed underwater supply identities for the existing 45-second backoff. Use bounded state with an explicit conservative saturation policy, so storage pressure cannot silently make an unexpired failed identity immediately eligible. Expired entries and different replacement identities may be reconsidered normally.
- [x] Reproduce the sparse-graph dropped-pack route: a valid nearest anchor must be considered when the direct leg exceeds the existing 2.0-unit span limit. A player 1.2 units before the only anchor and a pack 1.2 units beyond it must be able to use the two checked legs. Keep initial approach and final-span collision/support checks.
- [x] Run each regression before its fix and retain the expected failure. Apply minimal corrections and run the affected full native driver, portal and companion/hearing groups on both relevant source configurations as needed.
- [x] Self-review and provide a small candidate-2-to-candidate-3 source/test diff plus test commands and outcomes for scoped review. Preserve all unrelated candidate-2 work.

## Task 2: Repair the reproduced bank landing timing failure

Own only the equivalent `src/AI/jkBotWaterExit.inc` change in both engine trees, focused water-landing regression coverage, and a reproducible replay case manifest. Preserve Task 1 changes. The frozen candidate-2 replay demonstrated supported stock landings that the predictor rejected solely because the final checked walk to the bank anchor exceeded 0.14 units.

- [x] Reproduce the failing 74 ms and 87 ms Boba poses before changing production source. Retain the failure and exact input arguments.
- [x] Test the narrow proposed 0.16-unit allowance for the supported post-touchdown walk. Retain every full-body flight sweep, actual sector/support check, floor/rim proof, no-drop walk, lateral-speed and takeoff condition. Do not alter stock physics or increase recovery timers to hide the failure.
- [x] Require normal-dispatch stock-physics success from both failing poses at yaw offsets -90, 0, 90 and 180 degrees, with at least 38 consecutive dry floor-attachment steps. Preserve the four successful candidate-2 poses and the three prior sector 42-to-10 pool cases.
- [x] Exercise blocked rim, unsafe floor, obstructed body sweep, unsupported touchdown and non-walkable final segment rejection. Add focused coverage for the extended final walk and its bounded maximum where existing fixtures do not cover it.
- [x] Provide a focused before/after diff, replay matrix, test outcomes, and remaining limitations for independent scoped review. Do not include owned map geometry or machine paths in public evidence.

## Task 3: Integrate and qualify the corrected increment

The coordinating agent owns packaging and publication.

- [x] Resolve the Task 1 and Task 2 reviews, refresh native/browser patches and rebuild the affected runtimes with verified source/build identities.
- [x] Install the exact candidate on the private Windows test setup, verify hashes, and record 240 seconds after all four accelerated clients qualify. Verify actual red saber side/tip materials.
- [x] Inspect full telemetry and representative video frames. Report water behavior, equipment selection and fire-mode evidence with their sampling and attribution limits; preserve any failure observed.
- [ ] Refresh release metadata, verify the package, commit and push the authorized existing draft PR branch. Preserve draft status and record unfinished strategy work.
- [ ] Save and deliver the validated gameplay recording, with a concise continuation checkpoint in the repository.

## Task 4: Stop the reproduced cycle through failed water supply routes

The candidate-3 live trial established a policy failure after the physical exit fixes: a loaded, healthy bot repeatedly left the pool, selected another supply goal, and returned through the same water lane. Different identities became eligible after their independent 45-second cooldowns. Preserve the accepted contact, identity and physical landing fixes.

- [x] Reproduce the choice with ordinary dispatcher/route fixtures: at least two different supply identities reached through the same failed water entry, a stocked ranged weapon, and a viable dry route or pursuit. Show the failed-before-fix decision instead of weakening the pickup cooldown assertions.
- [x] Add a bounded cost or retry deterrent for the actually failed water approach, or a comparably narrow evidence-backed equipment opportunity-cost correction. Different item identities must not immediately erase an expensive failed approach. Prefer a viable dry alternative while retaining emergency supply acquisition, ordinary underwater escape and eventual reconsideration.
- [x] Apply the decision consistently to dedicated equipment routing and ordinary route planning so the fallback cannot reintroduce the same loop. Do not globally disable water, fake pickups, change physics, or hardcode Canyon Oasis sectors.
- [x] Verify reset/expiry and unrelated pools or routes, preserve useful dry pickups while fighting, preserve disarmed/empty-weapon recovery, and test all affected native/browser driver and navigation configurations. Retain meaningful failure evidence.
- [x] Provide a focused before/after diff, exact regression results and scoped implementation report for independent review. Root owns packaging, private PC installation and a new full recording after review.

## Task 5: Rebuild and qualify the route-policy correction

- [x] Resolve Task 4 review and rebuild/hash-verify both runtime packages and release metadata.
- [x] Install privately, record another autonomous four-seat 240-second trial, verify red saber and game audio, and compare equipment progress and prolonged confinement with both earlier candidates. The capture passed; Boba and Jan exposed repeated optional dry-equipment trips through the failed water entrance.
- [x] Preserve failed live evidence, save the fourth recording, and record an accurate continuation checkpoint. Publication of the new payload is pending.


## Task 6: Distinguish optional dry upgrades from necessary water transit

The fourth candidate recorded failed-approach memory, but a healthy bot with 88 concussion cells still revisited that approach for an extra railgun or repeater on dry ground. Destination wetness alone does not describe the cost of reaching it.

- [x] Reproduce the actual dry-upgrade choice before changing production source. Include a productive alternative, cached equipment goal, fallback planning and an underwater rescan.
- [x] Prefer the productive alternative for nonessential equipment while retaining the ordinary transit graph, needed recovery, explicit opponent pursuit and distinct entries. Inspect physical controls and movement ownership.
- [x] Preserve the affected driver, portal, hearing, loadout and bank replay cases on both source configurations; obtain independent review of the scoped correction.
- [x] Rebuild and verify the exact native/browser packages, privately record a fresh four-seat 240-second match, and inspect all seats before qualifying movement. Candidate 5 passed capture checks and failed broad sustained-movement qualification; its specific optional dry-weapon recurrence was not observed in the available cooldown windows.
- [x] Preserve every failed trial, deliver the validated fifth recording and update the continuation checkpoint and release metadata. Publication remains pending.


## Next increment: Validate forward water transit and useful recovery

- [x] Distinguish the bot's eight-second air priority from the engine's twenty-second first drowning threshold. Check near-vertical forward-swim control and preserve the existing bank-escape evidence. No production changes are included from this investigation.
- [ ] Add an ordinary-input, stock-collision replay of the observed forward passage. Measure actual wet-to-wet crossing, next breath, health loss and final stock pickup, using realistic control intervals and headings.
- [ ] Isolate steering and breathing-budget candidates. Require a supported escape margin and meaningful progress; a longer deadline alone is not evidence of a safe route.
- [ ] Compare time to actual shield or health recovery against an alternative destination, with urgent, low-ammunition and no-alternative controls. Preserve autonomous combat and valid objectives.
