# Checked monthly energy inputs

Team **225**; England and Wales pilot, UK units, GBP where relevant. This
helper converts supplied monthly **kWh**, not prices or meter-register readings,
to checked annual inputs. Electricity means grid imports, not generation,
exports or underlying demand; gas means consumed gas on the engine's gross-CV
kWh basis. Do not upload addresses, account numbers or personal bill documents.

## Requirement and scope

The original **Problem Statement 2, section 9, page 4**, requires consistent
annualisation of available monthly usage and explicit treatment of missing
months/fields rather than defaulting them to zero. Section 2 calls for annualised
metered energy per square metre; section 3 defines purchased energy as grid
electricity imports plus gas consumption. The local original-PS extracts at
`work/project-comparison/problem.txt` and
`work/audit-2026-10-10/problem.txt` were inspected.

The agreed implementation deliberately **abstains** when a fuel lacks a full
12-month baseline. It does not use `12 / n`, seasonally impute, fabricate monthly
observations from NEED annual data, or change the scoring/model interfaces.
The exact integration shape is in `docs/INTEGRATED_BUILD_CONTRACT.md`.
Earlier annual-only scope descriptions in other documents predate this helper;
their updates and API/frontend wiring belong to the parent, not this change.

## Python interface

```python
from datetime import date
from greenhome.energy_inputs import annualise_csv

preview = annualise_csv(
    csv_text,
    end_month="2026-09",
    today=date(2026, 10, 11),  # Optional test-only UTC calendar date.
)
```

`annualise_csv(csv_text: str, end_month: str, today: date | None = None) -> dict`
is pure, apart from reading the UTC clock if `today` is omitted. Production
callers omit `today`; never expose a client-controlled clock in the HTTP body.
An injected `today` must be a `date`, not a string or `datetime`.

Invalid input raises `ValueError` with a short, non-reflective message. Messages
may name a row number or known field but do not echo uploaded cells. A missing
required Python argument has the usual `TypeError`. The parent should translate
input validation failures to the API's validation response, not a successful
partial result.

### Strict input rules

- At most **16 KiB = 16,384 UTF-8 bytes**, inclusive, for the complete CSV text.
  This is a byte limit, not a Unicode-character limit. Invalid UTF-8 surrogate
  text is rejected. JSON transport overhead is separate and owned by the API.
- **0–36 data records**, excluding the header. A header-only file is a valid
  all-unknown preview. Empty input is invalid. Blank CSV records are invalid,
  not silently skipped; a single ordinary final line ending is fine.
- Exactly three unique, case-sensitive header names:
  `month,electricity_kwh,gas_kwh`. Any column order is allowed, but no extra,
  missing, duplicated, whitespace-padded or BOM-prefixed header is accepted.
  Do not add a fictional-data label as a fourth column or comment row.
- Standard comma-delimited CSV quoting and LF, CRLF or CR line endings are
  supported. Malformed quoting, missing/extra columns and embedded line breaks
  inside values are rejected. There is no delimiter guessing or locale repair.
- `end_month` is **required** and validated before CSV interpretation. All input
  months use exactly ASCII `YYYY-MM`, without padding, day, time or timezone.
  Input years are 1900–9999; the entire selected window must remain in that
  range, so the earliest supported `end_month` is **1900-12**.
- The selected period consists of exactly 12 consecutive calendar months,
  ending inclusively at `end_month`. For `2026-09` it is `2025-10`–`2026-09`.
  There is no 365-day approximation, leap-day scaling, fiscal-year inference,
  automatic latest-period selection or substitution of an older complete year.
- Both `end_month` and **every supplied row**, including ignored rows, must
  precede the current UTC calendar month. A month becomes complete on the first
  day of the next month at 00:00 UTC, not at the beginning of its last day.
  Example: September 2026 is not accepted on 30 September 2026 UTC and is
  accepted on 1 October 2026 UTC. Historical completed periods remain selectable.
