"""Offline monthly-input contract checks; no models, providers or persistence."""

import builtins
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import localcontext
from io import StringIO
import itertools
import json
from pathlib import Path
import socket

import pytest

from greenhome import energy_inputs
from greenhome.energy_inputs import annualise_csv


TODAY = date(2026, 10, 11)
END = "2026-09"
HEADERS = ("month", "electricity_kwh", "gas_kwh")
MONTHS = (
    "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
    "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09",
)
ROOT = Path(__file__).resolve().parents[1]


def make_csv(rows=(), headers=HEADERS, newline="\n"):
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator=newline)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def full_rows(electricity="100", gas="200"):
    return [(month, electricity, gas) for month in MONTHS]


def annualise(text, end=END, today=TODAY):
    return annualise_csv(text, end, today=today)


def test_complete_exact_contract_and_cross_year_period():
    result = annualise(make_csv(full_rows()))
    assert result == {
        "status": "complete",
        "period": {"start_month": "2025-10", "end_month": END, "expected_months": 12},
        "electricity_kwh": 1200.0,
        "gas_kwh": 2400.0,
        "purchased_kwh": 3600.0,
        "coverage": {"electricity_months": 12, "gas_months": 12},
        "missing_months": [],
        "ignored_rows": 0,
        "months": [
            {"month": month, "electricity_kwh": 100.0, "gas_kwh": 200.0}
            for month in MONTHS
        ],
        "warnings": [],
    }
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("headers", list(itertools.permutations(HEADERS)))
def test_exact_unique_headers_can_be_reordered(headers):
    rows = []
    for month in MONTHS:
        values = {"month": month, "electricity_kwh": "12", "gas_kwh": "34"}
        rows.append([values[header] for header in headers])
    result = annualise(make_csv(rows, headers=headers))
    assert result["electricity_kwh"] == 144
    assert result["gas_kwh"] == 408


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_csv_line_endings_and_optional_final_newline(newline):
    text = make_csv(full_rows(), newline=newline)
    assert annualise(text) == annualise(text.removesuffix(newline))


def test_quoted_fields_ascii_fuel_padding_and_decimal_notation():
    text = ",".join(f'"{header}"' for header in HEADERS) + "\n"
    text += "\n".join(f'"{month}"," \t1.25e+2\t ",".5"' for month in MONTHS)
    result = annualise(text)
    assert result["electricity_kwh"] == 1500
    assert result["gas_kwh"] == 6


def test_unsorted_rows_are_returned_in_calendar_order():
    assert annualise(make_csv(reversed(full_rows()))) == annualise(make_csv(full_rows()))


def test_absent_month_has_null_row_missing_label_and_reduced_coverage():
    rows = full_rows()
    rows.pop(3)
    result = annualise(make_csv(rows))
    assert result["status"] == "partial"
    assert result["electricity_kwh"] is None
    assert result["gas_kwh"] is None
    assert result["purchased_kwh"] is None
    assert result["coverage"] == {"electricity_months": 11, "gas_months": 11}
    assert result["missing_months"] == ["2026-01"]
    assert len(result["months"]) == 12
    assert result["months"][3] == {
        "month": "2026-01", "electricity_kwh": None, "gas_kwh": None,
    }
    assert len(result["warnings"]) == 2
    assert all("11/12" in warning and "not been imputed" in warning
               for warning in result["warnings"])


@pytest.mark.parametrize("blank", ["", " ", "\t", " \t "])
def test_blank_is_unknown_and_complete_other_fuel_still_has_total(blank):
    rows = full_rows()
    rows[1] = (MONTHS[1], blank, "0")
    rows[3] = (MONTHS[3], blank, "200")
    result = annualise(make_csv(rows))
    assert result["status"] == "partial"
    assert result["coverage"] == {"electricity_months": 10, "gas_months": 12}
    assert result["electricity_kwh"] is None
    assert result["gas_kwh"] == 2200
    assert result["purchased_kwh"] is None
    assert result["missing_months"] == ["2025-11", "2026-01"]
    assert result["months"][1]["electricity_kwh"] is None
    assert result["months"][1]["gas_kwh"] == 0
    assert len(result["warnings"]) == 1


