"""Strict, in-memory annual totals from an explicitly selected monthly CSV.

No scaling, imputation, model calls, home updates or persistence. See
docs/ENERGY_INPUTS.md for the caller and frontend contract.
"""

import csv
from datetime import date, datetime, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from io import StringIO
import re


MAX_CSV_BYTES = 16 * 1024
MAX_ROWS = 36
MAX_ANNUAL_KWH = 10_000_000

_HEADERS = ("month", "electricity_kwh", "gas_kwh")
_MONTH = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])")
_NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_FIRST_MONTH = 1900 * 12
# Enough significant digits for the entire bounded CSV plus the exponent range
# of nonzero finite floats. Summation must not round an over-limit subtotal down
# to the limit, or depend on a caller's ambient decimal context.
_SUM_CONTEXT = Context(prec=MAX_CSV_BYTES + 400)


def _month_index(value: str, label: str) -> int:
    if (
        not isinstance(value, str)
        or len(value) != 7
        or _MONTH.fullmatch(value) is None
        or int(value[:4]) < 1900
    ):
        raise ValueError(f"{label} must be YYYY-MM with a year from 1900 to 9999.")
    return int(value[:4]) * 12 + int(value[5:]) - 1


def _month_label(index: int) -> str:
    year, month = divmod(index, 12)
    return f"{year:04d}-{month + 1:02d}"


def _utc_today(today: date | None) -> date:
    if today is None:
        return datetime.now(timezone.utc).date()
    if not isinstance(today, date) or isinstance(today, datetime):
        raise ValueError("today must be a calendar date representing UTC today.")
    return today


def _energy(value: str, row_number: int, fuel: str) -> Decimal | None:
    text = value.strip(" \t")
    if not text:
        return None
    message = (
        f"Row {row_number}: {fuel} must be a finite unsigned decimal "
        f"from 0 to {MAX_ANNUAL_KWH} kWh, or blank if unknown."
    )
    if _NUMBER.fullmatch(text) is None:
        raise ValueError(message)
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(message) from None
    if not number.is_finite() or not 0 <= number <= MAX_ANNUAL_KWH:
        raise ValueError(message)
    if number == 0:
        # Normalise zero exponents before arithmetic (e.g. 0e-999999).
        return Decimal(0)
    if float(number) == 0:
        raise ValueError(
            f"Row {row_number}: {fuel} is too small to represent as a nonzero number."
        )
    return number


def annualise_csv(
    csv_text: str, end_month: str, today: date | None = None
) -> dict:
    """Return checked totals for the 12 calendar months ending at ``end_month``.

    ``today`` is an optional UTC calendar date for deterministic tests; production
    callers omit it. Invalid input raises ``ValueError`` without reflecting cell
    contents. Dates and headers are exact; fuel cells may have surrounding ASCII
    spaces/tabs. Blank cells and absent rows remain unknown, not zero.
    """
    # Validate the requested period before interpreting any supplied rows.
    end = _month_index(end_month, "end_month")
    start = end - 11
    if start < _FIRST_MONTH:
        raise ValueError("end_month must be 1900-12 or later for a full 12-month window.")
    current_date = _utc_today(today)
    current = current_date.year * 12 + current_date.month - 1
    if end >= current:
        raise ValueError("end_month must be a completed calendar month in UTC.")

    if not isinstance(csv_text, str):
        raise ValueError("csv_text must be CSV text, not a file, URL or other value.")
    if len(csv_text) > MAX_CSV_BYTES:
        raise ValueError("csv_text must not exceed 16 KiB (16384 UTF-8 bytes).")
    try:
        byte_count = len(csv_text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("csv_text must be valid UTF-8 text.") from None
    if byte_count > MAX_CSV_BYTES:
        raise ValueError("csv_text must not exceed 16 KiB (16384 UTF-8 bytes).")

    rows: dict[int, tuple[Decimal | None, Decimal | None]] = {}
    reader = csv.reader(StringIO(csv_text, newline=""), strict=True)
    try:
        header = next(reader, None)
        if header is None or len(header) != 3 or set(header) != set(_HEADERS):
            raise ValueError(
                "CSV headers must be exactly month, electricity_kwh, gas_kwh, "
                "once each (any order)."
            )
        columns = {name: header.index(name) for name in _HEADERS}
        for row_number, row in enumerate(reader, start=2):
            if row_number > MAX_ROWS + 1:
                raise ValueError("CSV must contain at most 36 data rows.")
            if len(row) != 3:
                raise ValueError(f"Row {row_number}: exactly three columns are required.")
            month = _month_index(row[columns["month"]], f"Row {row_number}: month")
            if month >= current:
                raise ValueError(
                    f"Row {row_number}: month must be a completed calendar month in UTC."
                )
            if month in rows:
                raise ValueError(f"Row {row_number}: duplicate month is not allowed.")
            rows[month] = (
                _energy(row[columns["electricity_kwh"]], row_number, "electricity_kwh"),
                _energy(row[columns["gas_kwh"]], row_number, "gas_kwh"),
            )
    except csv.Error:
        raise ValueError("CSV is malformed; check delimiters and quoting.") from None

    months = []
    missing_months = []
    coverage = {"electricity_months": 0, "gas_months": 0}
    sums = {"electricity_kwh": Decimal(0), "gas_kwh": Decimal(0)}
    ignored_rows = sum(not start <= month <= end for month in rows)

    with localcontext(_SUM_CONTEXT):
        for month in range(start, end + 1):
            values = rows.get(month, (None, None))
            label = _month_label(month)
            record = {"month": label}
            if None in values:
                missing_months.append(label)
            for fuel, coverage_key, value in zip(
                _HEADERS[1:], coverage, values, strict=True
            ):
                record[fuel] = None if value is None else float(value)
                if value is not None:
                    coverage[coverage_key] += 1
                    sums[fuel] += value
                    # A partial known subtotal cannot already exceed the annual
                    # domain, even though its final annual total will be null.
                    if sums[fuel] > MAX_ANNUAL_KWH:
                        raise ValueError(
                            f"Selected-period {fuel} exceeds the annual limit "
                            f"of {MAX_ANNUAL_KWH} kWh."
                        )
            months.append(record)

        totals = {
            fuel: float(sums[fuel]) if count == 12 else None
            for fuel, count in zip(_HEADERS[1:], coverage.values(), strict=True)
        }
        complete = all(count == 12 for count in coverage.values())
        purchased = float(sum(sums.values())) if complete else None

    warnings = []
    if ignored_rows:
        warnings.append(
            f"Ignored {ignored_rows} supplied row(s) outside the selected 12-month period."
        )
    for fuel, count in coverage.items():
        if count < 12:
            warnings.append(
                f"{fuel.removesuffix('_months').capitalize()}: {count}/12 months known; "
                "annual total is unavailable. Missing values have not been imputed."
            )

    return {
        "status": "complete" if complete else "partial",
        "period": {
            "start_month": _month_label(start),
            "end_month": _month_label(end),
            "expected_months": 12,
        },
        **totals,
        "purchased_kwh": purchased,
        "coverage": coverage,
        "missing_months": missing_months,
        "ignored_rows": ignored_rows,
        "months": months,
        "warnings": warnings,
    }