- Duplicate `YYYY-MM` rows are rejected across the entire upload, even if their
  values agree or they are outside the window. January in different years is
  not a duplicate. Input order does not affect the output.
- Fuel cells are unsigned ASCII decimal numbers, optionally with a decimal
  point and scientific exponent. Surrounding ASCII spaces/tabs are permitted.
  `0`, `.5`, `1.25`, `1e2`, and `1e-2` are valid. Leading `+` or `-` (including
  `-0`), formulas, `NaN`, infinities, currency/units, grouping commas, underscores,
  Unicode digits and textual `null`/`None` are rejected. No cell is evaluated.
- A blank or space/tab-only fuel cell is **unknown**. Only explicit numeric
  zero is zero; unknown gas does not confirm a no-gas home.
- Each supplied number and each selected-period **per-fuel known subtotal**
  must lie in **0–10,000,000 kWh inclusive**. Reject a subtotal above the limit
  even if that fuel has missing months. Two individually valid fuels may sum
  to 20,000,000 purchased kWh; the engine limit is per fuel, not combined.
  Decimal arithmetic checks exact supplied values and sums before conversion
  to finite JSON-compatible floats. A nonzero value that would underflow to
  float zero is rejected, never silently treated as an explicit zero.
- Rows outside the selected window are validated and counted, but not summed.
  Their aggregate is not an annual baseline. Invalid ignored rows invalidate
  the whole request; there is no best-effort partial parsing.
- No arbitrary path, URL, remote file or spreadsheet ingestion.

## Return contract and frontend handoff

Every successful result has **exactly** these keys:

```text
{
  status: "complete" | "partial",
  period: {
    start_month: "YYYY-MM",
    end_month: "YYYY-MM",
    expected_months: 12
  },
  electricity_kwh: number | null,
  gas_kwh: number | null,
  purchased_kwh: number | null,
  coverage: {electricity_months: integer, gas_months: integer},
  missing_months: ["YYYY-MM", ...],
  ignored_rows: integer,
  months: [
    {month: "YYYY-MM", electricity_kwh: number | null, gas_kwh: number | null},
    ... exactly 12, in ascending calendar order
  ],
  warnings: [plain_string, ...]
}
```

- `complete` means both fuels have **12 known values**, including explicit
  zeroes. It does not mean verified, current-for-a-retrofit, or saved.
- Each annual fuel total is the sum **only if that fuel has all 12 months**.
  Otherwise that total is `null`; do not display the known subtotal as annual.
  The other fuel may still have a valid total.
- `purchased_kwh` is available only if both annual fuel totals are available.
- Coverage counts known cells separately per fuel, never the number of rows.
- A wholly absent month is emitted with **both fuel values `null`**.
- `missing_months` is the chronologically ordered **union of months with any
  unknown fuel**, including absent rows and present rows with either blank cell.
  It is not limited to absent CSV records. Use `months` to identify which fuel
  is unknown. Thus a complete electricity series and a blank gas value can
  legitimately give `electricity_months: 12` and nonempty `missing_months`.
- `ignored_rows` is the count of valid supplied rows outside the selected
  period. A nonzero count always has an explanatory warning.
- There is one warning for each incomplete fuel, including its `n/12` coverage
  and non-imputation. A complete result with no ignored rows has no warnings.
  UI logic should consume structured fields rather than parse warning prose.

The parent owns `POST /api/energy-inputs`, accepting only
`{"csv_text": "...", "end_month": "YYYY-MM"}`. This module does **not** create
that route. The frontend should preview the selected period, coverage, warnings
and actual supplied monthly values, showing unknowns as gaps—not zero-height
observations. Every displayed figure must come from this result.

The user must explicitly **Apply annual inputs** after preview. Apply each fuel's
returned value, **including `null`**; do not use `value || previousValue`,
null-coalescing to a stale baseline, or zero defaults. Keep own-home
`data_kind="user_entered"`; importing does not create an observed-government or
synthetic-property valuation entitlement. Recompute through the existing engine
after explicit application. File selection or a successful preview alone must
not update a home, trigger model/provider calls, or write workspace records.

