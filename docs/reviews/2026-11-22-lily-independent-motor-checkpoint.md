# Lily independent motor checkpoint

The movement models now have an exclusive stock-input benchmark, with evidence
from the first applied action through the exact physical terminal. Both neural
candidates remain unpromoted. Faster feedback reduced the frozen model's landing
rate; the contact/history candidate improved familiar starts and regressed on
the nearby positions declared before training.

## Measured result

| Controller and schedule | Original case/yaw starts | Predeclared nearby starts |
| --- | ---: | ---: |
| Native baseline | 27/27 | 16/16 |
| Frozen v1, requested 550 ms | 22/27 | Not assigned |
| Frozen v1, requested 100 ms | 21/27 | Not assigned |
| Frozen v1, every original control tick | 18/27 | 10/16 |
| Contact/history v2, every original control tick | 21/27 | 7/16 |

The [complete receipt](../../qa/lily-independent-motor.json) retains all 226
executions, all failures, source identities and per-case outcomes. Every trial
has a complete control stream and a physical terminal. The count includes 43
repeated baseline executions used for pairing, leaving 183 distinct
controller/case/yaw configurations. The nearby set has eight pose groups, each
at two headings. No infrastructure-censored result was converted into a loss.

This is an ideal synchronous observation experiment. It does not measure the
live supervisor's transport delays or handover behavior. The preceding deployed
22/27 candidate result included baseline assistance and cannot establish the
same independent-control claim. Neither experiment measures human-opponent or
multiplayer strength.

## What changed

The fixture gives a frozen policy exclusive movement control from tick zero.
It preserves the original look, movement, freecam, collision, damage and 150 Hz
physics functions. Four analog axes use production quantization. Held buttons
retain their actual previous state, so holding Jump does not manufacture new
presses. No baseline planner or debug navigation query runs during model ticks.
A sequenced-packet exchange carries the tick identity and has one absolute
one-second deadline. Invalid controls, disconnection and stalled workers censor
the assigned trial without a fallback controller.

The scorer binds the first physical state to its declared position, sector,
velocity, health, breath, flags, pitch, interval and reconstructed yaw. It joins
every applied input to the correct decision observation. Success still requires
38 consecutive floor-supported physics steps in the requested dry sector, with
a 9,000-step limit. The 550 ms and 100 ms arms hold complete original ticks;
the original tick interval feature stays fixed.

One contact/history candidate adds the genuine water-surface flag and preceding
applied jump. It was fitted once on the original seven training poses: 22
episodes and 3,431 frames. The loader excludes every development and stress
trace. The [frozen receipt](../../qa/lily-contact-freeze.json) predates all stress
rollouts. The [declaration](../../qa/lily-motor-stress-plan.json) and
[addendum](../../qa/lily-motor-gate-addendum.json) preserve the cases, geometry
validation, gate and fixed settings. All eight starting spheres pass a
conservative binary32 error bound with at least 0.0304872 units of clearance
beyond the actor radius.

The 15 prior feature definitions and all action targets are preserved. Relative
goal reconstruction changes values only at floating-point precision, with a
maximum difference of 7.12e-8. Input width adds 64 parameters and changes seeded
initialization. This comparison measures the whole candidate and does not
isolate either extra feature individually. The original two excluded groups
have informed diagnostics and are development evidence for v2.

The reusable fixture, strict training/export pipeline, experimental model and
policy, geometry validator and failure-analysis helper are included. Existing
production controller code, native/browser engine packages and frozen v1
weights and export are unchanged.

## Failure diagnosis and next experiment

All eight contact-model pool stress failures reached the water surface and made
fresh jump presses. No recorded 150 Hz physics step placed those actors in the
demonstrated exit sector; every matched baseline was recorded there. The ninth
failure reached the dry sector, fell back into
water and made little final horizontal progress. The
[per-case audit](../../qa/lily-contact-failures.json) preserves the counts and
trajectory comparisons.

The learned policy needs a better approach and recovery behavior. These results
do not establish whether observation coverage, demonstration coverage or both
are responsible. The next bounded experiment is to collect corrective native
demonstrations from off-route states reached on the original training pool
poses, preserve actual input history, and evaluate the refitted policy with no
rescue on newly sealed starts. The present perturbation set is now diagnostic.
Outcome-based optimization and self-play remain later development; this
supervised experiment is neither.

## Verification

| Check | Observed result |
| --- | --- |
| Full regression suite, including native input boundary tests | 327 tests in 116.933 seconds; 324 passed and three platform-specific tests skipped. |
| Independent physical evidence audit | 226 valid terminals and 86,265 continuous applied control ticks, with no assisted model ticks. |
| Independent inference replay | All 55,326 saved decision observations reproduced their applied quantized controls. |
| Baseline preservation | All 27 original native traces match the preceding checkpoint; all 43 repeated original/nearby baseline runs match in both native and motor trace bytes. |
| Shared optimizer preservation | Original and refactored v1 fit returned identical canonical model and metric bytes on all 4,306 original frames. [Receipt](../../qa/lily-optimizer-equivalence.json) |
| Candidate isolation | Exactly seven original training groups; zero development or stress fitting rows; export regenerates byte-for-byte. |
| Evidence boundaries | Native tests reject misassigned poses/headings, altered observations, missing ticks, foreign inputs, malformed packets, disconnection and stalls. |
| Portable diagnosis helper | Regenerated all twelve case comparisons and physics-transition checks; diagnostic values match the original audit. Source receipt keys are normalized to experiment roles. |
| Release inventory | Version `0.4.0-dev`, 552 managed files; refreshed manifest and checksums, integrity check passed. |

The three skipped tests require PowerShell or Windows SID/DACL support. The
independent review found no remaining blocker within the implemented scope.
