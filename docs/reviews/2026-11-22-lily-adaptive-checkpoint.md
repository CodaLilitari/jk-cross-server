# Adaptive Lily development checkpoint

This records the initial adapter checkpoint. The later
[bank-task checkpoint](2026-11-22-lily-bank-checkpoint.md) documents the new task
semantics, additional tests and first matched physical score for the movement
candidate. Historical counts and scope below describe the earlier implementation.

This checkpoint is approved for the development draft in
[PR #2](https://github.com/CodaLilitari/jk-cross-server/pull/2), stacked on
`feature/competitive-bot-foundation`. The preserved baseline remains at
`04d482ea760f0604c5fb9e66a6c5f854b1d4385a`. The independently reviewed implementation
is `4e75abfa3ed1e31b5d6bbad10b28343314a10408`; later checkpoint documentation and
release-integrity updates do not change its engine or controller behavior.

## Implemented and verified

- Native route and motor authority is explicitly enabled for Lily. Movement,
  view, weapon and Force requests use ordinary player input handling.
- The companion preserves run/world/life identities, scoped authentication,
  deadlines, high-rate request receipts and terminal outcomes.
- Policy source is staged in a separate process and replaced at a safe action
  boundary. Broken candidates leave the active worker available. Exit and
  failure paths return bounded control to the autonomous baseline.
- SQLite journals intended submissions before dispatch, reconciles uncertain
  receipts and retains deduplicated physical outcomes separately from censored
  attempts. A rejected command does not advance action-dependent policy state.
- Training joins native attempt, observation and outcome identities and uses a
  consistent fixed-target geometry. Export from the checked-in model produces
  the checked-in executable policy byte for byte.

The final whole-branch review found no outstanding critical or important issue.
It checked native controls, browser transport, live policy and journal lifecycles,
learning attribution, package inventories and documentation scope.

## Evidence and its limits

| Check | Result and scope |
| --- | --- |
| Full Python suite | 279 tests, no failures, three environment-specific skips (109.867 seconds). |
| Focused final Lily suite | 41 tests passed after the learning and attribution fixes. |
| Browser JavaScript client | All four arena modes passed boot, scoped MEMFS, frame transfer and clock/deadline checks. |
| Native adapter regressions | 56 driver cases, companion control/lifecycle fixture and a 300-action stream passed; all six native runners passed during implementation. |
| Disabled-capability physical baseline | All 27 case/yaw combinations matched historical landing time to the published millisecond, landing health and sector. This is equivalence for that matrix. |
| Live stock-physics integration | The third 30-second probe passed seven checks, including two executable revisions applying inputs, invalid-candidate rejection, supported landing and baseline return after shutdown. |
| Retained physical experience | Identical fresh workers at the same recorded pose chose a sidestep with an empty database and forward movement with restored 3/3 physical successes. The later decision comparison was offline, validated before dispatch. |
| Neural movement experiment | 4,306 physical demonstration frames; held-out whole-pose axis MSE 0.18565. The candidate is unpromoted and has no closed-loop or multiplayer score. |
| Package correspondence | Native and browser supplied-object relinks reproduced the shipped executable, JavaScript and WASM byte for byte. Independently recompiling a third-party dependency linked successfully but produced different bytes, recorded separately. |

The [physical receipt](../../qa/lily-adaptive-live.json) retains the earlier
unsuccessful unrestricted motor probe. Its short displacement successes did not
produce a bank escape. This remains useful evidence about the difference between
local physical progress and completing an undertaking.

The [build receipt](../../qa/lily-adaptive-build.json) records exact source and
artifact identities. No new rendered multiplayer qualification, human-opponent
result, learned combat policy or competitive improvement is claimed. The physical
fixture excludes opponents, rendering and inventory/Force COG execution.

## Implementation choices

The engine has one opt-in adapter; executable policy development happens in a
separate trusted local process. This makes code and weight experiments possible
without rebuilding the engine for each revision, while adding a process/transport
boundary whose timing is measured rather than assumed.

Policy promotion waits for a safe handover. That can delay a new revision during
a jump, Force action or traversal transition, preserving the action already in
progress. The ordinary bots remain the fallback and comparison group.

The first network is a small movement-cloning experiment. Its reproducible weights
and honest evaluation give subsequent experiments a concrete starting point.
Promoting it before task-level physical comparisons would risk replacing a usable
controller with a worse one, so it remains opt-in.

## Deferred minor and continuation

One native regression uses a 50 ms wall-clock admission deadline. A heavily paused
test runner could fail before reaching its completion assertion. A controlled test
clock would remove this flake risk; it does not change the tested runtime behavior.

Continue with complete task outcomes, richer physical context and closed-loop
candidate evaluation. Water escape, forward shaft traversal and useful item
acquisition need separate outcomes. Longer-term work includes learned combat,
opponent-conditioned tactics and self-play. Use [the controller guide](../LILY_ADAPTIVE.md)
and [motor experiment](../LILY_MOTOR_LEARNING.md) for the current interfaces.