### Completion history and stale baseline safeguards

This helper has no retrofit history and cannot certify a post-completion
baseline. A September 2026 end period still describes October 2025–September
2026 when imported in November 2027; waiting does not refresh old consumption.
`status="complete"` is a coverage statement only.

Preserve the existing `docs/WORKSPACE_MEMORY.md` completion rules:

1. Completion invalidates both annual fuel inputs and marks the baseline
   `needs_update`. This helper must not alter that state.
2. Do not automatically set `baseline_confirmed_after_completion`, clear
   `needs_update`, or save uploaded monthly rows.
3. In the caller's review, a wholly pre-completion or overlapping period must
   not be represented as a full post-completion baseline. Monthly totals cannot
   split a month around the actual completion day. Show the period and
   completion history and retain the explicit confirmation workflow; full
   coverage alone is insufficient evidence of a post-work baseline.
4. Partial imported annual totals remain unknown and cannot confirm a full
   replacement baseline. Even a wholly later complete period still requires
   explicit application/confirmation; the parser verifies format, not a bill.

No automatic persistence, browser storage, logging of CSV text, training,
LLM/API calls or secrets are involved in this helper. Temporary transport and
preview data should remain temporary; workspace policy is separately owned.

## Fictional example and reproducibility

`data/monthly_energy_example.csv` is a **fictional, hand-designed seasonal
example**, not NEED, EPC, smart-meter, government or customer observations.
Its fixed dates are **October 2025–September 2026**; do not silently roll them
forward as time passes. Load it with `end_month="2026-09"` and label it
“Fictional monthly example” in the UI before showing/applying its numbers.

There is **no random generator and no random seed**. The complete deterministic
generation rule is:

- Iterate the 12 months from `2025-10` through `2026-09` in order.
- Associate fixed illustrative seasonal weights
  `[8, 12, 14, 15, 13, 10, 7, 4, 2, 2, 3, 10]` in that order (sum **100**).
- Monthly electricity kWh = `150 + 6 * weight`.
- Monthly gas kWh = `100 * weight`.

Consequently the fixture sums to **2,400 electricity kWh**, **10,000 gas kWh**
and **12,400 purchased kWh**. The winter/summer shape is an authored
illustration, not an empirically estimated seasonal model. Do not use it to
impute missing real months, retrain models, or claim external validation.

## Validation

Focused tests:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_energy_inputs.py -p no:cacheprovider -q
```

The suite checks exact shape, missing/blank/zero distinctions, both independent
fuel totals, duplicate rows/headers, all CSV limits, ignored-row validation,
annual bounds and decimal boundary cases, UTC month completion, cross-year and
leap-year windows, supported date boundaries, repeated/concurrent calls, no
implicit home/file/network mutation, and the exact fictional generation rule.
The historical-period check proves no automatic redating or confirmation; it
is **not** a test of the parent-owned route or frontend/workspace integration.
Only actually executed results should be reported as passing.

### Executed checks — 11 October 2026

- Focused command above: **246 passed, 0 failed** in 0.63 seconds.
- Required backend regression:

  ```bash
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_engine.py tests/test_engine_audit.py tests/test_ml.py tests/test_explain.py tests/test_api.py -k "not apptest" -p no:cacheprovider -q
  ```

  **330 passed, 0 failed** in 9.90 seconds.
- Combined test count across those two runs: **576 passed, 0 failed**.
- An additional read-only audit compiled the two owned Python files in memory,
  checked final newlines/trailing whitespace, verified the parser imports only
  the standard library, and checked the fixture has one header plus 12 rows and
  a finite JSON-serialisable result with the documented 2,400/10,000/12,400 totals.

These were offline local checks in the existing `.venv`, with bytecode and
pytest-cache writes disabled. No retraining, provider call, deployment, commit
or submission was performed by this worker. Parent-owned integration can change
independently; the counts describe these actual runs, not a future release.
