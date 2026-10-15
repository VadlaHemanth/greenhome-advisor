"""Offline finite-grid tests. These do not validate physical or market outcomes."""
from copy import deepcopy
from itertools import product
import json
import sys
from types import SimpleNamespace

import pytest

from greenhome import decision, engine


@pytest.fixture(autouse=True)
def no_model_dependency(monkeypatch):
    calls = {"energy": 0, "value": 0}

    def energy(home):
        calls["energy"] += 1
        return None

    def value(home, selected):
        calls["value"] += 1
        return {"status": "unavailable", "note": "Not part of decision ranking."}

    monkeypatch.setitem(sys.modules, "greenhome.ml", SimpleNamespace(
        predict_energy_benchmark=energy, predict_value_impact=value,
    ))
    return calls


def home(**changes):
    return {**engine.demo_homes()[0], "budget_gbp": 7350, **changes}


def package(result, retrofits):
    return next(p for p in result["packages"] if set(p["retrofits"]) == set(retrofits))


def test_exact_frontend_top_level_contract_and_finite_json():
    result = decision.decision_check(home())
    assert set(result) == {
        "status", "objective", "recommended_package", "nominal_package", "greedy_package",
        "stable", "scenario_count", "feasible_package_count", "regret_kwh", "next_check",
        "packages", "scenarios", "assumptions", "warnings",
    }
    assert result["status"] == "available"
    assert result["objective"] == "purchased_energy"
    assert result["scenario_count"] == len(result["scenarios"]) == 27
    assert result["feasible_package_count"] == len(result["packages"]) == 6
    json.dumps(result, allow_nan=False)
    assert set(result["next_check"]) == {"field", "question", "reason"}
    assert all(set(s) == {"id", "assumptions", "best_package", "best_saving_kwh"}
               for s in result["scenarios"])


def test_greedy_counterexample_is_exactly_the_disclosed_fixture():
    result = decision.decision_check(home(gas_kwh=6000))
    assert result["greedy_package"] == ["loft_insulation", "smart_controls"]
    assert result["nominal_package"] == ["smart_controls", "solar_pv"]
    assert package(result, result["greedy_package"])["nominal_saving_kwh"] == pytest.approx(1005.6)
    assert package(result, result["nominal_package"])["nominal_saving_kwh"] == pytest.approx(1551)
    assert package(result, result["nominal_package"])["cost_gbp"][1] == 7350
    assert result["feasible_package_count"] == 6


@pytest.mark.parametrize("self_use,solar_saving,winner", [
    (0.25, 1347, ["loft_insulation", "smart_controls"]),
    (0.45, 1887, ["loft_insulation", "smart_controls"]),
    (0.65, 2427, ["smart_controls", "solar_pv"]),
])
def test_nominal_solar_switch_is_not_replaced_by_stress_defaults(self_use, solar_saving, winner):
    result = decision.decision_check(home(solar_self_consumption_fraction=self_use))
    assert package(result, ["loft_insulation", "smart_controls"])["nominal_saving_kwh"] == pytest.approx(2011.2)
    assert package(result, ["smart_controls", "solar_pv"])["nominal_saving_kwh"] == pytest.approx(solar_saving)
    assert result["nominal_package"] == winner


def test_solar_switch_threshold_and_minimax_evidence_question():
    result = decision.decision_check(home(solar_self_consumption_fraction=0.496))
    assert package(result, ["loft_insulation", "smart_controls"])["nominal_saving_kwh"] == pytest.approx(
        package(result, ["solar_pv", "smart_controls"])["nominal_saving_kwh"]
    )
    assert result["nominal_package"] == ["loft_insulation", "smart_controls"]  # lower cost tie
    assert result["recommended_package"] == ["loft_insulation", "smart_controls"]
    assert result["stable"] is False
    assert result["next_check"]["field"] == "solar_self_consumption_fraction"
    assert result["regret_kwh"] == pytest.approx(750.6)
    assert "210.6" in result["next_check"]["reason"]