def test_missing_months_is_sorted_union_of_absent_and_each_unknown_fuel():
    rows = full_rows()
    rows[1] = (MONTHS[1], "", "200")
    rows[2] = (MONTHS[2], "100", "")
    rows.pop(3)
    result = annualise(make_csv(reversed(rows)))
    assert result["missing_months"] == ["2025-11", "2025-12", "2026-01"]
    assert result["coverage"] == {"electricity_months": 10, "gas_months": 10}
    assert result["months"][3]["electricity_kwh"] is None
    assert result["months"][3]["gas_kwh"] is None


@pytest.mark.parametrize("zero", ["0", "0.0", "0e-999999", "0e999999", "00.", ".0"])
def test_twelve_explicit_zeros_are_complete_not_missing(zero):
    result = annualise(make_csv(full_rows(zero, zero)))
    assert result["status"] == "complete"
    assert result["electricity_kwh"] == result["gas_kwh"] == result["purchased_kwh"] == 0
    assert result["missing_months"] == []


def test_no_gas_is_not_inferred_from_electricity_or_blank_gas():
    result = annualise(make_csv(full_rows("100", "")))
    assert result["electricity_kwh"] == 1200
    assert result["gas_kwh"] is result["purchased_kwh"] is None
    assert result["coverage"] == {"electricity_months": 12, "gas_months": 0}
    assert result["missing_months"] == list(MONTHS)


def test_header_only_is_an_explicit_empty_partial_window():
    result = annualise(make_csv())
    assert result["status"] == "partial"
    assert result["coverage"] == {"electricity_months": 0, "gas_months": 0}
    assert result["missing_months"] == list(MONTHS)
    assert len(result["months"]) == 12
    assert result["electricity_kwh"] is result["gas_kwh"] is result["purchased_kwh"] is None


def test_no_twelve_over_n_scaling_or_nearest_available_year():
    result = annualise(make_csv([("2026-09", "5000", "9000")]))
    assert result["coverage"] == {"electricity_months": 1, "gas_months": 1}
    assert result["electricity_kwh"] is result["gas_kwh"] is result["purchased_kwh"] is None
    assert result["months"][-1]["gas_kwh"] == 9000
    assert result["missing_months"] == list(MONTHS[:-1])


def test_36_rows_and_same_month_in_different_years_never_overlap():
    rows = [
        (f"{year}-{month:02d}", str(year - 2020), str(month))
        for year in (2023, 2024, 2025)
        for month in range(1, 13)
    ]
    for year in (2023, 2024, 2025):
        result = annualise(make_csv(rows), f"{year}-12")
        assert result["status"] == "complete"
        assert result["electricity_kwh"] == (year - 2020) * 12
        assert result["gas_kwh"] == 78
        assert result["ignored_rows"] == 24
        assert len(result["warnings"]) == 1
        assert "24" in result["warnings"][0]


def test_rows_on_both_sides_of_window_are_counted_not_summed():
    text = make_csv([
        ("2025-09", "9999999", "9999999"),
        *full_rows(), ("2026-10", "9999999", "9999999"),
    ])
    result = annualise(text, today=date(2026, 11, 1))
    assert result["electricity_kwh"] == 1200
    assert result["gas_kwh"] == 2400
    assert result["ignored_rows"] == 2
    assert len(result["months"]) == 12


def test_all_rows_outside_window_do_not_supply_missing_months():
    result = annualise(make_csv([("2024-09", "1", "2")]))
    assert result["ignored_rows"] == 1
    assert result["coverage"] == {"electricity_months": 0, "gas_months": 0}
    assert result["missing_months"] == list(MONTHS)


@pytest.mark.parametrize("extra", [1, 2, 10])
def test_more_than_36_data_rows_rejected_even_if_outside_window(extra):
    rows = [
        (f"{2020 + index // 12}-{index % 12 + 1:02d}", "0", "0")
        for index in range(36 + extra)
    ]
    with pytest.raises(ValueError, match="at most 36"):
        annualise(make_csv(rows))


