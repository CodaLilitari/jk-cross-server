# Lily bank escape under stock physics

## Intent and decision

Can Lily sustain one attempt to reach a particular bank, and does the unpromoted movement clone help her get there? The first unrestricted physical probe recorded 37 local movement successes without a supported landing. Existing SQLite estimates and fixed motor endpoints answer questions about individual commands. A player can execute many such commands during one unsuccessful escape.

Implementation choices were delegated. The engineering choice here is a single bank-escape task shared by an opt-in live directive and an evaluator. A replay-only scoreboard would leave the live policy free to change goals after each stride. Inferring a complete escape from current live telemetry would ascribe sector and floor information the protocol does not publish. The selected design pairs live target commitment with the existing exact replay oracle. It does not require new engine observations, model training, or changes to the shipped native or web engines. Acquisition and combat need their own future evidence.

## Global constraints

- Keep the baseline autonomous and Lily opt-in. Retain the existing learned-motor directive and model weights.
- Use ordinary player inputs, stock physics, existing atomic handover, and the Python standard library for deployed code.
- Keep motor evidence and bank-task evidence in separate records. Each task has one terminal per evidence source.
- Publish only sanitized receipts, provenance, and aggregate or case-level measurements. Keep retail assets, private traces and credentials out of git.

## One commitment

An operator issues the existing scoped directive with goal `escape-bank`, a unique ID, and parameters `position` (three finite world coordinates), `sector` (nonnegative signed-32-bit integer), and optional `budget_seconds` (finite 1 through 60, default 60). Validate types strictly, including rejection of booleans masquerading as numbers. Enforce the existing learned-policy reach limit of 100 game units at entry. The live task requires a fresh wet starting observation. A journaled task stores environment, run/world/life fence, directive ID, initial pose, immutable target and budget, active policy digest, and start sample. A policy can choose different inputs each time it has a safe opportunity. All accepted commands within the task link to this same identity. A prepared or rejected submission alone proves neither application nor takeover.

Use one bank attempt per (environment, run, world, life, directive ID). Renewing the same ID can extend its operator deadline. It cannot retarget, reopen a completed task, or substitute a new worker. Require a new ID for another bank attempt, including a retry at the same coordinates. Existing directive semantics for other goals are unaffected. A terminal latch survives process restart. A process that regains exclusive control censors any interrupted open task once as `restarted`; it never reconstructs missing control ticks or reissues a command to fill a gap. Honor preexisting journal recovery and fencing.

Hold the worker revision and task target across child command boundaries. The supervisor can stage and probe an update. It activates the update at a safe native boundary after task closure. A normal command interruption need not end the task if the same worker still owns it and meaningful control can resume. Fault, stale telemetry, lease loss or explicit release censors the task and permits immediate baseline fallback. A superseding operator directive closes the old task before the next goal acts. A matching fence change closes the old scope independently of what the next life reports. All previously valid non-task policies remain usable.

Observe the finite in-fence stock game clock for elapsed simulation time; repeated values add no time. Because stock state and rich sense publish at different cadences, anchor the budget and dry-support dwell on a new stock-clock publication after assignment or the first qualifying observation, respectively. On a missing or regressing clock within a task, withhold timeout proof. An operator expiry or watchdog still closes control safely. Reaching the live budget closes as `budget_elapsed` with no exact physical verdict. An optional conservative stop may recognize a fresh series of supported/air samples near the fixed endpoint that spans at least 0.25 simulated seconds. Disallow duplicate-sample accumulation and reset on a gap over 0.25 seconds, support loss, or water. Record this as `sampled_dry`, with null physical verdict. Define and document any nearness radius before use. Live samples omit own sector, surface identity, and the intervening 150 Hz physics steps.

## Shared result contract

Runtime/ledger owners provide one pure Python interface in `bots/lily/bank_task.py`. The evaluator imports it. This is the complete cross-lane dependency.

```python
bank_verdict(*, terminal: str, controller: str, wet_takeover: bool,
             baseline_assisted: bool, ownership_complete: bool) -> dict
```

The returned keys are `terminal`, `physical_success` (bool or null), `attribution` and `controller_success` (bool or null). Reject unknown terminal/controller and non-boolean flag values. Both live traces and replay receipts carry the evidence source and identity alongside that result.

| Terminal | Physical success | Evidence |
| --- | --- | --- |
| supported_dry | true | Native replay observes 38 consecutive 150 Hz physics steps attached to a floor in the requested dry sector. |
| died, sim_timeout | false | Native replay observes actor death before landing or full requested simulated budget without landing. |
| sampled_dry, budget_elapsed | null | Live sampled support or live game-clock budget end. |
| control_lost, fence_changed, directive_ended, restarted, unavailable, invalid_evidence | null | Loss, cancellation, missing authority, unusable trial, or invalid oracle data. Capture a reason separately. |

Attribution uses ordered rules. Incomplete tick ownership gives `unknown`. A complete baseline arm gives `baseline`. A candidate arm with no actual applied motor control from the assigned revision while wet gives `no_wet_takeover`. An eligible candidate run with any baseline-driven control tick from assignment through physical terminal gives `assisted`. Remaining complete, wet-owned candidate cases give `candidate`. Neutral control boundary ticks are recorded separately; absence of a rich sense packet does not establish neutral control. Only `baseline` and `candidate` inherit physical success as controller success. Physical and controller results can therefore differ on both wins and losses. Operational fallback before a later rescue closes the live task with null physical success; an independently identified replay evaluation may still report the eventual landing and the ownership history. Keep each source's result immutable.

## Matched evaluation

Use the stock water replay's nine captured starts and 27 case/yaw combinations. Compare each unchanged baseline run with a candidate assigned the exact exported water_bc_v1 policy, target bank and unchanged geometry/control interval. Use the existing 550 ms inference duration unless a different duration is explicitly measured and labeled separately. Start tracking control from the common assigned initial state. Record actual native control application and revision on physics-driving control frames. In particular, a safe handover sample, lease receipt, playback terminal, or model inference alone cannot establish wet takeover. Preserve atomic water exits even if they prevent the candidate from participating. If an isolated synchronous candidate harness is used, label the execution path precisely and verify the same stock input and handover rules; a bypass is a different experiment.

The authoritative landing predicate already lives in `native/tests/stock_water_replay/replay_loop.inc`. Emit one independent typed physical terminal with elapsed simulation time, sector and HP. Include time to first breath if observed, counts for baseline/candidate/neutral/unknown control ticks, candidate wet takeover, and case/seed and provenance digests. `replay_trace.inc` currently hardcodes baseline identity in imitation rows. Keep baseline-only demonstration records isolated from adaptive measurements. A wrapper timeout, rejected start, missing native terminal, or process error is censored. Retain every assigned row even if the client never starts, and present assigned and attribution-eligible denominators. Report prior model holdouts separately (four headings of lily-232.797 and pool-100 at yaw zero). Preserve failures; an evaluation can be complete even when the candidate loses. This fixture has no design claim about contested supplies, combat, human strength, or multiplayer.
