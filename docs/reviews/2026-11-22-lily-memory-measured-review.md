# Independent measurement review of the protected-memory run

**Final finding (23 November UTC, 22 November local).** The frozen open selection is static G8, with 32/32 landings in 45,889 charged steps. Transfer is inconclusive because both admitted transfer attempts were invalid and no scored pair exists. The frozen offline-audit CLI exited 1 on the heading validation and produced no final report. A separate post-run supplemental report re-inferred the 1,120,070 completed-prefix decisions and reproduced both invalid rejections. The counts and selection below are independently reconstructed from the preserved run. All three archives and their complete raw membership have been independently verified.

## Initial prefix, 23 November 2026 UTC (22 November local)

I examined the completed calibration block and the published S1–S4 and R1–R3 training rankings for run lily-memory-learning-20261122-01. This covers 1,152 completed assignments (144 calibration and 1,008 training) and 63 ranked candidates. I matched each assignment to its native terminal and both process return codes, recalculated each candidate's eligibility and four-part score, and resolved ties in declared order. I used the native target-sector supported-dry terminal, checked the 38-step minimum for successes and charged each failure 9,000 steps. I used no fitting, selection helper, new episode or later-stage evaluation data.

### Calibration and active controls

V3 won 17/48 training pool starts, 15/16 training shaft starts and 8/8 shaft anchors. G4 won 48/48, 15/16 and 7/8 respectively. Combined, 110 wins and 34 completed failures account for all 144 attempts. All 72 between-policy pairs had identical starts and initial observation hashes. All previously observed overlaps (16 v3 and 24 G4) had byte-identical native, motor and start files across studies. The zero-residual S1 and R1 incumbents each matched the calibration G4 native, motor and start files byte-for-byte on all 16 common starts, or 7,797 control ticks per arm.

### Ranking from observed outcomes

The native outcomes gave the same four-part score, eligibility and lost anchors as every published candidate row examined. Selected candidates had zero missed reference shaft wins, zero missed reference pool wins and 16/16 landings on that generation's common batch.

|Arm and generation|Selected candidate|Charged steps|Anchors, incumbent to selection|Proposals excluded|
|---|---|---:|---|---:|
|Static 1|s-g01-c05|30,738|7 to 8|3|
|Recurrent 1|r-g01-c07|32,424|7 to 8|2|
|Static 2|s-g02-c02|28,869|8 to 8|2|
|Recurrent 2|r-g02-c00|31,522|8 to 8|5|
|Static 3|s-g03-c03|23,893|8 to 8|0|
|Recurrent 3|r-g03-c01|23,366|8 to 8|3|
|Static 4|s-g04-c00|24,230|8 to 8|5|

### Recurrent state and native action

I re-inferred three complete R1 traces with their individual frozen standalone exports, starting every episode from the explicit zero vector. At each of the 2,420 ticks the recorded raw observation hash, before/after state hashes, four bounded memory values, recomputed quantized axes and buttons, applied motor input, native control, six-step native clock, preceding button state, rising-edge presses and model ownership agreed. The native terminal also agreed with the block row. The three assignments were r-g01-c02--outcome-train-pool-03-yaw-90 (1,500 ticks, timeout at 9,000 steps), r-g01-c07--outcome-development-shaft-01-yaw-90 (291 ticks, 38 dry steps at step 1,742), and r-g01-c07--outcome-train-pool-04-yaw0 (629 ticks, 38 dry steps at step 3,772). This was a three-episode full-trace sample.

### Frozen identities and environment

The declaration file matches Git bfe9aa52957046375ca34733debdc8eb1ece3520 and SHA256 77ef88dcfa3f94c2095a4fbd397cbfd3c6b11fafe8b55f387503df24b66b5b4d. All 71 frozen-file entries, six previous-evidence entries and both 17-entry fixture manifests match the working files and Git source 0df6d85faca861db917528bb8255e745f6725769. The previous run header matched the declaration. All 101 live build file sizes and hashes matched their manifest and all 101 prior raw file hashes. The executable SHA256 is 204ef95913b472b9190aa9b8d74aafff26043f0d8ddfd477f68d43d4ca54dd1f. The two reference model files, canonical identities and exports matched the declaration. All 63 candidate model files, canonical identities and exports matched their rankings.

The live path resides on tmpfs. The header recorded 5,225,656,320 free bytes at start. At 03:26 UTC, df reported 5,225,709,568 bytes total and 4,385,026,048 available on that mount. This prefix contains no final selection or transfer result, and it does not establish durable archival retention.

## Completed run, independent measurement review

