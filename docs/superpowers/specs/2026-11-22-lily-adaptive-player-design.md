# Lily adaptive player: live controller and retained experience

## Intent and authorization

The user approved the architecture reassessment and asked to retain the existing bots while pursuing a more ambitious learning player for Lily, including code changes while she plays. They delegated implementation choices and explicitly accepted starting with the working control foundation. This design is the implementation decision, not another approval request.

The target is consequential tactical agency, learned motor behavior, and new executable skills. A wrapper that repeatedly sends the existing four strategy modes is insufficient. This first complete increment must demonstrate ordinary-input authority, executable policy replacement during one running game, and retained outcome learning. It must expose training/weight experiments without claiming trained competitive strength before evidence exists.

## Decisions and alternatives

1. Keep the game executable stable and run a trusted replaceable Python policy outside it. Add one opt-in native adapter to expose state and apply bounded action sequences on engine control ticks. This supports actual new behavior without rebuilding the engine for each policy edit.
2. Preserve the existing autonomous controller as the default for other seats and as an explicit Lily fallback. Do not attempt binary patching of a running process, unbounded code evaluation in the game, or a new general-purpose browser.
3. Keep privileged engine observations permitted and ordinary player actions mandatory. Physics, speed, damage, inventory, Force costs/ranks and collision remain authoritative stock mechanics.
4. Native route execution and direct motor execution are both useful. Routes provide stable goals; motor sequences permit learned/generated movement and combat behavior to replace old mechanics.
5. Implement the control interface, learning records and policy loader now; evaluate small learned motor policies against it. Direct neural weight edits are an optional experiment against a defined policy, not a substitute for the interface.

## Global constraints

- Existing bots remain autonomous by default; adaptive capability is explicit and restricted to the selected Lily seat by the launcher and hub.
- All movement, view, firing, weapon selection and Force actions pass through ordinary engine input handling. No velocity, position, inventory, health or game-rule injection.
- Rich perception may expose synchronized privileged opponent state; label its scope. Do not silently narrow the previously authorized perception contract.
- Existing JKCP v1 STATE (144-byte payload), strategy/chat/release behavior and existing client compatibility remain intact.
- Keep datagrams at most 512 bytes, validate lengths/types/ranges/finite numbers, and retain run/world/life fencing, authentication and deadlines.
- Native input time follows game control ticks. Record applied duration; do not promise sub-frame button timing.
- Never claim ACK acceptance is skill success. Physical outcomes, interrupted/censored episodes and policy identity remain distinct.
- Code updates come from trusted operator-local files, never game chat or an HTTP code upload. Process isolation is for latency/crash containment, not a security sandbox.
- Do not publish credentials, local personal paths, raw chat, retail game archives, or private experience databases.
- Use the Python standard library for the deployed controller and inference. Optional local training can use already-installed NumPy, with no model download or paid training required.

## Native protocol and execution

Use extension event kinds 5 (offers), 6 (progress/outcome), and 7 (rich state), plus commands 19 (commit route) and 20 (motor sequence). Keep the 20-byte JKCP header and put the absolute deadline at payload byte zero for browser clock translation.

The native implementer owns the exact bounded binary layouts and matching pure-Python codec in `bots/lily/protocol.py`; document them in `docs/LILY_PROTOCOL.md` before other tasks consume them. It must provide `decode_event(kind, payload)` and `encode_command(kind, body, deadline)`, with public constants and validation. Use an explicit native sample ID in state and commands, separate from the web-remapped header event sequence.

Rich state includes source sample ID, physical pose/velocity/orientation, support/medium/breath, control cadence, actual applied axes/buttons, active owner/revision/phase, safe-handover indication, current route target, and bounded peer records. Retain the ordinary state for inventory/health/score. Expose a stable map identity where reliable; require an explicit environment identifier for persistent learning if it is unavailable.

Offers contain bounded, currently feasible node choices with sector/position, class, item bin, path cost and utility. Associate an offer identity with its fence and age. A route commit preserves its cursor and does not invoke the legacy strategy-reset path. Routine equipment/pursuit replanning must not overwrite a committed route; urgent survival and invalidated routes can interrupt with a reason. Arrival is a physical route result, not a promise of item gain.

Motor commands carry a source sample ID, policy revision and at most five relative-duration steps. Each step includes duration, bounded forward/strafe/turn/pitch, a legal button mask, optional weapon selection and optional Force request. Limit the sequence to 600 ms requested duration. The engine applies steps for at least one control tick, records actual timing, and accepts at most one queued successor. Stale observation references, invalid deadlines or fences and disabled capability are rejected.

Motor execution owns ordinary inputs rather than allowing the autonomous branch to overwrite them. Preserve common lifecycle/observation work. Respect existing behavior settings such as Force disabled, sabers-only and fists peace. Admission waits for existing atomic jump/Force/water-exit work to finish; forceful release, death, world replacement or expiry end authority with explicit reasons and ordinary key-release semantics. Consecutive valid chunks may preserve held keys; no unintended second press may be created by transport renewal.

