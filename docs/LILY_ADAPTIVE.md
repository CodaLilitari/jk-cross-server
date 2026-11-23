# Running the adaptive Lily controller

Start an adaptive-enabled Lily seat with its companion. The supervisor uses the scoped local `lily.json` for that run. It acquires the existing companion lease when the first action is ready. The other bots keep their normal controllers.

The [motor learning experiment](LILY_MOTOR_LEARNING.md) includes training, model
export and measured stock-physics evidence. Its first neural candidate is available
for explicit experiments and is not the default policy.

## Start, stage and roll back

Keep a writable copy of the initial policy and a backup of a known-good revision. These examples use a local work directory for the operator's policy, trace and experience.

```sh
cp bots/lily/policies/adaptive.py live_policy.py
cp live_policy.py previous_policy.py
python -m bots.lily --credentials RUN/companion/lily.json --policy live_policy.py --memory experience.sqlite3 --environment-id level-content-v1-stock-rules --directive-file directive.json --trace session.jsonl --duration-seconds 300
```

From another shell, stage a trusted local candidate by replacing the watched file. The following commands work with Python on Windows and POSIX. Use the second command to restore the saved revision.

```sh
python -c "from pathlib import Path; p=Path('live_policy.stage'); p.write_bytes(Path('candidate.py').read_bytes()); p.replace('live_policy.py')"
python -c "from pathlib import Path; p=Path('live_policy.stage'); p.write_bytes(Path('previous_policy.py').read_bytes()); p.replace('live_policy.py')"
```

The supervisor hashes file contents about every 300 ms. The child checks the SHA-256 digest and compiles those exact bytes. Keep changing configuration, code and model weights inside that source to give each revision a reproducible identity. Imports from the repository and standard library are available. Changes to an imported dependency alone do not trigger replacement.

A candidate starts next to the active worker. It must import within two seconds and answer a probe within 180 ms by default. A dedicated reader/writer thread for each child handles bounded binary stdio pipes on POSIX and Windows. The main polling loop never blocks on worker input or output. Each child has at most one outstanding decision. The probe plans a hypothetical next undertaking and never issues a game command. Candidate import and decision failures leave the active worker running.

A valid candidate takes over when the supervisor has cleared the last undertaking and sees a safe native handover. It makes a fresh decision on activation. The policy can run new ordinary-input motor code during the same match. An active-worker crash censors the open attempt, requests release, and stages the preceding revision when one exists. After a rollback, replacing the watched file with different bytes stages another candidate. With no usable worker, the native baseline takes control. Loss of observations, the bounded command deadline and lease expiry also limit authority. A normal exit requests release and kills the child workers.

## Executable ABI

An ABI-1 policy is trusted executable Python. The child provides failure and latency isolation. A trusted policy has the local operating-system access of its user. Only an operator-local file is loaded.

```python
ABI_VERSION = 1
STATE_VERSION = 1

def decide(observation, context):
    if context["undertaking"]:
        return {"action": "wait"}
    facing = observation["lily"]["sense"]["facing"]
    return {
        "action": "motor",
        "skill": "forward-probe",
        "goal": {"direction": facing, "distance": 0.04},
        "steps": [{"duration_ms": 240, "forward": 0.9},
                  {"duration_ms": 140, "forward": 0.4}],
    }
```

Observation contains the run/world/life fence, stock state, freshness and `lily.sense`, `lily.offers`, `lily.progress` and the bounded `lily.terminals` history. Expired offers are removed. Motor and route bodies use the field names and input bounds in [the protocol specification](LILY_PROTOCOL.md).