def test_exact_utf8_size_limit_inclusive():
    base = make_csv([("2026-09", "", "0")])
    padding = energy_inputs.MAX_CSV_BYTES - len(base.encode("utf-8"))
    text = make_csv([("2026-09", " " * padding, "0")])
    assert len(text.encode("utf-8")) == 16 * 1024
    assert annualise(text)["coverage"]["gas_months"] == 1
    with pytest.raises(ValueError, match="16 KiB"):
        annualise(text + " ")


def test_size_bound_is_bytes_not_unicode_character_count():
    text = make_csv([("2026-09", "é" * 8200, "0")])
    assert len(text) < 16 * 1024 < len(text.encode("utf-8"))
    with pytest.raises(ValueError, match="16 KiB"):
        annualise(text)


@pytest.mark.parametrize("text", [None, b"month,electricity_kwh,gas_kwh", 3, {}, [], True])
def test_csv_text_must_be_a_string(text):
    with pytest.raises(ValueError, match="csv_text must be CSV text"):
        annualise(text)


def test_invalid_utf8_surrogate_has_a_safe_validation_error():
    with pytest.raises(ValueError, match="valid UTF-8"):
        annualise(make_csv([("2026-09", "\ud800", "0")]))


@pytest.mark.parametrize("header", [
    "", "month,electricity_kwh", "month,electricity_kwh,gas_kwh,extra",
    "month,electricity_kwh,electricity_kwh",
    "month,month,gas_kwh", "month,gas_kwh,gas_kwh",
    "month,electricity_kwh,gas_kwh,gas_kwh", "Month,electricity_kwh,gas_kwh",
    " month,electricity_kwh,gas_kwh", "month,electricity_kwh,gas_kwh ",
    "\ufeffmonth,electricity_kwh,gas_kwh", "date,electricity_kwh,gas_kwh",
    "month;electricity_kwh;gas_kwh", "month,,gas_kwh",
])
def test_non_exact_duplicate_or_extra_headers_rejected(header):
    with pytest.raises(ValueError, match="headers"):
        annualise(header + "\n2026-09,1,2")


@pytest.mark.parametrize("row", [
    "2026-09,1,2,3", "2026-09,1,2,", "2026-09,1", "2026-09",
    ",1,2", ",,", "month,electricity_kwh,gas_kwh",
    "2026-09,\"1", "2026-09,\"1\"x,2", "2026-09,\"1\n\",2",
    "2026-09,\"1\r\",2", "2026-09,\"1,000\",2", "2026-09,1,000,2",
    "2026-09,1\x00,2", "2026-09,1\"2,3",
])
def test_bad_csv_records_rejected(row):
    with pytest.raises(ValueError):
        annualise(",".join(HEADERS) + "\n" + row)


@pytest.mark.parametrize("text", [
    "", "\n", " \n", "\nmonth,electricity_kwh,gas_kwh\n2026-09,1,2",
    "month,electricity_kwh,gas_kwh\n\n2026-09,1,2",
    "month,electricity_kwh,gas_kwh\n2026-09,1,2\n\n",
])
def test_empty_input_and_blank_csv_records_are_not_silently_skipped(text):
    with pytest.raises(ValueError):
        annualise(text)


@pytest.mark.parametrize("month", ["2026-09", "2024-01"])
@pytest.mark.parametrize("second", [("1", "2"), ("3", "4"), ("", "")])
def test_duplicate_months_rejected_inside_and_outside_window(month, second):
    with pytest.raises(ValueError, match="duplicate month"):
        annualise(make_csv([(month, "1", "2"), (month, *second)]))


@pytest.mark.parametrize("fuel", [1, 2], ids=["electricity", "gas"])
@pytest.mark.parametrize("value", [
    "-1", "-0", "+1", "=1+1", "=SUM(A1:A2)", "@SUM(1)", " \t=2",
    "NaN", "nan", "sNaN", "Infinity", "inf", "-inf", "1e9999",
    "10000001", "10000000.0000000001", "1e-9999",
    "1e99999999999999999999999999999", "0e99999999999999999999999999999",
    "1_000", "£5", "5 kWh", "null", "None", "true", "0x10",
    "１", "١", "1 2", ".", "1e", "1e+", "\n", "\r", "\v", "\f",
    "\u00a01\u00a0", "'1", "−1",
])
def test_invalid_fuel_values_are_rejected_in_either_column(fuel, value):
    row = ["2026-09", "1", "2"]
    row[fuel] = value
    with pytest.raises(ValueError):
        annualise(make_csv([row]))


