# Independent motor feedback experiment

## Intent

The deployed 550 ms candidate combination landed in 22/27 bank trials, with
baseline steering in every trial that admitted wet learned control. That result
cannot isolate the movement model's competence or the effect of feedback cadence.
This continuation measures both under unchanged stock player physics, then tests
one additional observation contract if faster feedback is insufficient.

Implementation choices and publication to the existing development branch are
delegated. The existing production bots, engine packages and v1 weights remain
the baseline. This work does not promise competitive strength.

## Approaches and decision

Shortening live commands also changes baseline re-entry, neutral boundaries and
transport delays. A production streaming-controller redesign would couple those
changes to the model experiment. Use a fixture-only synchronous policy loop first:
observe the current physical state, obtain a bounded action, and advance the
original stock control/physics loop. Explicitly label this ideal-observation,
model-only benchmark separately from the deployed supervisor evaluation.

## Fixed comparison

Run the native baseline and frozen v1 at three predeclared feedback schedules:
550 ms, 100 ms and every original control tick. Reuse all 27 original starts and
control intervals. A decision lasts `ceil(requested_ms / tick_ms)` complete
control ticks; discard a fractional remainder at each new decision. Preserve
the original control interval feature, so only feedback cadence changes.
A zero-input wait is model-owned and obeys the same hold schedule.

The model branch must never call the baseline planner or its debug navigation
queries. Before stock input handling, copy current keys to previous keys, clear
and repopulate axes/keys, and derive fresh button presses. Use the production
codec's hundredth-unit axis quantization. Admit only four finite axes in [-1,1]
and jump/duck buttons. Reject other actions, weapon/Force requests, malformed
packets, wrong tick identity and failed workers. Obtain a model action at tick
zero before any physics. A failure censors that assigned trial; it never invokes
baseline rescue.

Preserve actor size, movement/look/freecam handlers, collision, 150 Hz physics,
damage, 38 consecutive floor-attached steps in the requested sector, and the
9,000-step simulation budget. Baseline outputs must match the preceding fixture.
The synchronous observer may expose current water-surface contact and previous
applied buttons, but those fields do not alter v1 inference.

Use an explicit bounded IPC protocol with an absolute one-second exchange
deadline. Freeze policy bytes and hash inputs/build/model/observations/actions.
Record each control tick, physics step, decision source tick, applied quantized
inputs and rising edges. Complete ordered ownership and a valid physical terminal
are necessary for independent candidate credit. Retain every assigned failure,
timeout and infrastructure-censored row. Preserve the raw private evidence.

## One conditional learning candidate

If v1 with per-tick feedback does not match all baseline landings, fit one v2
candidate adding only physical water-surface contact and the preceding applied
jump state. Keep the 32-unit feedforward architecture, existing 15 features,
optimizer, 200 epochs, seed 23 and output thresholds fixed. Recollect the added
physical fields from the engine; never infer them from baseline navigation phase.
During evaluation, previous input comes from the candidate's own actual action.

Fit on the seven original training pose groups only. Every yaw, interval variant
and recollection of a pose stays in that same group. The two original held-out
groups have now informed diagnostics and are development evidence for v2, not an
untouched confirmation set. Freeze one candidate before opening its results on
a separately predeclared set of physically valid nearby starts. Label those as
perturbation stress cases, not new-map or human-opponent generalization.

The contact-aware candidate is an experimental fixture policy until its physical
observations and controller timing exist in the deployed runtime. Missing contact
evidence must fail closed. Do not silently fill the field or automatically promote
weights. No online reinforcement learning is claimed by supervised refitting.

## Evidence and release

Publish code, portable helpers, compact receipts, all case results and explicit
limits. Do not publish retail geometry, credentials or raw media. Preserve v1 and
all unfavorable experiments. Independent review, meaningful boundary tests,
baseline equivalence and package integrity precede the authorized push.
