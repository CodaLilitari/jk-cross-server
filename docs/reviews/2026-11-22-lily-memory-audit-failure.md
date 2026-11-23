# Why the frozen offline audit emitted no report

The official command exited 1 with “Memory reconstruction failed: incorrect_initial_heading”, as reported by the operator. It did not produce qa/lily-memory-evaluation.json. The independent stock-table analysis establishes the physical explanation for the two starts. A separate exception-handling asymmetry explains why the offline CLI could not publish even an inconclusive report. No source, receipt or score was changed.

## Frozen online path

At bfe9aa52957046375ca34733debdc8eb1ece3520, run_memory_learning.Experiment.perform (line 591) requests the sealed block only after writing the selection and freeze (574–580). Its live block calls run_block (464). run_block's worker executes the assigned trial then calls trial.audit_attempt (398–404). Old run_outcome_learning.dispatch starts at most two workers in this experiment, initializes all results to unrun, and calls future.result() (305–322). Any exception is encoded as an invalid record with exception type, message, and every regular file’s size and SHA-256 (323–327). This stops new admissions and drains already submitted workers (328–330). With both process files published, dispatch writes block.json and raises BlockStopped (330–341); it never returns scoreable rows to the memory runner.

Both recorded errors are ValueError/incorrect_initial_heading. The published block SHA-256 is bcd7f88663bb6dffbffd53e75eacb6baa91b8732cb39950d9a0c56828dc99263. Its 288 assignments have two invalid and 286 unrun, with no scored or censored attempts. The 134 diagnostic starts were part of the maximum budget, but no diagnostic ledger was admitted.

## Frozen offline path

1. audit_memory_learning.reconstruct (9–16) creates Experiment(audit=True) and calls perform. Calibration, 16 candidate blocks/rankings across eight generations, the open block, comparison, selection and freeze all precede the first attempted sealed reconstruction. Completed blocks enter experiment.report only after full audit_block and evidence-tree registration (run_memory_learning:461–472).
2. Upon the sealed call, Experiment.block sees completed=0 versus assigned=288 in its stored receipt, so it calls audit_partial_block (:455–458). After checking the assignment ledger, qualifying models and first attempt claim, audit_partial_block calls trial.audit_attempt directly (:331–358). This branch accounts for unfinished publications, censored attempts and absent directories. It has no exception-to-invalid conversion around that call.
3. I reproduced precisely one raw attempt offline and observed the following exception stack on the −45° v3 trial. Frame numbers are frozen: memory_rollouts.audit_attempt:271 → available_witnesses:174 → evaluate_motor.verify_start:123 → check:85 → ValueError('incorrect_initial_heading'). This happens before legacy motor re-inference or adjudication of a physical result. Constructing the runner's invalid envelope from that exception and the eight regular file hashes/sizes matched the corresponding stored block entry exactly. The +45° raw attempt was not re-audited for this addendum.
4. The ordinary ValueError propagates before audit_partial_block can collect remaining records, check the sealed receipt, write self.report['blocks']['sealed'], or raise the Incomplete class (:357–383, :458–460). audit_memory_learning.reconstruct catches *only* run.Incomplete, so neither its evidence.finish() nor incomplete_report() executes. main catches ValueError and exits 1 at :40–41. write(args.output,report) at :39 occurs only after successful reconstruct(). Consequently there is no official summary or final inventory closure even though prior stage checks were reached.
5. A second incompatibility exists for prospective work. audit_partial_block.labeled (:321–323) delegates to audit_outcome_learning.public_attempt (:174–192). It handles unrun, censored and complete. Given the dispatcher's invalid shape it first indexes the absent reinferred_decisions field; its other branches would require row/process. Adding a catch around only the attempt audit would therefore be insufficient. Tests for the partial path here cover censor/unrun behavior and errors on forged evidence.

## Post-run evidence approach

Keep the original CLI exit and missing output explicit. Preserve the failed command text/log, code identity and sealed block receipt; do not publish supplemental output at the official evaluation filename.

A separately named, read-only diagnostic can instantiate the frozen Experiment in audit mode and retain a reference to its instance. On the specific strict exception in the sealed path only, snapshot its existing report after asserting the expected 18 complete blocks, 16 rankings, selection and freeze are present and there is no sealed/diagnostic score. Those preceding stages represent 2,608 fully reconstructed rows if a new diagnostic run actually completes all those checks. Re-use the existing frozen block audit for that prefix. A helper that reads public/writer receipts only must label the calculations receipt-based; it cannot claim raw-decision re-inference. Preserve the original strict exception, even when it is expected. No error from an earlier stage is an acceptable termination condition.

Independently derive the sealed ordered assignment ledger and its predecessor from the locked freeze and inputs. Verify the two work directories exactly match the first two claims; other 286 are absent. Check every present raw file's hash, size, expected membership, and every per-attempt claim, compared against block.json. For each known invalid claim only, require frozen audit_attempt to reject with the recorded exact exception, then construct and compare the complete original invalid envelope without inventing row, process, decision count, terminal or score fields. Recalculate counts alongside a copy of the raw block digest. Treat any unexpected error, extra file, changed bytes, mismatched labels/exception or foreign later directory as a separate diagnostic failure. The preservation inventory should bind every file separately; do not imply frozen evidence.finish() completed. Do not use a general catch-and-continue to turn tampering into known invalid evidence.

Report three scopes separately: full raw reconstruction through open when achieved; independent reproduction of per-attempt validation rejection and byte inventory on sealed; no historical execution. Persist the open selected static identity, transfer criterion null and the frozen strict audit's failed status. A successful supplemental prefix check authenticates the completed prefix and preserves the failure boundary. It cannot give the original CLI a successful status or score any transfer attempts.

No games, retries or full audits were run in this investigation. Only one stored invalid attempt was passed through its frozen offline checking function.

## Supplemental implementation

The separate `report_memory_failure.py` helper now implements the closed scope
above. Its output is `qa/lily-memory-supplemental.json`; the original CLI's
intended `qa/lily-memory-evaluation.json` remains absent. The report records
`original_cli_failed: true`, the preserved failure transcript, the frozen source
hash and the post-run helper's own hash. It emits block progress only after the
unchanged strict block reconstruction returns successfully.

The helper requires the exact declaration, run header, sealed receipt and complete
raw inventory identities. It recognizes the heading error by its exact exception
type, message, frozen call-stack functions, first claimed work directory and
sealed partial-block context. It then derives the full ledger, reproduces both
strict rejections, checks every invalid envelope against the published receipt,
requires the other 286 directories to be absent and closes the supplemental
evidence inventory. Other failures are not accepted as this known interruption.
The invalid public records contain labels, exception identity and raw hashes;
they have no fabricated terminal, process result, inference count or score.

Three focused tests cover the genuine heading throw site without producing a
score, an identical error message thrown from a different site, and tampered
counts, raw hashes or free-space witnesses. The implementation check also passed
both retained invalid attempts through the unchanged verifier and reproduced
the complete sealed receipt. That additional check is distinct from the
one-attempt initial root-cause investigation. Full prefix reconstruction and
the final checkpoint suite are recorded in the validation receipt after they
actually complete; neither is implied by these focused checks.