@pytest.mark.parametrize("row", [
    ("2024-01", "=2", "1"), ("2024-01", "1", "-1"),
    ("2024-01", "NaN", "1"), ("2024-01", "10000001", "0"),
    ("2026-10", "0", "0"), ("2027-01", "0", "0"),
    ("2024-1", "0", "0"), ("1899-12", "0", "0"),
])
def test_ignored_rows_must_still_be_valid_and_completed(row):
    with pytest.raises(ValueError):
        annualise(make_csv([*full_rows(), row]))


@pytest.mark.parametrize("value", ["1", "001", "1.", ".5", "1.25", "1e2", "1E-2", "1e+2"])
def test_finite_unsigned_decimal_forms_are_accepted(value):
    result = annualise(make_csv([("2026-09", value, "0")]))
    assert result["months"][-1]["electricity_kwh"] == float(value)


def test_per_fuel_annual_limit_inclusive_combined_can_be_twice_limit():
    rows = full_rows("0", "0")
    rows[0] = (MONTHS[0], "10000000", "10000000")
    result = annualise(make_csv(rows))
    assert result["electricity_kwh"] == result["gas_kwh"] == 10_000_000
    assert result["purchased_kwh"] == 20_000_000


@pytest.mark.parametrize("fuel", [1, 2], ids=["electricity", "gas"])
@pytest.mark.parametrize("partial", [False, True], ids=["complete", "partial"])
def test_annual_sum_limit_checked_for_each_fuel_even_when_partial(fuel, partial):
    rows = [list(row) for row in full_rows("0", "0")]
    rows[0][fuel] = "6000000"
    rows[1][fuel] = "4000001"
    if partial:
        rows[-1][fuel] = ""
    with pytest.raises(ValueError, match="annual limit"):
        annualise(make_csv(rows))


@pytest.mark.parametrize("extra", ["0.0000000001", "1e-300", "5e-324"])
def test_decimal_sum_cannot_round_excess_down_to_annual_limit(extra):
    rows = full_rows("0", "0")
    rows[0] = (MONTHS[0], "10000000", "0")
    rows[1] = (MONTHS[1], extra, "0")
    with pytest.raises(ValueError, match="annual limit"):
        annualise(make_csv(rows))


def test_long_decimal_subtotal_is_exact_at_bound():
    rows = full_rows("0", "0")
    rows[0] = (MONTHS[0], "9999999." + "9" * 4000, "0")
    rows[1] = (MONTHS[1], "1e-4000", "0")
    # Positive cells that would underflow to zero must be rejected, not silently
    # used as zero to make the annual-bound comparison appear to pass.
    with pytest.raises(ValueError, match="too small"):
        annualise(make_csv(rows))


def test_decimal_arithmetic_is_independent_of_ambient_context():
    text = make_csv(full_rows("12345.6789", ".1"))
    expected = annualise(text)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        assert annualise(text) == expected
        assert context.prec == context.Emax == 2
    assert expected["electricity_kwh"] == 148148.1468
    assert expected["gas_kwh"] == 1.2
    assert expected["purchased_kwh"] == 148149.3468


@pytest.mark.parametrize("month", [
    "", "2026-9", "26-09", "202609", "2026/09", "2026-00", "2026-13",
    "2026-09-01", "2026-09T00:00:00Z", " 2026-09", "2026-09 ", "2026-09\n",
    "２０２６-09", "2026-٠٩", "0000-01", "0001-01", "1899-12", "10000-01",
    "+2026-09", "=2026-09", "NaN",
])
def test_invalid_month_format_rejected_in_end_and_rows(month):
    with pytest.raises(ValueError):
        annualise(make_csv(full_rows()), month)
    with pytest.raises(ValueError):
        annualise(make_csv([(month, "0", "0")]))


@pytest.mark.parametrize("end", [None, 202609, date(2026, 9, 1), True, {}, []])
def test_end_month_must_be_an_explicit_string(end):
    with pytest.raises(ValueError, match="end_month"):
        annualise(make_csv(full_rows()), end)