def test_minimax_regret_against_independent_exhaustive_matrix():
    h = home()
    result = decision.decision_check(h)
    expected = {}
    for item in result["packages"]:
        gaps = []
        values = []
        for scenario in result["scenarios"]:
            actual = engine.calculate_scenario({**h, **scenario["assumptions"]}, item["retrofits"])
            saving = actual["net_saving_kwh"]
            values.append(saving)
            gaps.append(max(0, scenario["best_saving_kwh"] - saving))
        expected[tuple(item["retrofits"])] = max(gaps)
        assert item["min_saving_kwh"] == pytest.approx(min(values))
        assert item["max_saving_kwh"] == pytest.approx(max(values))
        assert item["max_regret_kwh"] == pytest.approx(max(gaps))
    assert result["regret_kwh"] == pytest.approx(min(expected.values()))
    assert expected[tuple(result["recommended_package"])] == pytest.approx(result["regret_kwh"])


def test_one_shared_screening_no_assessment_or_ml_in_grid(monkeypatch, no_model_dependency):
    real = engine.screen_home
    calls = []

    def counted(h):
        calls.append(1)
        return real(h)

    monkeypatch.setattr(engine, "screen_home", counted)
    monkeypatch.setattr(engine, "assess", lambda *a: pytest.fail("No model-backed assessment needed."))
    result = decision.decision_check(home(budget_gbp=None))
    assert len(calls) == 1
    assert no_model_dependency == {"energy": 0, "value": 0}
    assert result["feasible_package_count"] == 32
    assert package(result, [])["nominal_saving_kwh"] == 0


def test_stress_only_varies_three_hypotheses_and_never_mutates_input(monkeypatch):
    h = home(space_heat_fraction=0.3, heat_pump_spf=1.5,
             solar_self_consumption_fraction=0.8, boiler_efficiency=0.7,
             solar_yield_kwh_per_kwp=1300)
    original = deepcopy(h)
    real = engine.calculate_scenario
    seen = []

    def checked(current, selected):
        seen.append(deepcopy(current))
        for key, value in original.items():
            if key not in decision.STRESS_VALUES:
                assert current[key] == value
        return real(current, selected)

    monkeypatch.setattr(engine, "calculate_scenario", checked)
    result = decision.decision_check(h)
    assert h == original
    assert result["scenario_count"] == 28
    assert result["scenarios"][-1]["assumptions"] == {
        key: original[key] for key in decision.STRESS_VALUES
    }
    assert len({tuple(s["assumptions"].items()) for s in result["scenarios"]}) == 28
    assert seen


@pytest.mark.parametrize("field", ["electricity_kwh", "gas_kwh"])
@pytest.mark.parametrize("omitted", [False, True])
def test_missing_annual_input_is_unavailable_not_zero(field, omitted, monkeypatch):
    h = home(**{field: None})
    if omitted:
        h.pop(field)
    monkeypatch.setattr(engine, "assess", lambda *args: pytest.fail("Do not assess missing baselines."))
    result = decision.decision_check(h)
    assert result["status"] == "unavailable"
    assert result["next_check"]["field"] == field
    for key in ("recommended_package", "nominal_package", "greedy_package", "stable",
                "scenario_count", "feasible_package_count", "regret_kwh", "packages", "scenarios"):
        assert result[key] is None


@pytest.mark.parametrize("values", [
    {"electricity_kwh": 0, "gas_kwh": 0},
])
def test_zero_combined_baseline_is_unavailable(values):
    assert decision.decision_check(home(**values))["status"] == "unavailable"


