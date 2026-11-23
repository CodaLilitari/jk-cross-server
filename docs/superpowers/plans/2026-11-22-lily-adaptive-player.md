# Lily Adaptive Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Give Lily ordinary-input authority, persistent outcome learning and live executable policy replacement while retaining existing autonomous bots.

**Architecture:** An opt-in engine adapter publishes physical state and executes committed routes or short motor sequences. A separate Python supervisor hosts replaceable policy processes, preserves experience and accepts operator directives. Existing bots remain default and provide fallback/comparison.

**Tech Stack:** Existing C engine/native tests, Python standard library, browser JavaScript adapter; optional already-installed NumPy for offline motor training.

**Spec:** `docs/superpowers/specs/2026-11-22-lily-adaptive-player-design.md`

## Global Constraints

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

## Review Focus

- An identical intent or a worker reload must not restart a held jump/Force action; pin native edge and runtime boundary tests to Tasks 1 and 3.
- A delayed action from a previous life/browser instance must not execute or receive reward in the new life; pin fencing/censor tests to Tasks 1–3.
- More than 256 motor actions must remain available without weakening legacy request-id rules; pin sustained-stream tests to Task 2.
- A candidate policy can hang on import, flood output or emit NaN; pin process deadline/size/rejection tests to Task 3.
- Arrival without useful inventory gain and missing telemetry must not be called successful acquisition or motor improvement; pin outcome attribution tests to Task 3 and real receipts to Task 4.

---

### Task 1: Native action authority and matched wire codec

**Files:**
- Modify patched engine `src/AI/jkBot.c`, `src/AI/jkBotCompanion.inc` and focused navigation hooks.
- Create focused engine `src/AI/jkBotLily.inc` if that keeps responsibilities clear.
- Modify `native/bot-client.patch` in this worktree after generating the complete source diff.
- Create `bots/lily/__init__.py`, `bots/lily/protocol.py`, `docs/LILY_PROTOCOL.md`.
- Add native companion/driver regressions and `tests/test_lily_protocol.py`.

**Interfaces:**
- Produces native event kinds 5 offers, 6 progress, 7 rich state; commands 19 commit, 20 motor.
- Produces `decode_event(kind, payload) -> dict | None` and `encode_command(kind, body, deadline) -> bytes` with public format/constants in `bots.lily.protocol`.
- Publish exact fields/layouts in `docs/LILY_PROTOCOL.md` before Tasks 2/3 wire integration. Consumers must use the codec rather than duplicate layouts.
- Native feature flag `JK_BOT_LILY=1`; disabled path preserves original behavior.

- [x] Write native failures proving disabled rejection, malformed/deadline/sample rejection, input application, continuous held edges, bounded queued successor, physical route completion and terminal identity replay.
- [x] Run those tests and confirm failures reflect missing extension behavior.
- [x] Implement the bounded protocol, rich state, offer/route ownership and motor authority from the spec; keep authoritative stock rules and existing settings intact.
- [x] Write and run matching codec tests including nonfinite, oversize and wrong-type payloads.
- [x] Run affected native tests plus the existing native regression set; record exact commands and results.
- [x] Generate the native patch and commit only this task's files; report source/worktree state and remaining runtime risks.

### Task 2: Scoped companion, CLI and browser/native launch integration

**Files:**
- Modify `bots/companion.py`, `bots/companion_cli.py`, `bots/run.py`, `bots/profiles.json` as needed.
- Modify `web_bots/serve.py`, `web_bots/client.js`.
- Add/modify focused tests in `tests/test_companion.py`, `tests/test_bots.py`, `tests/test_web_bot_host.py`, `tests/test_web_bot_client.js` and `tests/test_lily_bridge.py`.
- Update `docs/COMPANION.md` with extension usage while preserving legacy contract.

**Interfaces:**
- Consumes Task 1's codec and `docs/LILY_PROTOCOL.md` verbatim.
- `Hub(..., experimental_ids=())` defaults to no extension. Only explicitly selected Lily is enabled.
- GET observation retains legacy fields and adds `lily: {sense, offers, progress, ...freshness}`; capabilities advertises extension support.
- Authenticated POST `commit` and `motor` use the existing lease/fences with Task 1 codec. Keep a separate bounded history for high-rate extension commands.
- CLI `commit` and `motor` accept local JSON payloads; CLI observe exposes extension state. Launcher flag is `--adaptive-lily` and enables required companion/native capability only for Lily.

- [x] Add failing tests for enabled versus default seats, malformed commands, stale observation/fence, duplicate submission, continuous >256-command operation, and browser deadline/identity rebasing.
- [x] Implement bridge integration using codec validation; preserve legacy pending/idempotence semantics.
- [x] Implement launch flags and CLI. Native Lily may use stock Kyle assets unless an existing compatible cosmetic is explicitly provided; do not change current defaults.
- [x] Run affected Python/Node tests and the complete Python suite, reporting pre-existing failures separately.
- [x] Commit only task-owned files and report the shared JSON contract to Task 3.