All 144 calibration, 2,304 training and 160 open assignments were scoreable: 2,608 total, 2,389 landings and 219 completed failures. I checked the independently read native terminal and process records for each. Across all 16 generations-by-arm, every candidate used its declared 16-start batch. The independently computed 144 candidate four-part scores, protected-anchor loss lists, eligibility decisions, 16 selected IDs, model hashes and policy export hashes agreed with the frozen records. Every selected candidate landed on all 16 of its generation's assignments. The fixed anchors increased from seven to eight in generation one of each arm and remained at eight. Rotating cases varied by generation.

|Arm and generation (remaining blocks)|Selected candidate|Charged steps|Anchors retained|Proposals excluded|
|---|---|---:|---:|---:|
|Recurrent 4|r-g04-c00|32,136|8/8|4|
|Static 5|s-g05-c07|22,596|8/8|4|
|Recurrent 5|r-g05-c05|23,638|8/8|5|
|Static 6|s-g06-c05|20,249|8/8|4|
|Recurrent 6|r-g06-c00|25,673|8/8|3|
|Static 7|s-g07-c04|22,370|8/8|2|
|Recurrent 7|r-g07-c07|25,752|8/8|4|
|Static 8|s-g08-c06|22,093|8/8|2|
|Recurrent 8|r-g08-c06|27,810|8/8|4|

### Open results, paired at the identical 32 starts

|Policy|Pool landings|Shaft landings|Pool charged steps|Shaft charged steps|Total charged steps|
|---|---:|---:|---:|---:|---:|
|v3|11/24|8/8|147,229|10,861|158,090|
|G4|24/24|7/8|57,145|18,542|75,687|
|Static G8|24/24|8/8|37,785|8,104|45,889|
|Recurrent G8|24/24|8/8|42,178|14,921|57,099|
|Recurrent G8, no history|24/24|8/8|42,241|13,840|56,081|

The two eligible final candidates both qualified. Static won the declared lower-charged-steps tiebreak by 11,210 steps. The stored selection and freeze identify its final-generation export s-g08-c06. On all 64 historical baseline episodes (32 v3 and 32 G4), the start, full native trace and full motor trace matched the previous study byte-for-byte. All five current policies had identical start files and initial observation hashes on each of 32 pairs.

Against v3, static gained 13 pool landings and retained all 19 v3 landings. Pool gains across the six positions were 3, 2, 2, 2, 1 and 3. Shaft gains were zero. Against G4 it gained one shaft landing (shaft 01, yaw 90), retaining all 31 G4 landings. Recurrent, static and no-history had zero landing differences at every open position. The recurrent arm took 4,393 more charged pool steps and 6,817 more shaft steps than static. Against its own no-history intervention it took 63 fewer pool steps and 1,081 more shaft steps, or 1,018 more steps overall. The open set is design-informed and the eight shafts were training anchors.

### Final-policy trace samples

I checked the final recurrent and no-history checkpoints on the same two starts with separate zero-initialized replay sessions. At pool 01 yaw −90, all 658 recurrent and 268 no-history decisions matched their state and physical joins. At shaft 01 yaw 90 the corresponding counts were 439 and 500. The resulting 1,865 open decisions and 2,420 earlier training decisions form a seven-episode sample, 4,285 matched ticks. Each final policy reached the correct target with 38 dry steps on both examples. The two frozen model files have equal base and residual numerical parameters and distinct modes and canonical hashes.

### Transfer interruption and scope

Of the six arms' 288 sealed assignments, the first two v3 assignments (pool 01, yaw −45 and +45) have invalid records with detail incorrect_initial_heading. Their retained raw file hashes agree with the ledger. The other 286 assignments were unrun; only the two invalid work directories exist. No transfer observation entered the score. No paired transfer timing, original/stress/recovery score, held-out efficacy or memory-benefit claim is available. The 134 conditional diagnostic attempts never started. Across the declared maximum of 3,030, this accounts for 2,608 scoreable, two invalid and 420 unrun, with zero censored.

### Per-start open outcomes and charged steps

The cells give charged steps at 150 Hz. F marks a failure charged at the declared 9,000-step cap. All other cells are supported-dry landings.