@pytest.mark.parametrize("values", [
    {"electricity_kwh": float("nan")}, {"gas_kwh": -1}, {"gas_kwh": 10**400},
    {"electricity_kwh": 1e308, "gas_kwh": 1e308},
    {"electricity_kwh": 10**308, "gas_kwh": 10**308},
    {"listed_building": "false"}, {"space_heat_fraction": None},
])
def test_invalid_inputs_follow_engine_error_contract(values):
    with pytest.raises(ValueError, match="Invalid home"):
        decision.decision_check(home(**values))


@pytest.mark.parametrize("field,blocked", [
    ("roof_access", {"loft_insulation", "solar_pv"}),
    ("listed_building", {"loft_insulation", "double_glazing", "solar_pv", "heat_pump"}),
    ("heat_pump_ready", {"heat_pump"}),
])
def test_unknown_permission_is_never_swept_or_assumed_true(field, blocked):
    h = home(budget_gbp=None, **{field: None})
    result = decision.decision_check(h)
    for item in result["packages"]:
        assert not blocked.intersection(item["retrofits"])
    assert all(field not in point["assumptions"] for point in result["scenarios"])
    assert any("withheld" in warning for warning in result["warnings"])


def test_budget_7000_never_sneaks_in_7350_package():
    result = decision.decision_check(home(gas_kwh=6000, budget_gbp=7000))
    assert all(item["cost_gbp"][1] <= 7000 for item in result["packages"])
    assert not any(set(item["retrofits"]) == {"solar_pv", "smart_controls"} for item in result["packages"])


def test_signed_fuels_carbon_and_cost_are_separate():
    h = home(budget_gbp=25000)
    result = decision.decision_check(h)
    item = package(result, ["heat_pump"])
    assert item["nominal_electricity_saving_kwh"] < 0
    assert item["nominal_gas_saving_kwh"] > 0
    assert item["nominal_saving_kwh"] == pytest.approx(
        item["nominal_electricity_saving_kwh"] + item["nominal_gas_saving_kwh"]
    )
    assert item["nominal_carbon_kgco2e"] == pytest.approx(
        item["nominal_electricity_saving_kwh"] * engine.EMISSIONS["electricity"]
        + item["nominal_gas_saving_kwh"] * engine.EMISSIONS["gas"]
    )
    assert item["cost_gbp"] == [9000, 15000]


@pytest.mark.parametrize("changes", [
    {"budget_gbp": 0},
    {"space_heat_fraction": 0, "solar_self_consumption_fraction": 0},
    {"excluded_retrofits": list(engine.RETROFITS)},
])
def test_no_action_is_available_but_not_a_stability_success(changes):
    result = decision.decision_check(home(**changes))
    assert result["status"] == "available"
    assert result["recommended_package"] == []
    assert result["feasible_package_count"] == 1
    assert result["stable"] is None
    assert result["regret_kwh"] == 0
    assert "no-action" in " ".join(result["warnings"])


def test_stable_decision_does_not_invent_a_measurement_priority():
    result = decision.decision_check(home(budget_gbp=3000))
    assert result["stable"] is True
    assert result["regret_kwh"] == pytest.approx(0)
    assert result["next_check"]["field"] is None
    assert "No additional check" in result["next_check"]["question"]


def test_value_and_cohort_numbers_do_not_change_energy_choice(monkeypatch):
    h = home()
    first = decision.decision_check(h)
    ml = sys.modules["greenhome.ml"]
    monkeypatch.setattr(ml, "predict_value_impact", lambda *args: {
        "status": "synthetic_illustration", "low_gbp": 1e12, "high_gbp": 2e12,
    })
    monkeypatch.setattr(ml, "predict_energy_benchmark", lambda *args: {
        "electricity_kwh": 9e12, "gas_kwh": 9e12,
    })
    assert decision.decision_check(h) == first


def test_deterministic_ties_cost_then_ids():
    packages = [
        {"retrofits": ["z"], "cost_gbp": [0, 10]},
        {"retrofits": ["a"], "cost_gbp": [0, 10]},
        {"retrofits": ["b"], "cost_gbp": [0, 20]},
    ]
    assert decision._choose([1, 1, 1], packages, maximise=False) == 1
    assert decision._choose([1, 1, 1], packages, maximise=True) == 1


