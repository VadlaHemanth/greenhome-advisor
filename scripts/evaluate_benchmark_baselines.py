#!/usr/bin/env python3
"""Train-only type/area medians vs FROZEN VALIDATION predictions; no model fit.

Test target strings are never converted, consumed as observations or predicted.
Existing manifest/metrics are read for provenance ONLY; nothing is rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
MIN_CELL = 30  # Predeclared support threshold, NOT chosen using validation error.
FUEL_COLUMNS = {"electricity": ("Econs2024", "ElecValFlag2024"),
                "gas": ("Gcons2024", "GasValFlag2024")}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_cohorts(train_rows, fuel):
    target, flag = FUEL_COLUMNS[fuel]
    cells = {name: defaultdict(list) for name in ("type_area", "area", "type")}
    all_y = []
    for row in train_rows:
        if row["split"] != "train":
            raise ValueError("Cohort fit may only consume training rows.")
        if row[flag] != "V" or row[target] == "":
            continue
        y = float(row[target])
        if not math.isfinite(y):
            raise ValueError("Non-finite training target")
        all_y.append(y)
        for name, key in cohort_keys(row):
            cells[name][key].append(y)
    if not all_y:
        raise ValueError("No valid train-only observations")
    return {"global": median(all_y), "n_train": len(all_y),
            "cells": {name: {key: (len(ys), median(ys)) for key, ys in groups.items()}
                      for name, groups in cells.items()}}


def cohort_keys(row):
    return (("type_area", (row["PROP_TYPE"], row["FLOOR_AREA_BAND"])),
            ("area", row["FLOOR_AREA_BAND"]), ("type", row["PROP_TYPE"]))


def predict_cohort(fitted, row):
    for name, key in cohort_keys(row):
        count, value = fitted["cells"][name].get(key, (0, None))
        if count >= MIN_CELL:
            return value, name, count
    return fitted["global"], "global", fitted["n_train"]


def metrics(rows, predictor):
    errors = [r[predictor] - r["actual"] for r in rows]
    return {"n": len(errors), "mae": sum(map(abs, errors)) / len(errors) if errors else None,
            "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None,
            "bias": sum(errors) / len(errors) if errors else None}


def run():
    paths = ["data/energy_properties.csv", "data/data_manifest.json", "reports/training_metrics.json",
             "reports/validation_predictions.csv", "models/energy_benchmark.joblib",
             "scripts/evaluate_benchmark_baselines.py", "docs/EVALUATION_PROTOCOL.md"]
    before = {p: sha(ROOT / p) for p in paths}
    manifest = json.loads((ROOT / "data/data_manifest.json").read_text())
    historical = json.loads((ROOT / "reports/training_metrics.json").read_text())
    if manifest["data_kind"] != "observed_NEED2026":
        raise ValueError("This benchmark requires the observed NEED source, not synthetic fallback.")
    if before["data/energy_properties.csv"] != manifest["files"]["energy_properties.csv"]:
        raise ValueError("Prepared data hash mismatch")
    if before["data/data_manifest.json"] != historical["data_manifest_sha256"]:
        raise ValueError("Training manifest mismatch")
    for path in ("reports/validation_predictions.csv", "models/energy_benchmark.joblib"):
        if before[path] != historical["artifacts"][path]["sha256"]:
            raise ValueError(f"Frozen artifact hash mismatch: {path}")
    train, validation, seen = [], {}, set()
    skipped_test = 0
    with (ROOT / "data/energy_properties.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["model_sample"] != "True":
                continue
            # No test target/flag/feature access beyond CSV tokenization.
            if row["split"] == "test":
                skipped_test += 1
                continue
            pid = row["property_id"]
            if pid in seen:
                raise ValueError("Duplicate or overlapping training/validation property")
            seen.add(pid)
            if row["split"] == "train":
                train.append(row)
            elif row["split"] == "validation":
                validation[pid] = row
            else:
                raise ValueError("Unexpected split")
    frozen = {}
    with (ROOT / "reports/validation_predictions.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if not row["task"].startswith("energy_"):
                continue
            if row["split"] != "validation":
                raise ValueError("Non-validation row in validation predictions")
            key = (row["task"].removeprefix("energy_"), row["property_id"])
            if key in frozen:
                raise ValueError("Duplicate frozen prediction")
            frozen[key] = row
    predictions, results, slices, cohort_tables = [], {}, [], []
    expected_keys = set()
    for fuel, (target, flag) in FUEL_COLUMNS.items():
        fitted = fit_cohorts(train, fuel)
        for name, cells in fitted["cells"].items():
            cohort_tables.extend({"fuel": fuel, "cohort": name, "key": key, "n_train": n, "median_kwh": value,
                                  "eligible": n >= MIN_CELL} for key, (n, value) in cells.items())
        rows = []
        for pid, row in validation.items():
            if not row[target]:
                continue
            if row[flag] != "V":
                raise ValueError("Non-V validation target")
            expected_keys.add((fuel, pid))
            old = frozen[(fuel, pid)]
            actual = float(row[target])
            if actual != float(old["actual"]):
                raise ValueError("Frozen validation target mismatch")
            if float(old["baseline_predicted"]) != fitted["global"]:
                raise ValueError("Recomputed global train median disagrees with historical baseline")
            cohort, level, n = predict_cohort(fitted, row)
            other_flag = FUEL_COLUMNS["gas" if fuel == "electricity" else "electricity"][1]
            result = {"fuel": fuel, "property_id": pid, "split": "validation", "actual": actual,
                      "existing_model": float(old["predicted"]), "global_median": fitted["global"],
                      "type_area_median": cohort, "fallback_level": level, "cohort_n_train": n,
                      **{k: row[k] for k in ("EPC", "REGION", "PROP_TYPE", "FLOOR_AREA_BAND")},
                      "other_fuel_availability": "both_valid" if row[other_flag] == "V" else "other_fuel_not_valid",
                      "epc_availability": "missing_epc" if row["EPC"] == "No EPC" else "recorded_epc"}
            rows.append(result)
        results[fuel] = {"n_train": fitted["n_train"], "n_validation": len(rows),
                         "strategies": {p: metrics(rows, p) for p in ("existing_model", "global_median", "type_area_median")},
                         "fallback_counts": dict(Counter(r["fallback_level"] for r in rows))}
        for field in ("EPC", "REGION", "PROP_TYPE", "FLOOR_AREA_BAND", "other_fuel_availability", "epc_availability"):
            for value in sorted({r[field] for r in rows}):
                group = [r for r in rows if r[field] == value]
                slices.append({"fuel": fuel, "slice": field, "value": value, "n": len(group),
                               "strategies": {p: metrics(group, p) for p in ("existing_model", "global_median", "type_area_median")}})
        predictions.extend(rows)
    if set(frozen) != expected_keys:
        raise ValueError("Frozen validation prediction membership mismatch")
    after = {p: sha(ROOT / p) for p in paths}
    if before != after:
        raise ValueError("Input/source changed during run; rerun required.")
    report = {
        "status": "completed", "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "VALIDATION ONLY retrospective observed annual-consumption association, NOT retrofit savings or prospective forecasting.",
        "policy": f"Train V targets only; type+area median if n>={MIN_CELL}, then area, type, global. Fixed before results.",
        "candidate_source": "Hash-verified frozen validation_predictions.csv from existing energy_benchmark.joblib; no reload/refit/retraining.",
        "test_policy": "Test rows skipped before target conversion; no test predictions file opened, metrics computed, tuning or model selection.",
        "train_properties": len(train), "validation_properties": len(validation), "test_rows_skipped": skipped_test,
        "prediction_rows": len(predictions), "input_hashes_before": before, "input_hashes_after": after,
        "results": results, "slices": slices,
        "limitations": [
            "Latest EPC/property snapshot can post-date targets; not time-safe.",
            "Fuel quality inclusion is separate; missing gas is not zero.",
            "Electricity/gas periods differ, and only gas is weather corrected.",
            "Anonymous row IDs do not establish independent customers.",
            "Slices overlap and have unequal support; no significance or calibrated uncertainty claim.",
            "No historical model or saved metrics modified; this diagnostic cannot justify tuning on old test data.",
        ],
    }
    path = ROOT / "reports/benchmark_baselines.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (ROOT / "reports/benchmark_baselines_cohorts.json").write_text(json.dumps(cohort_tables, indent=2) + "\n")
    with (ROOT / "reports/benchmark_baselines_validation.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    lines = ["# Train-only cohort baseline — validation only", "",
             "Observed NEED annual consumption, **not retrofit savings**. No retraining or test evaluation.", "",
             "| Fuel | Strategy | n validation | MAE kWh | RMSE kWh | Bias kWh |",
             "|---|---|---:|---:|---:|---:|"]
    for fuel, result in results.items():
        for strategy, m in result["strategies"].items():
            lines.append(f"| {fuel} | {strategy} | {m['n']} | {m['mae']:.2f} | {m['rmse']:.2f} | {m['bias']:.2f} |")
    lines += ["", "All EPC, region, property-type, area and availability slices (including worse/small slices) are in JSON.",
              "Fixed n≥30 fallback: type+area → area → type → global; every median uses training targets only.",
              "Models are represented by their hash-verified frozen validation predictions; no new test results or tuning.",
              "Bias = predicted − observed. Different fuel reporting periods and retrospective EPC/snapshot limitations remain."]
    (ROOT / "reports/benchmark_baselines.md").write_text("\n".join(lines) + "\n")
    return report


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = run()
    print(json.dumps({"status": result["status"], "prediction_rows": result["prediction_rows"],
                      "results": result["results"]}, indent=2))