### Task 3: Live policy supervisor, retained outcomes and initial skills

**Files:**
- Create `bots/lily/runtime.py`, `bots/lily/worker.py`, `bots/lily/memory.py`, `bots/lily/policies/adaptive.py`, and focused `__main__.py`/CLI files.
- Create `tests/test_lily_runtime.py`, `tests/test_lily_memory.py` and process fixtures where required.
- Create `docs/LILY_ADAPTIVE.md` for executable policy API, memory/outcomes and operator directives.

**Interfaces:**
- Consumes Task 2 authenticated observation/commit/motor/release APIs and Task 1 codec validation.
- Policy exports `ABI_VERSION = 1` and `decide(observation, context) -> dict`; source and optional model/config hashes identify revisions.
- Supervisor CLI uses `--credentials`, `--policy`, `--memory`, `--environment-id`, bounded `--duration-seconds`, and a local `--directive-file` for Astra/operator input.
- `ExperienceStore` owns durable, deduplicated attempts/outcomes and estimates; worker state remains bounded JSON separate from retained experience.
- Runtime trace records observations/applied controls, policy transitions, native acknowledgments and actual outcomes, with credentials/chat excluded.

- [x] Add failing integration tests for same-session executable replacement, equal-length source rewrite, hanging import/decision, invalid output, policy crash, action-boundary handoff, stale life, and retained exactly-once outcome learning.
- [x] Implement isolated asynchronous worker IO and bounded supervisor decisions; active policy continues while candidate warms.
- [x] Implement persistent conditional outcome estimates and an adaptive initial policy with meaningful route choice, stable commitment and at least one ordinary motor skill.
- [x] Implement fenced operator directives through the existing owner rather than a competing lease; same directive renewal must retain progress.
- [x] Run real worker-process tests plus full Python suite. Explicitly distinguish playback completion, physical arrival, useful acquisition and censoring.
- [x] Commit task-owned files, report commands for live stage/activation/rollback and exact trace schema for Task 4.

### Task 4: Motor-learning experiment, real-engine validation and packaging

**Files:**
- Create compact training/export/inference modules under `bots/lily/` without overlapping Task 3 files.
- Extend a focused injected-input replay/trace adapter under `scripts/bot_development/` or `native/tests/stock_water_replay/` if necessary.
- Update browser/native source patches/build receipts and create `qa/lily-adaptive-live.json` with honest observed results.
- Update `docs/BOTS_CONTINUATION.md`, `docs/LILY_ADAPTIVE.md` and release/source manifests as affected by actual packaging.

**Interfaces:**
- Consumes actual applied-control trace and outcome schema from Task 3.
- Exports versioned feature normalization, action contract and JSON weights suitable for standard-library policy inference, with digest recorded by runtime.
- Real-engine probe must use the new extension path, not call only the legacy controller fixture and infer equivalent behavior.

- [x] Validate a compact train/export path with separate episode splits and honest held-out loss/action agreement; do not equate cloning with stronger gameplay.
- [x] Build native and browser adapters using existing pinned dependencies and reproducible packaging.
- [x] Exercise ordinary motor inputs and a controller revision in a live engine or stock-physics injected-action environment; retain exact engine/policy digests, action/outcome timing and fallback result.
- [x] Verify retained learning on observed outcomes across supervisor restarts and unchanged behavior/capability of baseline seats.
- [x] Train/evaluate an actual compact candidate only when suitable observed data are available; otherwise report the unfulfilled data requirement explicitly with runnable tooling.
- [x] Perform independent whole-branch review, resolve material findings, publish commits to the new branch and provide a reproducible continuation checkpoint.

## Execution rulings

- User delegated implementation and accepted beginning with this increment; no new design/plan confirmation is required.
- Use an isolated feature worktree. Temporary builds may use the separate temporary filesystem; preserve existing captures and baseline artifacts.
- Independent tasks may proceed concurrently with exclusive file ownership and a fixed shared contract; dependent wire integration waits for Task 1's published codec. This follows the session's proactive parallel-work instruction.
- Testing is concentrated on actual control, lifecycle, process replacement and learning attribution risks. Do not add implementation-mirroring tests or repeat successful suites without a concrete remaining risk.

## Completion checkpoint

The first increment is implemented, independently reviewed and published as draft PR #2 on `feature/lily-adaptive-player`, stacked on the preserved baseline branch. The final review/test checkpoint is `docs/reviews/2026-11-22-lily-adaptive-checkpoint.md`. That document and the QA receipts distinguish physical control, retained decisions, held-out model fit and the competitive work still open.
