# Changes

## 0.2.0-dev — Browser asset delivery

- Send the selected missing custom JK/MotS episode through the published
  browser client's existing JKMT transfer protocol.
- Advertise the active mod with the existing JKMD fingerprint and prepare a
  deterministic mod pack for the browser's normal download/restart flow.
- Reconstruct matching original content through the client's retail-reference
  scheme; original game files and the special MotS Remastered pack remain
  local client requirements.
- Add a default-enabled download switch and a live browser-content section in
  the Python administration panel, including fingerprints and transfer counts.
- Keep asset work separate from game messages, with bounded queues,
  backpressure, retry handling and cancellation on departure.
- Reject resource overrides that would be missing from the advertised content;
  custom resources belong in the selected episode or configured mod folder.
- Accept the original installed resource aliases `res1.gob`, `res1low.gob` and
  `jkmsnd.goo` during server preflight.

The regression suite has 34 passing checks. Actual unchanged-browser download,
restart and rendered-game observations are recorded separately in
`docs/QUALIFICATION.md`. The native engine and original-retail bridge binaries
are unchanged from 0.1.0-dev. Clients do not need an engine patch.

## 0.1.0-dev — Dedicated cross-client session

Initial native dedicated engine, original DirectPlay adapter, browser gateway,
Python administration panel, pinned-client fetcher and reproducible source /
build materials. Qualification includes simultaneous original-retail, native
and published-browser stock sessions in JK and MotS; see the recorded limits
in the qualification report.
