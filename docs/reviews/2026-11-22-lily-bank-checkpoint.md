# Lily bank task and human-reference checkpoint

This extends the opt-in adaptive controller in
[draft PR #2](https://github.com/CodaLilitari/jk-cross-server/pull/2). It adds one
complete bank-escape task above short motor commands and a matched physical
evaluator. The preserved baseline branch, production native/browser engine
packages, neural weights and automatic policy selection are unchanged.

## Result

The final comparison completed all 54 assigned trials. Baseline landed in **27/27**;
the candidate-assigned runs landed in **22/27**, including **4/5** previous holdouts.
There were four candidate timeouts and one death. Eighteen candidate-arm landings
included baseline steering, and four occurred without any wet candidate takeover.
No trial qualified for independent neural credit. The candidate remains
**unpromoted**. This is a fixture result, not a multiplayer score.

The [machine-readable receipt](../../qa/lily-bank-task.json) preserves all cases,
owners, physical terminals, source identities and limitations. It also retains
the first complete matrix's 23/27 candidate result; the later 22/27 result was
not replaced with the more favorable run. Real-time controller startup and
transport allow run variation even with matched initial physical states.

## What changed

An `escape-bank` order creates a durable task with one target, revision, life
fence and bounded simulation budget. Accepted motor commands link to the task;
their individual movement outcomes do not decide whether the bank was reached.
New policy bytes can be staged during play, with voluntary activation held until
the task ends. Faults and explicit release still return control immediately.
The same directive ID cannot replay an ended task, including after restart.

The live dry-support proxy is deliberately censored. Exact success comes from
38 consecutive 150 Hz physics steps attached to a floor in the requested sector.
The fixture records the actual native controller before end-of-frame cleanup,
separates baseline/motor/neutral ticks, and joins motor ownership to the full
policy digest and admitted action identity. No physics or native handover rule
is bypassed.

Independent review found three defects and verified their correction: an
unrelated policy-supplied motor endpoint, missed late admission during restart,
and premature sampled closure from a cached stock clock. Regression tests failed
before those fixes and passed afterward. A further custom-policy edge now prevents
a zero-distance task endpoint from becoming a local displacement win.

That last guard was added after the final physical matrix. It changes local
credit only. All 688 recorded candidate motor attempts had strictly positive
distance, and the shipped policy waits near the endpoint. The receipt preserves
both runtime source hashes and the explicit check that the guard was unexercised;
all other recorded source hashes match the delivered code.

## Verification

| Check | Observed result |
| --- | --- |
| Full Python suite | 307 tests in 111.114 seconds; no failures, three platform-specific skips. Two require PowerShell and one requires Windows SID/DACL support. |
| Independent review before the final local-credit guard | All three important findings resolved; 68 focused Lily tests passed independently. |
| Final zero-distance regression | Failed with an unearned local win before the guard; included in the passing full suite afterward. |
| Final independent closeout | Receipt fields, raw receipt digest, both runtime hashes and all other fixture-source hashes verified. All 688 positive-distance attempts checked; no release blocker. |
| Physical comparison | 27 matched case/yaw pairs; every assigned row has a physical verdict and complete control ownership. |
| Baseline preservation | 27/27 fresh demonstration JSONLs byte-identical to `9e07697`; historical landing time, HP and sector match for all cases. |
| Training preservation | All original corpus hashes verified; 4,306/4,306 observations and all 27 terminals match after removing metadata already added before this change. Model weights unchanged; export reproducibility passes. |
| Human review helper | Public-preview helper smoke retrieved and indexed the requested samples; portable motion helper extracted and decoded the reviewed clips on the authorized desktop; both CLI interfaces checked. |
| Release inventory | Version `0.4.0-dev`, 531 managed files; refreshed checksums and package integrity check passed. |

The full suite exercises the new native oracle boundary, wrong-bank landing,
loss of support, complete assignment denominators, recovery and policy replacement.
No new rendered game session or human-opponent qualification was performed.

## Human footage

The [reference review](2026-11-22-human-oasis-reference.md) covers 100 one-second
samples from two Full Force Canyon Oasis excerpts, sparse tournament previews,
and a high-resolution status-message check. It distinguishes visible routes and
effects from guessed objectives and unobserved inputs. The message at 06:27
establishes Grip damage; an earlier empty-ammunition explanation remains unverified.
Public source links, clip hashes and sampling limits are recorded, with reusable
research helpers included. Third-party media and private host paths are excluded.

## Next experiment justified by the evidence

Retain the current production controller. The learned clone needs a better
movement experiment before promotion. The 550 ms action hold differs substantially
from its 26–87 ms demonstration ticks; measure faster feedback and recurrent or
terrain context with the same full-task oracle. A later independent-controller
experiment must also eliminate baseline steering through an explicitly measured
handover procedure before claiming autonomous neural escape. Contested pickups,
combat and self-play require their own observation and outcome contracts.