Progress distinguishes accepted/queued, started/running, completed, interrupted, failed and expired, with action sequence, policy revision and source sample. Repeat the latest terminal identity in a bounded way so one dropped event cannot strand the learner. Physical completion is separate from sequence playback completion.

## Companion and browser integration

Add an opt-in `experimental_ids` argument to Hub, default empty, with only the selected `lily` identity enabled in launchers. Capabilities advertise extensions only when enabled. Add authenticated `commit` and `motor` operations and rich observation fields. Keep old request-id behavior unchanged. High-rate motor/commit requests require a separate bounded replay history that can evict terminal records; do not exhaust the legacy 256-command lifetime budget after seconds of play. Never evict pending commands or allow duplicate input execution.

Observation JSON retains existing keys and adds `lily` containing `sense`, `offers`, `progress` and freshness information. The exact codec output names are the shared schema. Browser kind allowlists and deadline translation must support extension traffic only for enabled seats. Do not remap native sample/offer identities as if they were transport event sequences. Browser restart must fence previous commands.

Expose `--adaptive-lily` in the browser arena and native launcher. Native profile support may add Lily while preserving existing default selections. The native path requires its companion enabled. Add CLI commands to inspect offers/progress and submit route/motor JSON through the same authority lease. Do not add a second conflicting controller lease for Astra.

## Replaceable policy supervisor

Create a separate `bots.lily` command that attaches to Lily's scoped companion and owns the active undertaking. A worker policy is trusted local Python with `ABI_VERSION = 1` and `decide(observation, context) -> dict`. Context contains versioned serializable policy state, current undertaking, learned route/skill estimates and an optional operator directive. Output can select a route, issue a bounded motor sequence, continue waiting, or explicitly return to baseline, and may return updated policy state.

Compile exact staged source bytes under a SHA-256 identity. Equal-length/equal-mtime edits must still be detected. Start a candidate worker beside the active worker; apply startup/decision deadlines, bounded JSON and finite-output validation. Do not use in-process importlib.reload. A broken or hanging candidate cannot stop the active controller. Promote at a confirmed action/skill boundary and safe native handover, preserving supervisor-owned experience and compatible state. Retain a known-good revision for rollback. Record stage, rejection, activation and fallback events.

Use one bounded decision in flight per worker, coalesce stale observations, and keep blocking worker IO off the main game-control polling loop. Handle Windows pipes explicitly. On process failure or stale telemetry, stop issuing new actions and allow bounded native fallback. No background work is claimed after the supervisor exits.

Provide trusted local directive input for Astra to choose goals/skills and parameters without directly replacing the worker lease. A directive has an ID/fence and provenance, and renewing the same directive must not reset a committed maneuver. This is operator control, not an automatic hosted-model integration or use of unavailable API credentials.

## Durable learning and motor experiment

Use SQLite to preserve attempts, observed transitions, outcomes, policy/skill identities and conditional route/skill estimates. Deduplicate by run/world/life/action/outcome identity. Interrupted, stale and lost-telemetry episodes are censored, not physical failures. Separate route arrival, item gain, damage and elapsed time. Cross-run route keys use environment identity, sector, quantized position/direction and item/skill class, never an ephemeral node index alone.

The initial policy should make consequential choices among offers using empirical completion/cost estimates and switching cost, retain a selected undertaking, and provide at least one directly executable motor skill. This is measurable retained adaptation; it is not evidence of expert-level policy learning.

Add an optional compact motor-policy training/export path from synchronized applied controls and known successful outcomes. Deployed inference stays standard-library only. Record feature normalization, action contract and model digest. Train/evaluate on separate episode IDs; synthetic unit tests are not gameplay evidence. A weight edit can be evaluated as a separate candidate through the same loader, with regressions tested against known-good cases.

## Acceptance evidence

1. Legacy native/Python/browser regressions remain green, and disabled seats reject extension commands.
2. Protocol malformed, stale, duplicate and timing cases are exercised in native and Python tests, including sustained high-rate operation beyond 256 actions.
3. Worker revision changes behavior on the same running session; invalid/hanging candidate retains prior revision, active action is not reset, and crash/expiry produces bounded fallback.
4. An observed physical outcome updates a route/skill estimate exactly once and affects a later decision after restarting the supervisor; censored attempts do not poison competence.
5. A real-engine trial or stock-physics injected-action replay proves that the new control path applied ordinary inputs; capture policy hash, input receipt and actual result. Report narrow results honestly.
6. A compact trained candidate is exported and evaluated only if real synchronized training data are available; otherwise leave its runnable interface explicit and report the data gap rather than claim learned competence.

Future continuation remains broader: expert demonstrations, richer skills, self-play populations, learned motor/tactical policies and controlled direct-weight edits. This increment should make those executable without another redesign of authority or outcomes.
