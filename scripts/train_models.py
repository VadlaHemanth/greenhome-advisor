#!/usr/bin/env python3
"""Train fixed-configuration models; report untouched property holdout metrics."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_pinball_loss, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from greenhome.ml import ENERGY_FEATURES, RETROFIT_IDS, SEED, VALUE_CATEGORICAL, VALUE_NUMERIC, value_quantile_predictions

DATA, MODELS, REPORTS = ROOT / "data", ROOT / "models", ROOT / "reports"
ENERGY_PARAMETERS = dict(n_estimators=128, min_samples_leaf=15, max_depth=18,
                         max_features=.85, random_state=SEED, n_jobs=2)
VALUE_PARAMETERS = dict(n_estimators=170, learning_rate=.055, max_depth=3,
                        min_samples_leaf=20, random_state=SEED)


def regression_metrics(actual, predicted) -> dict:
    return {"mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))), "n": int(len(actual))}


def split_audit(frame: pd.DataFrame) -> dict:
    ids = {split: set(frame.loc[frame.split == split, "property_id"]) for split in ("train", "validation", "test")}
    overlaps = {f"{a}_{b}": len(ids[a] & ids[b]) for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    if any(overlaps.values()):
        raise ValueError(f"Property leakage detected: {overlaps}")
    if any(not value for value in ids.values()):
        raise ValueError("Empty property split.")
    return {"unique_properties": {s: len(v) for s, v in ids.items()},
            "row_counts": frame.split.value_counts().to_dict(), "property_overlap": overlaps}


def energy_pipeline(estimator) -> Pipeline:
    return Pipeline([("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                     ("model", estimator)])


def train_energy(frame: pd.DataFrame, manifest: dict, predictions: dict) -> dict:
    full_audit = split_audit(frame)
    frame = frame.loc[frame.model_sample].copy()
    bundle = {"data_kind": manifest["data_kind"], "features": ENERGY_FEATURES, "models": {},
              "seed": SEED, "sklearn_version": sklearn.__version__}
    result = {"data_kind": manifest["data_kind"], "target_year": 2024, "units": "kWh/year",
              "algorithm": "ExtraTreesRegressor trained on log1p(target), expm1 inverse",
              "fixed_parameters": ENERGY_PARAMETERS, "features": list(ENERGY_FEATURES),
              "baseline": "DummyRegressor(strategy='median') fitted on train only",
              "full_data_audit": full_audit, "sample_audit": split_audit(frame), "targets": {}}
    for fuel, column in (("electricity", "Econs2024"), ("gas", "Gcons2024")):
        observed = frame.loc[frame[column].notna()].copy()
        target_result = {"target": column, "row_counts": observed.split.value_counts().to_dict(),
                         "missing_excluded_in_sample": int(frame[column].isna().sum())}
        train = observed.loc[observed.split == "train"]
        x_train, y_train = train[list(ENERGY_FEATURES)], train[column].to_numpy(float)
        estimator = TransformedTargetRegressor(regressor=ExtraTreesRegressor(**ENERGY_PARAMETERS),
                                               func=np.log1p, inverse_func=np.expm1)
        model = energy_pipeline(estimator)
        dummy = energy_pipeline(DummyRegressor(strategy="median"))
        start = time.perf_counter()
        model.fit(x_train, y_train)
        dummy.fit(x_train, y_train)
        target_result["fit_seconds"] = round(time.perf_counter() - start, 4)
        bundle["models"][fuel] = model
        bundle.setdefault("baselines", {})[fuel] = dummy
        for split in ("validation", "test"):
            held = observed.loc[observed.split == split]
            x, y = held[list(ENERGY_FEATURES)], held[column].to_numpy(float)
            pred, baseline = model.predict(x), dummy.predict(x)
            target_result[split] = {"model": regression_metrics(y, pred),
                                    "dummy_median": regression_metrics(y, baseline)}
            target_result[split]["mae_improvement_percent_vs_dummy"] = float(
                100 * (1 - target_result[split]["model"]["mae"] / target_result[split]["dummy_median"]["mae"]))
            predictions[split].append(pd.DataFrame({
                "task": f"energy_{fuel}", "data_kind": manifest["data_kind"],
                "property_id": held.property_id.to_numpy(), "scenario_id": "",
                "split": split, "unit": "kWh/year", "actual": y, "predicted": pred,
                "baseline_predicted": baseline,
            }))
        result["targets"][fuel] = target_result
        print(f"ENERGY {fuel}: " + json.dumps(target_result), flush=True)
    joblib.dump(bundle, MODELS / "energy_benchmark.joblib", compress=3)
    return result


def value_pipeline(alpha: float) -> Pipeline:
    preprocess = ColumnTransformer([
        ("categories", OneHotEncoder(handle_unknown="ignore", sparse_output=False), list(VALUE_CATEGORICAL)),
        ("numbers", "passthrough", list(VALUE_NUMERIC)),
    ])
    return Pipeline([("encode", preprocess),
                     ("model", GradientBoostingRegressor(loss="quantile", alpha=alpha, **VALUE_PARAMETERS))])


def train_value(frame: pd.DataFrame, predictions: dict) -> dict:
    result = {"data_kind": "synthetic_hypothetical_NOT_market_calibrated",
              "algorithm": "Three GradientBoostingRegressor quantile models; p10/p50/p90",
              "fixed_parameters": VALUE_PARAMETERS, "quantiles": [.1, .5, .9],
              "nominal_interval_coverage": .8, "coverage_scope": "Synthetic references only; no real causal/market coverage claim.",
              "features": list(VALUE_CATEGORICAL + VALUE_NUMERIC), "split_audit": split_audit(frame),
              "postprocessing": "Sort crossed quantiles; force no-intervention predictions to exact zero. No interval tuning/calibration.",
              "baseline": "Train-set global median, with same exact-zero no-op identity."}
    features = list(VALUE_CATEGORICAL + VALUE_NUMERIC)
    train = frame.loc[frame.split == "train"]
    bundle = {"data_kind": result["data_kind"], "models": {}, "seed": SEED,
              "features": features, "sklearn_version": sklearn.__version__}
    start = time.perf_counter()
    for name, alpha in (("p10", .1), ("p50", .5), ("p90", .9)):
        model = value_pipeline(alpha)
        model.fit(train[features], train.impact_percent)
        bundle["models"][name] = model
        print(f"VALUE trained {name}: {len(train)} synthetic train scenarios", flush=True)
    result["fit_seconds"] = round(time.perf_counter() - start, 4)
    median = float(train.impact_percent.median())
    bundle["dummy_median_percent"] = median
    for split in ("validation", "test"):
        held = frame.loc[frame.split == split]
        x = held[features]
        y = held.impact_percent.to_numpy(float)
        p = value_quantile_predictions(bundle, x)
        noop = x[list(RETROFIT_IDS)].sum(axis=1).to_numpy() == 0
        baseline = np.where(noop, 0, median)
        covered = (y >= p[:, 0]) & (y <= p[:, 2])
        group_coverage = pd.DataFrame({"property_id": held.property_id.to_numpy(), "covered": covered}).groupby("property_id").covered.all()
        m = {"p50_percent": regression_metrics(y, p[:, 1]),
             "dummy_median_percent": regression_metrics(y, baseline),
             "p50_gbp": regression_metrics(held.impact_gbp, p[:, 1] * held.current_value_gbp.to_numpy() / 100),
             "coverage_p10_p90_all_scenarios": float(covered.mean()),
             "coverage_p10_p90_active_scenarios": float(covered[~noop].mean()),
             "property_all_scenarios_covered_fraction": float(group_coverage.mean()),
             "mean_interval_width_percentage_points": float(np.mean(p[:, 2] - p[:, 0])),
             "active_mean_interval_width_percentage_points": float(np.mean((p[:, 2] - p[:, 0])[~noop])),
             "pinball_loss": {name: float(mean_pinball_loss(y, p[:, i], alpha=alpha))
                              for i, (name, alpha) in enumerate((("p10", .1), ("p50", .5), ("p90", .9)))},
             "no_op_rows": int(noop.sum()), "active_rows": int((~noop).sum()),
             "no_op_exact_zero": bool(np.all(p[noop] == 0) and np.all(y[noop] == 0)),
             "intervals_ordered": bool(np.all(p[:, 0] <= p[:, 1]) and np.all(p[:, 1] <= p[:, 2]))}
        result[split] = m
        predictions[split].append(pd.DataFrame({
            "task": "synthetic_value_impact", "data_kind": result["data_kind"],
            "property_id": held.property_id.to_numpy(), "scenario_id": held.scenario_id.to_numpy(),
            "split": split, "unit": "percentage_points", "actual": y, "predicted": p[:, 1],
            "baseline_predicted": baseline, "p10": p[:, 0], "p50": p[:, 1], "p90": p[:, 2],
            "current_value_gbp": held.current_value_gbp.to_numpy(),
            "reference_before_gbp": held.reference_before_gbp.to_numpy(),
            "reference_after_gbp": held.reference_after_gbp.to_numpy(),
            "actual_gbp": held.impact_gbp.to_numpy(), "predicted_gbp": p[:, 1] * held.current_value_gbp.to_numpy() / 100,
            "no_op": noop,
        }))
        print(f"VALUE {split}: " + json.dumps(m), flush=True)
    joblib.dump(bundle, MODELS / "synthetic_value.joblib", compress=3)
    return result


def main():
    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    manifest = json.loads((DATA / "data_manifest.json").read_text())
    # Detect stale/corrupted preparations rather than training unidentified inputs.
    for name, expected in manifest["files"].items():
        actual = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Prepared data hash mismatch: {name}")
    energy = pd.read_csv(DATA / "energy_properties.csv", dtype={column: str for column in ENERGY_FEATURES})
    value = pd.read_csv(DATA / "synthetic_value_scenarios.csv")
    start = time.perf_counter()
    predictions = {"validation": [], "test": []}
    metrics = {"status": "completed", "trained_at_utc": datetime.now(timezone.utc).isoformat(), "seed": SEED,
               "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                            "numpy": np.__version__, "pandas": pd.__version__, "joblib": joblib.__version__},
               "methodology": "Fixed configurations decided before fitting. Train-only preprocessing and models. No test tuning, no selection on test, no train+validation refit.",
               "data_manifest_sha256": hashlib.sha256((DATA / "data_manifest.json").read_bytes()).hexdigest(),
               "source_data_kind": manifest["data_kind"], "fallback_reason": manifest["fallback_reason"]}
    with threadpool_limits(limits=2):
        metrics["energy"] = train_energy(energy, manifest, predictions)
        metrics["synthetic_value"] = train_value(value, predictions)
    metrics["total_train_evaluate_seconds"] = round(time.perf_counter() - start, 4)
    files = {}
    for split, chunks in predictions.items():
        path = REPORTS / f"{split}_predictions.csv"
        pd.concat(chunks, ignore_index=True).to_csv(path, index=False, float_format="%.12g")
        files[str(path.relative_to(ROOT))] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "rows": sum(len(chunk) for chunk in chunks)}
    for path in MODELS.glob("*.joblib"):
        files[str(path.relative_to(ROOT))] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "bytes": path.stat().st_size}
    metrics["artifacts"] = files
    (REPORTS / "training_metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    print("COMPLETED: reports/training_metrics.json and frozen validation/test_predictions.csv", flush=True)


if __name__ == "__main__":
    main()
