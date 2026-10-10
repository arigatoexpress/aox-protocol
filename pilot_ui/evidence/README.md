# Synthetic demo evidence

Captured locally on 2026-10-08 using the checked-in browser smoke script and Python
standard-library tests. All task receipts, offers, outcomes and UI activity are synthetic.
They are not a live marketplace or adoption evidence.

Screenshots are not included in this public snapshot.

- `synthetic-pass.json`: exported fixture receipt, including Unicode/script-like text
  handled only as literal data. Hashes are not signatures or proof of real execution.
- `devlog-draft.txt`: generated from that exact receipt using `pilot_ui.draft_devlog`.
- `baseline-tests.txt`: 37 existing tests passed.
- `pilot-tests.txt`: 13 pilot tests passed.
- `browser-tests.txt`: desktop/mobile and imported-receipt regression smoke results.

A separate reviewer found three issues and independently verified their fixes: truthful
failure/falsy-output rendering, quote-time offer evidence, and bounded socket reads.
The reviewer reran 13 tests and eight imported-receipt browser cases.

The GitHub workflow now explicitly checks the 37 baseline tests, all 13 pilot tests,
deterministic simulator output and a reproducible receipt-to-draft CLI run. Browser
results remain local only; hosted CI does not install or run Playwright.

## CSV local tool evidence

`csv-receipt.json` and `normalized.csv` are actual browser-generated outputs for a
clearly labeled synthetic sample. They are not marketplace or provider receipts.
Input and output are intentionally public synthetic inventory data.

`csv-tests.txt` records six Node test groups (including a 2,000-case deterministic
malformed-parser agreement corpus); `csv-browser-tests.txt` records local browser
acceptance, including no CSV data requests/storage. An independent reviewer found
and verified the uploaded-file line-ending fix: receipt hashes now retain original
CRLF input bytes and bare-CR files are rejected. Browser tests remain local
evidence; hosted CI also explicitly runs the dependency-free Node CSV suite.
