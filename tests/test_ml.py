"""Artifact-backed ML tests: real recorded metrics, leakage guards and abstention."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error, mean_squared_error

from greenhome import ml
from greenhome.engine import demo_homes
from scripts.prepare_data import assign_splits, observed_energy, parse_metadata, synthetic_reference

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def metrics():
    return json.loads((ROOT / "reports/training_metrics.json").read_text())


@pytest.fixture(scope="module")
def predictions():
    return pd.read_csv(ROOT / "reports/test_predictions.csv")


def test_training_really_completed_and_artifacts_match(metrics):
    assert metrics["status"] == "completed"
    assert metrics["source_data_kind"] == "observed_NEED2026"
    assert metrics["fallback_reason"] is None
    for name, artifact in metrics["artifacts"].items():
        path = ROOT / name
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


@pytest.mark.training_data
def test_official_metadata_was_parsed_before_targets():
    sheets = parse_metadata(ROOT / "data/raw/NEED-2026-anonymised-dataset-metadata.ods")
    text = json.dumps(sheets)
    assert "2022-2024" in text
    assert "1930-1972" in text
    assert "2000 or later" in text


@pytest.mark.training_data
def test_quality_flags_are_observed_only_and_missing_is_not_zero():
    raw = pd.read_csv(ROOT / "data/raw/anon2026_50k.csv", dtype=str)
    frame, audit = observed_energy(raw)
    assert len(frame) == 50000
    assert frame.property_id.is_unique
    assert audit["Econs2024"]["accepted"] == 45214
    assert audit["Gcons2024"]["accepted"] == 37186
    for target, flag in (("Econs2024", "ElecValFlag2024"), ("Gcons2024", "GasValFlag2024")):
        assert frame.loc[frame[flag] != "V", target].isna().all()
        assert frame.loc[frame[target].notna(), flag].eq("V").all()
        assert not frame[target].eq(0).any()


def test_current_or_future_usage_and_identity_never_features(metrics):
    assert ml.ENERGY_FEATURES == ("PROP_TYPE", "PROP_AGE_BAND", "FLOOR_AREA_BAND", "REGION", "EPC")
    assert metrics["energy"]["features"] == list(ml.ENERGY_FEATURES)
    forbidden = {"MAIN_HEAT_FUEL", "Econs2024", "Gcons2024", "property_id", "split",
                 "reference_before_gbp", "reference_after_gbp", "impact_percent", "synthetic_market_shock"}
    assert not forbidden.intersection(metrics["energy"]["features"])
    assert not forbidden.intersection(metrics["synthetic_value"]["features"])


@pytest.mark.training_data
def test_property_splits_and_scenario_expansion_have_no_overlap(metrics):
    energy = pd.read_csv(ROOT / "data/energy_properties.csv")
    scenarios = pd.read_csv(ROOT / "data/synthetic_value_scenarios.csv")
    assert energy.property_id.is_unique
    assert len(energy) == 50000
    assert energy.model_sample.sum() == 20000
    assert energy.loc[energy.model_sample].split.value_counts().to_dict() == {"train": 12000, "validation": 4000, "test": 4000}
    assert scenarios.groupby("property_id").split.nunique().eq(1).all()
    assert scenarios.scenario_id.is_unique
    for audit in (metrics["energy"]["full_data_audit"], metrics["energy"]["sample_audit"],
                  metrics["synthetic_value"]["split_audit"]):
        assert all(v == 0 for v in audit["property_overlap"].values())
    assert metrics["synthetic_value"]["split_audit"]["unique_properties"] == {"train": 1080, "validation": 360, "test": 360}


def test_split_reproducibility_and_duplicate_guard():
    rows = pd.DataFrame({"property_id": [f"P{i}" for i in range(100)]})
    a, b = assign_splits(rows, 42, 50), assign_splits(rows, 42, 50)
    pd.testing.assert_frame_equal(a, b)
    assert a.loc[a.model_sample].split.value_counts().to_dict() == {"train": 30, "validation": 10, "test": 10}
    with pytest.raises(ValueError, match="unique"):
        assign_splits(pd.concat([rows, rows]), 42)


@pytest.mark.parametrize("area,expected", [(30, "1"), (50, "1"), (50.1, "2"), (100, "2"),
                                         (100.1, "3"), (150, "3"), (200, "4"), (201, "5")])
def test_metadata_floor_bands(area, expected):
    assert ml.floor_area_band(area) == expected


@pytest.mark.parametrize("area", [None, 0, -1, True, np.nan, np.inf])
def test_invalid_floor_area_never_imputed_as_zero(area):
    with pytest.raises(ValueError):
        ml.floor_area_band(area)


def test_energy_api_schema_and_usage_independence():
    home = demo_homes()[0]
    first = ml.predict_energy_benchmark(home)
    changed = {**home, "electricity_kwh": 999999, "gas_kwh": None,
               "current_value_gbp": 999999, "property_id": "UNSEEN-ID"}
    assert first == ml.predict_energy_benchmark(changed)
    assert set(first) == {"electricity_kwh", "gas_kwh", "note", "status"}
    assert first["status"] == "observed_benchmark"
    assert first["electricity_kwh"] > 0
    assert first["gas_kwh"] > 0
    assert "post-date" in first["note"]


@pytest.mark.parametrize("heating", ["heat_pump", "electric_resistance", "unknown", None])
def test_gas_abstains_for_electric_or_unknown_heat(heating):
    out = ml.predict_energy_benchmark({**demo_homes()[0], "heating": heating})
    assert out["electricity_kwh"] > 0
    assert out["gas_kwh"] is None
    assert out["status"] == "partial_observed_benchmark"
    assert "missing gas is not zero" in out["note"]


@pytest.mark.parametrize("change", [{"floor_area_m2": None}, {"age_band": 5}, {"region": "US-CA"},
                                   {"property_type": "Unknown"}, {"age_band": True}])
def test_energy_out_of_scope_abstains(change):
    out = ml.predict_energy_benchmark({**demo_homes()[0], **change})
    assert out["status"] == "unavailable"
    assert out["electricity_kwh"] is None and out["gas_kwh"] is None


def test_missing_epc_is_explicit_no_epc_cohort():
    home = {**demo_homes()[0], "epc_rating": None}
    assert ml.energy_features(home).iloc[0]["EPC"] == "No EPC"
    assert ml.predict_energy_benchmark(home)["electricity_kwh"] > 0


def test_value_trained_schema_and_synthetic_label():
    out = ml.predict_value_impact(demo_homes()[0], ["loft_insulation", "heat_pump"])
    assert set(out) == {"status", "low_gbp", "high_gbp", "low_percent", "high_percent", "note"}
    assert out["status"] == "synthetic_illustration"
    assert out["low_gbp"] <= out["high_gbp"]
    assert out["low_percent"] <= out["high_percent"]
    assert "NOT market-calibrated" in out["note"]


@pytest.mark.parametrize("kind", ["user_entered", "real", None])
def test_value_non_demo_always_abstains_even_with_opt_in(kind):
    home = {**demo_homes()[0], "data_kind": kind, "value_illustrative_opt_in": True}
    out = ml.predict_value_impact(home, ["loft_insulation"])
    assert out["status"] == "abstained"
    assert out["low_gbp"] is None and out["high_gbp"] is None


@pytest.mark.parametrize("home", [{}, {"data_kind": "user_entered"}, demo_homes()[0]])
def test_no_op_is_exact_zero_even_without_valuation(home):
    out = ml.predict_value_impact(home, [])
    assert out["status"] == "no_change"
    assert [out[k] for k in ("low_gbp", "high_gbp", "low_percent", "high_percent")] == [0., 0., 0., 0.]


def test_already_installed_measures_are_exact_zero():
    home = demo_homes()[2]
    out = ml.predict_value_impact(home, list(ml.RETROFIT_IDS))
    assert out["status"] == "no_change"
    assert out["low_gbp"] == out["high_gbp"] == out["low_percent"] == out["high_percent"] == 0


@pytest.mark.parametrize("change", [{"current_value_gbp": None}, {"floor_area_m2": None},
                                   {"insulation": "unknown"}, {"glazing": "unknown"}, {"heating": "unknown"},
                                   {"epc_rating": None}, {"region": "unknown"}, {"smart_controls": None},
                                   {"floor_area_m2": 301}, {"current_value_gbp": 2000000}])
def test_unknown_or_out_of_domain_value_abstains(change):
    out = ml.predict_value_impact({**demo_homes()[0], **change}, ["smart_controls"])
    assert out["status"] == "abstained"
    assert out["low_gbp"] is None and out["high_gbp"] is None


def test_value_order_invariance_and_no_input_mutation():
    home = demo_homes()[0]
    saved = deepcopy(home)
    a = ml.predict_value_impact(home, ["loft_insulation", "heat_pump"])
    b = ml.predict_value_impact(home, ["heat_pump", "loft_insulation", "heat_pump"])
    assert a == b
    assert saved == home
    assert ml.predict_value_impact(home, ["invented_upgrade"])["status"] == "abstained"


def test_infeasible_value_requests_abstain():
    assert ml.predict_value_impact({**demo_homes()[0], "roof_access": None}, ["solar_pv"])["status"] == "abstained"
    assert ml.predict_value_impact({**demo_homes()[0], "heat_pump_ready": False}, ["heat_pump"])["status"] == "abstained"


@pytest.mark.parametrize("retrofit", ["solar_pv", "heat_pump", "loft_insulation"])
@pytest.mark.parametrize("omit", [False, True])
def test_value_unknown_listing_does_not_assume_consent(retrofit, omit):
    home = {**demo_homes()[0], "listed_building": None, "consent_confirmed": False}
    if omit:
        home.pop("listed_building")
    assert ml.predict_value_impact(home, [retrofit])["status"] == "abstained"


@pytest.mark.parametrize("field", ["floor_area_m2", "age_band", "current_value_gbp", "solar_kwp"])
@pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["positive_huge", "negative_huge"])
def test_oversized_integer_is_abstention_not_overflow(field, value):
    assert not ml.finite_number(value)
    home = {**demo_homes()[0], field: value}
    assert ml.predict_value_impact(home, ["smart_controls"])["status"] == "abstained"
    if field in ("floor_area_m2", "age_band"):
        assert ml.predict_energy_benchmark(home)["status"] == "unavailable"


def test_missing_models_are_exposed_not_fake(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "MODEL_DIR", tmp_path)
    assert ml.predict_energy_benchmark(demo_homes()[0])["status"] == "unavailable"
    assert ml.predict_value_impact(demo_homes()[0], ["smart_controls"])["status"] == "abstained"
    assert ml.predict_value_impact({}, [])["low_gbp"] == 0


@pytest.mark.parametrize("fuel", ["electricity", "gas"])
def test_actual_energy_test_metrics_match_frozen_predictions(metrics, predictions, fuel):
    rows = predictions.loc[predictions.task == f"energy_{fuel}"]
    result = metrics["energy"]["targets"][fuel]["test"]
    assert len(rows) == result["model"]["n"]
    for kind, column in (("model", "predicted"), ("dummy_median", "baseline_predicted")):
        assert mean_absolute_error(rows.actual, rows[column]) == pytest.approx(result[kind]["mae"], rel=1e-9)
        assert np.sqrt(mean_squared_error(rows.actual, rows[column])) == pytest.approx(result[kind]["rmse"], rel=1e-9)


def test_synthetic_interval_coverage_and_noops_match_frozen_predictions(metrics, predictions):
    rows = predictions.loc[predictions.task == "synthetic_value_impact"]
    m = metrics["synthetic_value"]["test"]
    covered = (rows.actual >= rows.p10) & (rows.actual <= rows.p90)
    active = rows.no_op.astype(str).str.lower().eq("false")
    assert covered.mean() == pytest.approx(m["coverage_p10_p90_all_scenarios"])
    assert covered[active].mean() == pytest.approx(m["coverage_p10_p90_active_scenarios"])
    assert (rows.p10 <= rows.p50).all() and (rows.p50 <= rows.p90).all()
    assert (rows.loc[~active, ["actual", "p10", "p50", "p90"]].to_numpy() == 0).all()
    assert len(rows) == m["p50_percent"]["n"]
    assert np.allclose(rows.reference_after_gbp - rows.reference_before_gbp, rows.actual_gbp, atol=1e-5)


def test_synthetic_rule_is_nonlinear_and_can_be_negative():
    home = demo_homes()[0]
    pair = synthetic_reference(home, ("loft_insulation", "heat_pump"), 0, 0)
    summed = synthetic_reference(home, ("loft_insulation",), 0, 0) + synthetic_reference(home, ("heat_pump",), 0, 0)
    assert pair < summed  # disclosed diminishing interaction, not additive premium
    assert synthetic_reference(home, ("smart_controls",), -2, 0) < 0
    assert synthetic_reference(home, (), 100, 100) == 0


def test_cached_energy_fitted_models_are_single_worker_without_changing_disk():
    path = ROOT / "models/energy_benchmark.joblib"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    ml._read_artifact.cache_clear()
    cached = ml.load_artifact(path.name)
    assert ml.load_artifact(path.name) is cached
    original = joblib.load(path)
    for fuel in ("electricity", "gas"):
        fitted = cached["models"][fuel].named_steps["model"]
        assert fitted.regressor_.n_jobs == 1
        # Changing only the constructor's regressor would not affect prediction.
        assert fitted.regressor.n_jobs == 2
        assert original["models"][fuel].named_steps["model"].regressor_.n_jobs == 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("fuel", ["electricity", "gas"])
@pytest.mark.training_data
def test_single_worker_matches_original_and_frozen_energy_predictions(fuel, predictions):
    rows = predictions.loc[predictions.task == f"energy_{fuel}"]
    energy = pd.read_csv(ROOT / "data/energy_properties.csv",
                         dtype={column: str for column in ml.ENERGY_FEATURES}).set_index("property_id")
    x = energy.loc[rows.property_id, list(ml.ENERGY_FEATURES)]
    original = joblib.load(ROOT / "models/energy_benchmark.joblib")["models"][fuel]
    cached = ml.load_artifact("energy_benchmark.joblib")["models"][fuel]
    actual = cached.predict(x)
    # Full-precision predictions must not change, with no relative-tolerance escape.
    np.testing.assert_allclose(actual, original.predict(x), rtol=0, atol=1e-8)
    # train_models.py froze CSVs with %.12g, losing up to 5e-8 at gas scales.
    # Compare at that existing serialization precision; never rewrite the CSV.
    serialized = np.array([float(f"{value:.12g}") for value in actual])
    np.testing.assert_allclose(serialized, rows.predicted, rtol=0, atol=1e-8)


@pytest.mark.training_data
def test_value_frozen_predictions_unchanged_by_inference_loading(predictions):
    rows = predictions.loc[predictions.task == "synthetic_value_impact"]
    scenarios = pd.read_csv(ROOT / "data/synthetic_value_scenarios.csv").set_index("scenario_id")
    x = scenarios.loc[rows.scenario_id, list(ml.VALUE_CATEGORICAL + ml.VALUE_NUMERIC)]
    actual = ml.value_quantile_predictions(ml.load_artifact("synthetic_value.joblib"), x)
    np.testing.assert_allclose(actual, rows[["p10", "p50", "p90"]], rtol=0, atol=1e-8)


def test_concurrent_energy_requests_are_stable_without_parallel_config_warnings():
    home = demo_homes()[0]
    expected = ml.predict_energy_benchmark(home)
    assert expected["status"] == "observed_benchmark"
    # Recording is scoped to this test, not a production/global warning filter.
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with ThreadPoolExecutor(max_workers=4) as executor:
            actual = list(executor.map(ml.predict_energy_benchmark, [home] * 16))
    assert all(result == expected for result in actual)
    assert not [warning for warning in recorded
                if "sklearn.utils.parallel.delayed" in str(warning.message)]