| Context field | Meaning |
| --- | --- |
| `abi_version`, `state_version`, `state` | Supervisor ABI, worker-declared schema, and last accepted bounded JSON object. Two revisions can explicitly share a positive integer `STATE_VERSION`. State resets on an incompatible version or new life. |
| `undertaking` | Null when available, otherwise the episode ID, native action sequence, skill and physical goal. The supervisor owns its lifetime. |
| `bank_task` | Null, or the durable bank task ID, `active`/`closed` status, fixed world position, target sector and simulation budget. It spans multiple native actions. |
| `directive` | A fresh operator-local directive for this exact run, world and life, or null. |
| `routes` | Estimates for current choices, keyed by the ephemeral node rendered as a string. Durable evidence is keyed by geometry. |
| `skills` | Conditional estimates for `forward-probe` and `sidestep` at the current pose. |

A decision has an `action` and an optional `state` object. Use `wait` to hold, `baseline` to release the lease, `route` with a currently offered integer `node` and optional `skill`, or `motor` with a `skill`, one through five `steps`, and an optional `goal`. A motor goal is a world-space direction vector and a positive distance in game units. The supervisor normalizes the direction and freezes the world endpoint at the decision's source pose. Each attributed observation reports the updated direction and remaining distance from its current pose to that endpoint. The motor outcome still measures projected displacement between observations during native ownership. It does not certify arrival at the model's endpoint. The supervisor binds the sample, revision, offer and request identity itself. The maximum source is 192 KiB, the worker message is 320 KiB, a decision including its envelope is 24 KiB, and retained policy state is 8 KiB. JSON numbers must be finite.

The included policy ranks native offers using utility, path cost, conditional completion evidence, observed elapsed time and a small target-retention bonus. It commits once, waits for terminal evidence and preserves the route cursor. For motor movement it compares a forward stride and a lateral step using prior physical outcomes and the count of previous attempts. Even on a mapped level, a nearby peer or a set of empirically poor routes can trigger a motor probe between commitments. Each skill supplies ordinary analog inputs and a measurable displacement goal. These are starting behaviors. Competitive strength requires gameplay evaluation.

## Local tactical directives

Run `python -m bots.companion_cli --credentials RUN/companion/lily.json observe` and take the current fence. Write a directive to the watched path using a temporary file and rename. For example, the following Python snippet issues a one-minute sidestep directive. It reads the scoped credential locally.

```python
import json
import time
from pathlib import Path
from bots.companion_cli import call, load_private

credential = load_private(Path("RUN/companion/lily.json"))
observed = call(credential, "observation")
order = {key: observed[key] for key in ("run_id", "world_epoch", "life_epoch")}
order.update(id="sidestep-01", provenance="astra", expires_at=time.time() + 60,
             goal="motor", parameters={"skill": "sidestep", "distance": 0.04})
stage = Path("directive.stage")
stage.write_text(json.dumps(order), encoding="utf-8")
stage.replace("directive.json")
```

The initial policy recognizes `explore`, `resource`, `route` with an optional current `parameters.node`, `motor` with optional `parameters.skill` and `parameters.distance`, and `baseline`. A custom policy may implement other goals. Give a changed order a new ID. Renewing an active ID updates its expiry and keeps its original parameters. Reusing an ID after its previous expiry starts a new order with its new parameters. The runtime rereads the directive and checks the original sample age after any blocking lease or persistence operation, immediately before posting the action. Existing maneuvers finish before any tactical change. Life/world/run mismatches and expired directives are ignored. A directive can be present at initial launch or replaced while running. Astra uses this same lease through the supervisor. There is no hosted-model connection.

