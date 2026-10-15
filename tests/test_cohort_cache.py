from copy import deepcopy

from greenhome import engine, ml


def test_cached_predictions_match_frozen_pipeline():
    ml._cohort_prediction.cache_clear()
    home = engine.demo_homes()[0]
    frame = ml.energy_features(home)
    models = ml.load_artifact("energy_benchmark.joblib")["models"]
    result = ml.predict_energy_benchmark(home)
    for fuel in ("electricity", "gas"):
        assert result[f"{fuel}_kwh"] == round(float(models[fuel].predict(frame)[0]), 1)
    before = ml._cohort_prediction.cache_info()
    changed = {**home, "property_id":"DIFFERENT", "electricity_kwh":1234.0, "gas_kwh":9876.0,
               "current_value_gbp":600000.0, "budget_gbp":1000.0}
    assert ml.predict_energy_benchmark(changed) == result
    after = ml._cohort_prediction.cache_info()
    assert after.hits == before.hits + 2
    assert after.currsize == 2


def test_changed_fitted_model_gets_separate_cache_identity():
    home = engine.demo_homes()[0]
    pipeline = ml.load_artifact("energy_benchmark.joblib")["models"]["electricity"]
    features = tuple(ml.energy_features(home).iloc[0][key] for key in ml.ENERGY_FEATURES)
    first = ml._cohort_prediction(pipeline, features)
    replaced = deepcopy(pipeline)
    before = ml._cohort_prediction.cache_info()
    assert ml._cohort_prediction(replaced, features) == first
    assert ml._cohort_prediction.cache_info().misses == before.misses + 1


def test_output_mutation_never_changes_cached_value():
    home = engine.demo_homes()[0]
    first = ml.predict_energy_benchmark(home)
    expected = first["electricity_kwh"]
    first["electricity_kwh"] = -1
    assert ml.predict_energy_benchmark(home)["electricity_kwh"] == expected