def test_repeated_calls_are_identical_and_detached():
    first = decision.decision_check(home())
    second = decision.decision_check(home())
    assert first == second
    first["packages"][0]["cost_gbp"][1] = 999999
    first["scenarios"][0]["assumptions"]["space_heat_fraction"] = 99
    assert decision.decision_check(home()) == second


def test_grid_is_fixed_full_factorial_not_sampling_probabilities():
    points = decision.stress_points(home())
    expected = set(product((0.6, 0.8, 1.0), (2, 3, 4), (0.25, 0.45, 0.65)))
    assert {tuple(point.values()) for point in points} == expected
    assert len(points) == 27


@pytest.mark.parametrize("changes,count", [
    ({"space_heat_fraction": 0}, 9),
    ({"solar_self_consumption_fraction": 0}, 9),
    ({"space_heat_fraction": 0, "solar_self_consumption_fraction": 0}, 3),
    ({"space_heat_fraction": 0, "solar_self_consumption_fraction": 0.8}, 10),
])
def test_supplied_zero_fractions_are_fixed_not_positive_counterfactuals(changes, count):
    result = decision.decision_check(home(**changes))
    assert result["scenario_count"] == count
    for point in result["scenarios"]:
        for field, value in changes.items():
            if value == 0:
                assert point["assumptions"][field] == 0
    if count == 10:
        assert result["scenarios"][-1]["id"] == "nominal"


def test_audit_zero_heat_share_does_not_become_stable_positive_grid_recommendation():
    result = decision.decision_check(home(space_heat_fraction=0, budget_gbp=3000))
    assert result["status"] == "available"
    assert result["recommended_package"] == result["nominal_package"] == []
    assert result["stable"] is None
    assert result["feasible_package_count"] == 1
    assert all(s["best_saving_kwh"] == 0 for s in result["scenarios"])


@pytest.mark.parametrize("changes", [
    {"solar_kwp": None},
    {"solar_kwp": 3, "heating": "heat_pump"},
])
def test_unassessable_potential_is_not_a_no_action_success(changes):
    result = decision.decision_check(home(**changes))
    assert result["status"] == "unavailable"
    assert result["stable"] is None
    assert result["recommended_package"] is None
    assert result["regret_kwh"] is None
    assert result["packages"] is None


def test_existing_pv_gas_only_decision_preserves_electrical_imports():
    result = decision.decision_check(home(solar_kwp=3))
    assert result["status"] == "available"
    assert result["recommended_package"] == ["loft_insulation", "smart_controls"]
    assert all(p["nominal_electricity_saving_kwh"] == 0 for p in result["packages"])
    assert all(not {"solar_pv", "heat_pump"}.intersection(p["retrofits"]) for p in result["packages"])


def test_exclusions_apply_to_every_decision_strategy_and_stress_package():
    excluded = {"loft_insulation", "heat_pump", "solar_pv"}
    result = decision.decision_check(home(budget_gbp=None, excluded_retrofits=sorted(excluded)))
    for key in ("greedy_package", "nominal_package", "recommended_package"):
        assert not excluded.intersection(result[key])
    assert all(not excluded.intersection(p["retrofits"]) for p in result["packages"])
    assert all(not excluded.intersection(p["best_package"]) for p in result["scenarios"])


def test_zero_import_solar_is_retained_jointly_but_not_as_zero_action():
    result = decision.decision_check(home(electricity_kwh=0, budget_gbp=22000))
    assert result["nominal_package"] == ["heat_pump", "solar_pv"]
    assert not any(p["retrofits"] == ["solar_pv"] for p in result["packages"])
    assert all(p["nominal_saving_kwh"] > 0 for p in result["packages"] if p["retrofits"])
