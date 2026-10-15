from copy import deepcopy
import math
import pytest
from greenhome.engine import assess, demo_homes, calculate_score, EMISSIONS


def home(**changes):
    return {**demo_homes()[0], **changes}


def test_score_fixed_weights_and_contributions():
    s = assess(home(), [])["score"]
    assert sum(c["weight"] for c in s["components"]) == pytest.approx(1)
    assert s["total"] == math.floor(sum(c["contribution"] for c in s["components"]) + .5)
    assert 0 <= s["total"] <= 100


@pytest.mark.parametrize("key,value", [("insulation", "good"), ("glazing", "triple"),
                                    ("epc_rating", "A"), ("smart_controls", True),
                                    ("solar_kwp", 4), ("electricity_kwh", 2000)])
def test_component_improvements_monotonic(key, value):
    assert calculate_score(home(**{key: value}))["total"] >= calculate_score(home())["total"]


def test_noop_is_zero_and_input_not_mutated():
    h = home()
    before = deepcopy(h)
    r = assess(h, [])["scenario"]
    assert r["net_saving_kwh"] == 0
    assert r["carbon_reduction_kgco2e"] == 0
    assert h == before


def test_missing_gas_is_not_zero():
    r = assess(home(gas_kwh=None), [])
    assert r["score"]["total"] is None
    assert r["scenario"]["net_saving_kwh"] is None
    assert r["scenario"]["carbon_reduction_kgco2e"] is None


def test_zero_baseline_percentage_unavailable():
    r = assess(home(electricity_kwh=0, gas_kwh=0), [])["scenario"]
    assert r["net_saving_kwh"] == 0
    assert r["improvement_percent"] is None


@pytest.mark.parametrize("key,value", [("floor_area_m2", 0), ("electricity_kwh", -1),
                                    ("gas_kwh", float("nan")), ("boiler_efficiency", 0),
                                    ("heat_pump_spf", .5), ("roof_access", "true"),
                                    ("solar_kwp", True), ("epc_rating", ["A"])])
def test_invalid_inputs_rejected(key, value):
    with pytest.raises(ValueError):
        assess(home(**{key: value}))


def test_heatpump_negative_electricity_positive_gas():
    s = assess(home(), ["heat_pump"])["scenario"]
    assert s["electricity_saving_kwh"] < 0 < s["gas_saving_kwh"]
    assert s["gas_kwh"] == pytest.approx(2400)
    assert s["carbon_reduction_kgco2e"] == pytest.approx(
        s["electricity_saving_kwh"] * EMISSIONS["electricity"] +
        s["gas_saving_kwh"] * EMISSIONS["gas"])


def test_interactions_not_added():
    h = home()
    a = assess(h, ["loft_insulation"])["scenario"]["net_saving_kwh"]
    b = assess(h, ["heat_pump"])["scenario"]["net_saving_kwh"]
    combined = assess(h, ["heat_pump", "loft_insulation"])
    assert combined["selected_retrofits"] == ["loft_insulation", "heat_pump"]
    assert combined["scenario"]["net_saving_kwh"] != pytest.approx(a + b)


def test_solar_never_negative_import():
    s = assess(home(electricity_kwh=10), ["solar_pv"])["scenario"]
    assert s["electricity_kwh"] == 0
    assert s["electricity_saving_kwh"] == 10
    assert s["gas_saving_kwh"] == 0


@pytest.mark.parametrize("changes,rid", [
    ({"roof_access": False}, "solar_pv"), ({"roof_access": None}, "loft_insulation"),
    ({"glazing": "double"}, "double_glazing"), ({"smart_controls": True}, "smart_controls"),
    ({"heat_pump_ready": None}, "heat_pump"), ({"listed_building": True}, "solar_pv"),
])
def test_infeasible_rejected(changes, rid):
    with pytest.raises(ValueError):
        assess(home(**changes), [rid])


def test_combined_budget_respected():
    h = home(budget_gbp=1700)
    with pytest.raises(ValueError):
        assess(h, ["loft_insulation", "smart_controls"])
    r = assess(h)
    assert r["scenario"]["cost_gbp"][1] <= 1700


def test_no_secret_or_unknown_retrofit():
    with pytest.raises(ValueError):
        assess(home(), ["ignore_previous_instructions"])


def test_equal_intensity_not_penalised_for_size():
    s1 = calculate_score(home())
    s2 = calculate_score(home(floor_area_m2=200, electricity_kwh=9600, gas_kwh=24000))
    assert s1["components"][1]["score"] == s2["components"][1]["score"]


def test_missing_area_keeps_fixed_weight_no_reweight():
    s = calculate_score(home(floor_area_m2=None))
    assert s["total"] is None
    assert s["components"][1]["weight"] == .20


def test_duplicate_retrofit_does_not_double_count():
    assert assess(home(), ["solar_pv", "solar_pv"])["scenario"] == assess(home(), ["solar_pv"])["scenario"]


def test_unknown_solar_not_assumed_absent():
    r = assess(home(solar_kwp=None), [])
    assert r["score"]["total"] is None
    assert all(not rec["feasible"] for rec in r["recommendations"])