|Family|Position|Yaw|v3|G4|Static|Recurrent|No history|
|---|---:|---:|---:|---:|---:|---:|---:|
|Pool|01|-90|9,000 F|3456|1493|3944|1607|
|Pool|01|0|9,000 F|4197|1476|3183|1861|
|Pool|01|90|2865|3740|2760|2771|4604|
|Pool|01|180|9,000 F|1728|3732|2105|2334|
|Pool|02|-90|3402|2128|2106|2344|1747|
|Pool|02|0|9,000 F|1205|1824|1416|1896|
|Pool|02|90|9,000 F|1609|1644|1724|914|
|Pool|02|180|1646|5813|1001|1485|3185|
|Pool|03|-90|9,000 F|1577|3035|1661|1664|
|Pool|03|0|6192|2393|2092|1760|3406|
|Pool|03|90|8997|2388|1250|1373|1316|
|Pool|03|180|9,000 F|1217|1101|1288|1285|
|Pool|04|-90|9,000 F|1147|1020|930|933|
|Pool|04|0|9,000 F|5060|1250|821|813|
|Pool|04|90|1056|1634|770|854|834|
|Pool|04|180|826|873|814|2042|890|
|Pool|05|-90|9,000 F|1439|1878|1957|1026|
|Pool|05|0|2422|4654|998|1430|1783|
|Pool|05|90|684|1501|642|867|864|
|Pool|05|180|731|3120|2754|893|836|
|Pool|06|-90|1408|1127|553|785|1612|
|Pool|06|0|9,000 F|509|1519|4528|3488|
|Pool|06|90|9,000 F|2089|1579|1180|2316|
|Pool|06|180|9,000 F|2541|494|837|1027|
|Shaft|01|-90|2765|2679|1348|1436|1550|
|Shaft|01|0|1015|1144|1246|1989|2203|
|Shaft|01|90|1366|9,000 F|1041|2633|2998|
|Shaft|01|180|1320|1028|1094|2565|1385|
|Shaft|02|-90|961|807|851|2443|1213|
|Shaft|02|0|979|1195|690|1503|2109|
|Shaft|02|90|1153|1099|1008|898|1512|
|Shaft|02|180|1302|1590|826|1454|870|

### Raw evidence archive verification

I streamed the three compressed archives independently and recomputed both their full compressed-file digests and each member's uncompressed SHA-256. I checked safe relative paths, regular-file membership, uniqueness within and between archives, exact lengths, agreement with the live run bytes, and complete on-disk path coverage. The only non-run members were the two declared license texts in the historical build archive. Both matched the receipt's byte counts and digests.

|Archive|Raw files|Raw bytes|Compressed SHA-256|
|---|---:|---:|---|
|Public candidate models and exports|298|7,569,342|8fb7cb16d85175910e123331414aa526b0f4c24f68c8f9516a3b6bdd63368520|
|Historical public build inputs|96|1,332,811|6c0cc363ca28040eaec778031bd154249152f1783483b8b56bf288ed9b9febb6|
|Private evidence|20,944|1,304,489,795|833d2a827c4e3033fae100c31110a401ddeced51d0bb6b78e6ca270a2a28336d|

Each of the 149 candidate artifacts has both its model and export. The private archive contains the remaining five build files. The union reproduces all 21,338 raw files and 1,313,391,948 bytes. The independently reconstructed sorted, compact path/length/hash inventory SHA-256 is 88a9389d73cd97c174f4bc738c36057d3a31b2ebb30e893fca52b132a5027ed5, matching the preservation receipt. This verifies the content of the available archives.


### Final audit status and extent of independent verification

The experiment operator recorded exit 1 from the frozen offline-audit command with “Memory reconstruction failed: incorrect_initial_heading”. It produced no official final report or reported final re-inference count. Across all 19 stored block manifests I independently reconciled each assignment, per-block status and count to the physical work directories, compared all 20,880 recorded attempt-file sizes and hashes, and checked each of the 2,608 scored rows against its native terminal, process record and first observed input. Of 2,896 ledger assignments, 2,610 were attempted, 2,608 completed (2,389 landings, 219 failures), two were invalid, 286 were unrun and zero were censored. The remaining 134 conditional diagnostics had no ledger or work directories.

Counting the decisions in every completed journal independently gives **1,120,070**, exactly equal to the stored 2,608 per-episode re-inference counts, control ticks, and native terminal tick counts. The two invalid traces contain another 2,354 recorded decision lines excluded from this total. My separate frozen-export state/action re-inference covered **4,285 ticks in seven complete episodes**. The independent file/terminal reconciliation and sampled model replay above are the basis for this review.


### Supplemental reconstruction cross-check

A separate post-run reporter completed at 03:54:58 UTC and wrote qa/lily-memory-supplemental.json (SHA-256 475a3b9b311ef900204a5b6ea422d4978ffc7de2f3e0280be33b4908546ed685). Its recorded 18 completed blocks have **1,120,070 actual offline re-inferences**. I compared every one of its 2,896 assignment rows across 19 blocks with the run: the 2,608 scored rows matched the physical terminals, process evidence, initial observed inputs and journal lengths; the two sealed invalid rows matched their raw file hashes, exact error and unscored status; the remaining 286 rows matched unrun assignments. All 16 full ranking records, all block receipts and assigned model identities, all five open scores, the frozen static selection, all 160 published pairwise comparisons with their aggregated position and timing differences, and the raw archive inventory agreed with my independent checks. The supplemental reproduced the two heading rejections without scoring a sealed outcome. Its reported inference count describes its completed-prefix reconstruction; my separate seven-episode sample remains 4,285 decisions. The original preregistered CLI still has exit code 1 and no final report.