def test_end_month_argument_is_required_and_validated_before_csv_rows():
    with pytest.raises(TypeError):
        annualise_csv(make_csv(full_rows()))
    with pytest.raises(ValueError, match="end_month"):
        annualise_csv(None, "bad", today=TODAY)


@pytest.mark.parametrize("end", ["2026-10", "2026-11", "2027-01", "9999-12"])
def test_current_and_future_end_months_rejected(end):
    with pytest.raises(ValueError, match="completed calendar month"):
        annualise(make_csv(), end)


@pytest.mark.parametrize("month,last_day,next_day", [
    ("2026-09", date(2026, 9, 30), date(2026, 10, 1)),
    ("2025-12", date(2025, 12, 31), date(2026, 1, 1)),
    ("2024-02", date(2024, 2, 29), date(2024, 3, 1)),
    ("2023-02", date(2023, 2, 28), date(2023, 3, 1)),
    ("2000-02", date(2000, 2, 29), date(2000, 3, 1)),
    ("1900-02", date(1900, 2, 28), date(1900, 3, 1)),
])
def test_row_month_only_becomes_complete_on_next_calendar_month(month, last_day, next_day):
    # An older valid selected year isolates validation of the supplied row.
    if month.startswith("1900"):
        # Test this row as historical evidence in the first supported year;
        # its February still has no invented daily weighting.
        result = annualise(make_csv([(month, "7", "0")]), "1900-12", date(1901, 1, 1))
        assert result["months"][1]["electricity_kwh"] == 7
        return
    end = f"{int(month[:4]) - 1}-12"
    text = make_csv([(month, "7", "0")])
    with pytest.raises(ValueError, match="completed calendar month"):
        annualise(text, end, last_day)
    result = annualise(text, end, next_day)
    assert result["ignored_rows"] == 1


@pytest.mark.parametrize("end,before,after,start", [
    ("2026-09", date(2026, 9, 30), date(2026, 10, 1), "2025-10"),
    ("2025-12", date(2025, 12, 31), date(2026, 1, 1), "2025-01"),
    ("2024-02", date(2024, 2, 29), date(2024, 3, 1), "2023-03"),
    ("2023-02", date(2023, 2, 28), date(2023, 3, 1), "2022-03"),
])
def test_period_completion_before_and_after_midnight_boundary(end, before, after, start):
    with pytest.raises(ValueError, match="completed calendar month"):
        annualise(make_csv(), end, before)
    result = annualise(make_csv(), end, after)
    assert result["period"] == {
        "start_month": start, "end_month": end, "expected_months": 12,
    }


def test_leap_year_window_uses_months_not_365_days_or_daily_weighting():
    months = [f"2023-{month:02d}" for month in range(3, 13)] + ["2024-01", "2024-02"]
    result = annualise(
        make_csv([(month, "1", "2") for month in months]), "2024-02", date(2024, 3, 1)
    )
    assert [row["month"] for row in result["months"]] == months
    assert result["electricity_kwh"] == 12
    assert result["gas_kwh"] == 24


def test_earliest_full_supported_window_and_safe_upper_date_boundary():
    result = annualise(make_csv(), "1900-12", date(1901, 1, 1))
    assert result["period"]["start_month"] == "1900-01"
    with pytest.raises(ValueError, match="1900-12 or later"):
        annualise(make_csv(), "1900-11")
    result = annualise(make_csv([("9999-11", "0", "0")]), "9999-11", date.max)
    assert result["period"]["start_month"] == "9998-12"
    assert result["period"]["end_month"] == "9999-11"
    with pytest.raises(ValueError, match="completed calendar month"):
        annualise(make_csv(), "9999-12", date.max)
    with pytest.raises(ValueError, match="completed calendar month"):
        annualise(make_csv(), "1900-12", date.min)


@pytest.mark.parametrize("today", [
    "2026-10-11", 20261011, True, {}, datetime(2026, 10, 11),
    datetime(2026, 10, 11, tzinfo=timezone.utc),
])
def test_injected_today_must_be_a_date_not_a_datetime_or_coerced_value(today):
    with pytest.raises(ValueError, match="today must be a calendar date"):
        annualise(make_csv(), today=today)


