# SDD ledger — plan: docs/superpowers/plans/2026-10-28-browser-spectator.md

## Authorization and baseline

Andrei approved the reviewed optional WebGL geometry design with “Proceed” after the explicit approval question. Continue implementation without another approval loop. Existing authorization covers feature branch publication and checkpoints; no merge or deployment requested.

Project worktree: /workspace/scratch/55e850edc256/jk-browser-spectator, branch feature/browser-spectator-renderer, base d7009dcebe259db98003bfc668e2ca98909cf20f.
Native worktree: /workspace/scratch/55e850edc256/jk-native-browser-spectator, base 74e4657c4f1751d09af9ad9e056acb8f41997acb plus exact existing project patch.

Ruling: use an external isolated worktree — preserves the recovered branch byte-for-byte — costs only a reversible new branch/check-out.
Ruling: skill helper scripts are unavailable through their provider; use an equivalent plan-specific ignored workspace and explicit briefs — preserves the ledger/review workflow without installing tools.
Ruling: Task 2 native/manager/browser components run in parallel with disjoint ownership and a frozen wire contract; root alone stages/commits — saves time and avoids shared-index races.
Ruling: do not block approved development on the unrelated GitHub provider grant; preserve GitLab checkpoints and record GitHub as incomplete.

## Preflight conflict scan

| Tasks | Producer / consumer or internal agreement | Finding / ruling |
| --- | --- | --- |
| 1 / 2A,2B,2C | Exact JKSG contract consumed by each component | Shared document is authoritative; any needed change goes through root |
| 2A / 2B | Native operation 3, capability 16, independent frame socket / Python decoder and IPC | Same header, lease and count bounds; no shared source file |
| 2B / 2C | Authenticated geometry route, additive status / optional viewer | Same URL/body; manager owns asset allowlist, browser owns JS/HTML/CSS |
| 2A / 2C | Clip-space RGBA/index payload / shader inputs | Native projection fixed; WebGL profile explicitly uses LESS, depth write, no blend/cull |
| 1 | Baseline/spec/protocol and initial commit | No product behavior change |
| 2A | Native tests exercise capture/channel/lifetime implementation | Existing render guards and image channel remain authoritative |
| 2B | Socket/HTTP tests exercise validation/lifecycle/routes | Optional errors must not affect image controller or gameplay IPC |
| 2C | Decoder/UI tests plus real browser evidence | Node mocks insufficient for visible result; Task 3 requires live GPU draw |
| 3 | Integration/build/live qualification | Root runs full suite after all worker edits finish, avoiding inconsistent intermediate files |
| 4 | Review/publication | No merge/release; exact remote-tree verification required |

## Progress

Task 1: worktrees and fixed interface documents prepared. Native baseline: all 12 reported observer checks pass using existing build flags under socket-capable execution. Python/Node baseline logs in /workspace/scratch/55e850edc256/spectator-audit/development/baseline.
Task 2A: implemented; fresh review requested changes for missing bounded native rejection diagnostic. Fix round 1 dispatched to geometry_native_fix; original implementer no longer live.
Task 2B: implemented; fresh review found stale-epoch geometry denial poisons new epoch. Fix round 1 dispatched to geometry_manager_fix; original implementer no longer live.
Task 2C: implemented; fresh spec and quality review PASS, no findings. Real WebGL fixture passed 8/8 readback pixels and context loss observed in Chromium 156 / SwiftShader.
Task 3: integration underway. Initial command exits all zero: manager count output incomplete (must recover explicit runner result); gateway 27, UI 33, native 17 behavior groups, packager 2. Live test isolated at local panel port 48765.
Task 4: initial approved docs checkpoint published on GitLab branch cf565fdc15ddc3f47d13dddca2611a1943c946ca. Implementation checkpoint pending review fixes/qualification.

Baseline Python 159/159 and Node 16/16 passed. Initial contract commit: ae692c74d8d59485b10bea198de0ce49b7af9057.

Task 2A: minor (deferred): unconditional rdTri declaration breaks RDCACHE_RENDER_NGONS/TARGET_TWL profile; Linux target unaffected. Whole-branch reviewer must triage.
Task 2B: reviewer investigated lease extension after in-flight operation; no concrete contract violation established, no finding.

Task 2A: fix round 1/5 (2 addressed, 0 important open — bounded rejection diagnostics; literal RPATH token; scoped native review PASS). Minor n-gon portability remains deferred.
Task 2B: fix round 1/5 (1 addressed, 0 open — stale epoch activation retry; 54 focused tests; scoped review PASS).
Task 3: final manager TestResult explicitly confirms 176/176 passed, zero failures/errors/skips, no source changes during run. Gateway27, Node33, native observer19 behavior groups and native packager2 passed. Actual packaged-binary live UI checks passed; observed paired image/geometry capture sequences match. Package core16944b47, byte-identical supplied-object relink, successful source-rebuild relink.
Ruling: execute the already requested feature-branch publication without presenting another integration menu; do not merge, release, or deploy — user asked for a branch and then continued development.
Ruling: preserve the plan evidence until it is committed and checkpointed; do not delete work that would recreate the earlier lost-evidence problem.

Final whole-branch review: two Minor findings, both addressed by the single final fix wave. Scoped re-review approved; no open findings. Current Node34, native19 and Linux SDL2+n-gon syntax check passed. Latest actual panel pass passed all12checks. The initial TARGET_TWL missing-type claim was corrected; real failing profile was Linux SDL2+n-gon member access.
Publication checkpoint: GitLab23f11bc233c77b59d61ed6d43214dc9716fd45b6 exactly matches local576f768 tree0f3967d8cb707a63068c977bf2cfe07e4547e21e: all352files,7executables,414treeentries. Final fix/evidence follow-up pending. Fresh GitHub blob-write retry23:24UTC returned403Resource notaccessiblebyintegration; no CLIcredentials available.