The separate `water_contact_v2.py` and `water_recovery_v3.py` policies are
synchronous stock-fixture experiments. Their required water-surface contact
input is absent from the deployed observation contract, and they reject that
missing field. Recovery v3 passed its declared same-pool transfer criterion,
landing 10/24 fresh starts against v2's 0/24, but it remains unpromoted. Neither
is selected automatically or qualified for this deployed observation path.
See [corrective recovery learning](LILY_MOTOR_LEARNING.md#corrective-recovery-candidate)
and the [checkpoint](reviews/2026-11-22-lily-recovery-learning-checkpoint.md).

The later [outcome-trained heads](reviews/2026-11-22-lily-outcome-learning-checkpoint.md)
share this fixture-only input requirement. Both improved development pool
landings to 24/24 from v3's 11/24, but each lost a v3 shaft win. Neither passed the
retention gate. They are preserved with all candidates in
`qa/lily-outcome-candidates.tar.gz`; there is no selected live replacement.

## Commit to a bank across motor commands

The opt-in `escape-bank` directive gives the movement policy one task above its
short native motor actions. Stage `bots/lily/policies/water_bc_v1.py` explicitly
to use the checked-in learned candidate. Its weights remain experimental; the
default adaptive policy does not silently select this model.

Using the same fresh fence and atomic directive-file replacement shown above,
supply a verified dry-bank position and sector:

```python
order.update(id="bank-escape-01", provenance="operator", expires_at=time.time() + 90,
             goal="escape-bank",
             parameters={"position": dry_bank_position, "sector": dry_bank_sector,
                         "budget_seconds": 60})
```

The task starts from a fresh wet observation at a native handover opportunity.
The target must be within 100 game units; the optional budget is 1–60 simulated
seconds and defaults to 60. A bank-aware custom policy reads `context.bank_task`
and echoes its `task_id` on each motor decision. The supervisor removes that
Python-only field before sending native controls and binds the command to the
committed endpoint. A conflicting local motor goal is rejected. Accepted child
actions link to the task only after positive native admission evidence.

The target, policy digest and task identity remain fixed across motor chunks.
New source can be staged and probed during play; voluntary replacement waits
until the task closes and native control is safe. Explicit release, a changed
operator order, worker fault, stale observations or lost authority still release
control. No policy may acquire an independent second lease.

Bank IDs have stricter retry semantics than general directives: the same ID in
the same environment/run/world/life cannot restart after completion, expiry or a
supervisor restart. Use a new ID for a new attempt, even at the same destination.
Renewing the old ID can extend its operator expiry but cannot change its target
or budget. Recovery reconciles pending receipts, preserves already-bound native
sequences, and censors the interrupted task instead of reconstructing missing play.

The live stopping proxy requires fresh, distinct supported/air samples within
0.15 game units of the target, spanning at least 0.25 simulated seconds. It starts
timing from a new stock-clock publication after the first qualifying observation;
the cached clock can precede that observation. A gap over 0.25 seconds resets the
proxy. An absent or regressing clock disables timed evidence for that task. The
budget likewise starts from a new clock publication after assignment. Operator
expiry and control faults still end authority.

Live `sampled_dry` and `budget_elapsed` records have **null physical verdicts**.
Rich sense does not publish the actor's sector, floor identity or every physics
step. The separate stock replay establishes a true landing only after 38
consecutive floor-attached steps in the requested dry sector at 150 Hz. Its
receipt reports physical success separately from controller credit: baseline
assistance or no wet candidate takeover cannot become an independent learned win.
See [the task comparison](../qa/lily-bank-task.json) and
[human reference review](reviews/2026-11-22-human-oasis-reference.md).

## Evidence, persistence and trace

Choose an environment ID that identifies the actual level content and rules. A stock map name reused for different geometry would mix incompatible evidence. SQLite journals the exact intended command and run-wide request ID before dispatch. The journal excludes the lease secret and credential. If the POST reply is lost, the supervisor looks up the same receipt without reissuing the action. The request ID, action kind and original run/world/life must all match. A later exclusive owner can reconcile a journal entry left by a crash between acceptance and local bookkeeping. A missing or evicted receipt leaves the unresolved submission censored. The native episode is linked to the durable request in one SQLite transaction. SQLite also stores observed native phase changes and terminal records. Route keys use the environment, target sector, half-unit position cell, approach heading and vertical direction, class and item bin. Motor keys use the environment, skill, starting cell, intended direction, medium and support state. Native sense has no self-sector field, so overlapping motor starting cells in distinct sectors can coincide. Counts persist across game and worker restarts. Attempts abandoned by an unknown previous game process have no physical verdict and cannot affect the competence estimate. A new exclusive controller censors outstanding records from its run after obtaining the lease.

An episode ID is the slash-joined run ID, world epoch, life epoch and native action sequence. One episode can contribute at most one verdict. `trials` counts records with a physical verdict. `probability` is the smoothed estimate `(wins + 1) / (trials + 2)`. An admitted action without a physical verdict still counts toward exploration. A proposal rejected before native admission changes neither exploration counts nor the policy's returned action-dependent state. Pending admissions keep that state tentative until an applied ACK or matching native progress confirms acceptance.

| Observation | Stored interpretation |
| --- | --- |
| ACK pending or applied | Transport receipt. A command can remain queued behind native work. |
| Route completed with arrived | Native follower verified physical arrival. |
| Started route failed with invalid_route | Verified route-execution failure. A route invalidated before starting is interrupted and censored. |
| Motor completed with playback | Input sequence finished. With a declared goal, at least two matching running-owner samples can establish displacement in the requested direction. Only a measured threshold crossing produces a positive physical verdict. A short or undersampled maneuver may be unscored. |
| Expiry, stale life, missing terminal, release, interrupted route, worker failure | Censored. Excluded from competence estimates. |
| Change in resources | `item_gain` contains observed positive changes to health, shields, mana or ammo during the attempt. The change has no item-instance provenance. A recharge or another nearby pickup can contribute. `damage` is net health-plus-shield loss between samples. Neither quantity establishes why the resource changed. |

Use `--trace FILE` to append one JSON record per line. Every row has `schema: 1`, `event`, `monotonic_seconds`, `run_id`, `world_epoch`, and `life_epoch`. Null fence components are possible before observation. The file contains game telemetry, including synchronized peer positions, and excludes credentials, lease tickets and chat.

| Event | Additional fields |
| --- | --- |
| `observation` | `sense` is the decoded native sample including axes, buttons, pose, peer records and action identity. `state` contains available health, shields, mana, weapon, ammo, kills, deaths, game_time and position. `episode_id`, `policy_hash`, `skill`, and `goal` are populated only for a matching running owner, action sequence, revision and source sample. |
| `submission`, `submission_reconciled`, `submission_censored` | Durable request identity before dispatch, recovery of a matching receipt, or unresolved evidence. These records have a `request_id`; only a bound native action has an episode ID. |
| `attempt` | `episode_id, action_seq, sample_id, revision, policy_hash, kind, skill, key, goal`. A declared motor goal and a route goal both include the fixed world position, initial direction and distance. Route goals also include sector and item bin. |
| `bank_start`, `bank_outcome` | Durable task assignment or its single live terminal, with `task_id`, policy identity and evidence source. Task-assigned attempts also carry `task_id`. Live bank outcomes are censored even when sampled dry support ends steering. |
| `ack`, `progress` | `episode_id, policy_hash` and either native action sequence and transport status, or the decoded native progress record. |
| `outcome` | `episode_id, action_seq, policy_hash, skill, status, physical_success, duration_seconds, applied_ms, damage, item_gain`. Verdicts can be true, false or null. Wall elapsed time and native applied simulation milliseconds have distinct units and clocks. |
| `stage`, `candidate_ready`, `activated`, `rejected`, `fallback`, `admission_error`, `recovered_attempt` | Policy transitions, failure/rollback and evidence recovery. `activated` includes the previous hash if available. |

Native sense snapshots sample the pose and ordinary inputs selected by the current control callback. The sampled pose precedes the later motion caused by those inputs. At up to roughly 20 samples per second, a trace captures selected control ticks. Stock health and inventory state arrives separately at about 5 Hz and can lag a rich sample or terminal. For imitation training, use the axes and buttons in an attributed running sample. For scoring, join the episode to its independent physical outcome. Baseline samples have null episode/goal metadata here. Raw action acceptance, native playback, and synthetic fixtures provide no competitive-performance measurement.