@pytest.mark.parametrize("instant,accepted", [
    (datetime(2026, 10, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))), False),
    (datetime(2026, 9, 30, 23, 30, tzinfo=timezone(timedelta(hours=-1))), True),
])
def test_default_clock_explicitly_uses_utc_not_local_date(monkeypatch, instant, accepted):
    calls = []

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            calls.append(tz)
            assert tz is timezone.utc
            return instant.astimezone(tz)

    monkeypatch.setattr(energy_inputs, "datetime", FrozenDatetime)
    if accepted:
        assert annualise_csv(make_csv(full_rows()), END)["status"] == "complete"
    else:
        with pytest.raises(ValueError, match="completed calendar month"):
            annualise_csv(make_csv(full_rows()), END)
    assert calls == [timezone.utc]


def test_optional_today_can_be_injected_positionally():
    assert annualise_csv(make_csv(), END, TODAY) == annualise(make_csv())


def test_repeated_imports_return_fresh_independent_objects():
    text = make_csv(full_rows("100", ""))
    expected = annualise(text)
    result = annualise(text)
    result["months"][0]["gas_kwh"] = 0
    result["months"].append({})
    result["coverage"]["gas_months"] = 12
    result["period"]["end_month"] = "2026-10"
    result["missing_months"].clear()
    result["warnings"].clear()
    assert annualise(text) == expected


def test_simultaneous_imports_do_not_share_period_or_coverage_state():
    texts = [make_csv(full_rows("1", "2")), make_csv(full_rows("", "0"))] * 16
    expected = [annualise(text) for text in texts]
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(annualise, texts)) == expected


def test_old_period_does_not_become_post_completion_baseline_as_today_advances():
    text = make_csv(full_rows())
    before = annualise(text, today=date(2026, 10, 1))
    after = annualise(text, today=date(2027, 11, 1))
    assert after == before
    assert "baseline_confirmed_after_completion" not in after
    assert "baseline_status" not in after
    assert after["period"]["end_month"] == "2026-09"


def test_import_does_not_mutate_a_home_or_persist_or_contact_network(monkeypatch, tmp_path):
    home = {
        "electricity_kwh": None, "gas_kwh": None, "data_kind": "user_entered",
        "baseline_status": "needs_update", "baseline_confirmed_after_completion": False,
    }
    before = deepcopy(home)
    text = make_csv(full_rows())
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Monthly parsing must not open files or network connections.")

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(Path, "open", forbidden)
        guard.setattr(socket, "socket", forbidden)
        result = annualise(text)
    assert result["status"] == "complete"
    assert home == before
    assert list(tmp_path.iterdir()) == []


def test_invalid_text_is_not_echoed_in_validation_errors():
    sentinel = "FICTIONAL-PRIVATE-INPUT-DO-NOT-ECHO"
    for text, end in [
        (make_csv([("2026-09", sentinel, "0")]), END),
        (make_csv([(sentinel, "0", "0")]), END),
        (make_csv(headers=(sentinel, "electricity_kwh", "gas_kwh")), END),
        (make_csv(), sentinel),
    ]:
        with pytest.raises(ValueError) as error:
            annualise(text, end)
        assert sentinel not in str(error.value)


def test_fictional_example_matches_documented_fixed_seasonal_rule():
    # This is a hand-designed example, not observations or an evaluation dataset.
    profile = [8, 12, 14, 15, 13, 10, 7, 4, 2, 2, 3, 10]
    text = (ROOT / "data/monthly_energy_example.csv").read_text(encoding="utf-8")
    result = annualise(text)
    assert result["status"] == "complete"
    assert result["electricity_kwh"] == 2400
    assert result["gas_kwh"] == 10000
    assert result["purchased_kwh"] == 12400
    assert [row["month"] for row in result["months"]] == list(MONTHS)
    assert [row["electricity_kwh"] for row in result["months"]] == [
        150 + 6 * weight for weight in profile
    ]
    assert [row["gas_kwh"] for row in result["months"]] == [
        100 * weight for weight in profile
    ]
