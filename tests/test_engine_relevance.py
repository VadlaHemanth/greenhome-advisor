"""Calculation/relevance regressions; fictional inputs, no provider or models."""
from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import pytest

from greenhome import engine


@pytest.fixture(autouse=True)
def offline_models(monkeypatch):
    monkeypatch.setitem(sys.modules, "greenhome.ml", SimpleNamespace(
        predict_energy_benchmark=lambda h: None,
        predict_value_impact=lambda *a: {"status": "unavailable"},
    ))


def home(**changes):
    return {**engine.demo_homes()[0], **changes}


@pytest.mark.parametrize("changes,expected", [
    ({"space_heat_fraction": 0}, {"solar_pv"}),
    ({"gas_kwh": 0}, {"solar_pv"}),
    ({"electricity_kwh": 0, "gas_kwh": 0}, set()),
    ({"heating": "electric_resistance", "electricity_kwh": 0}, set()),
    ({"solar_self_consumption_fraction": 0}, set(engine.RETROFITS) - {"solar_pv"}),
])
def test_known_zero_benefits_are_not_recommended_or_selected(changes, expected):
    h = home(**changes)
    before = deepcopy(h)
    result = engine.assess(h)
    assert set(result["selected_retrofits"]) == expected
    assert {r["id"] for r in result["recommendations"] if r["feasible"]} == expected
    for rec in result["recommendations"]:
        if rec["id"] not in expected:
            assert rec["status"] in ("no_modelled_benefit", "not_applicable")
            assert rec["suitability"] == "Low"
    assert not engine.validate_home(h)
    assert h == before
    json.dumps(result, allow_nan=False)


def test_joint_zero_import_pv_not_filtered_by_its_zero_standalone():
    h = home(electricity_kwh=0, budget_gbp=22000)
    result = engine.assess(h, ["heat_pump", "solar_pv"])
    pv = next(r for r in result["recommendations"] if r["id"] == "solar_pv")
    assert pv["feasible"] and pv["joint_only"]
    assert pv["standalone"]["net_saving_kwh"] == 0
    assert "jointly" in pv["reason"]
    hp_only = engine.calculate_scenario(h, ["heat_pump"])
    assert result["scenario"]["net_saving_kwh"] - hp_only["net_saving_kwh"] == pytest.approx(1215)
    with pytest.raises(ValueError, match="Joint-only"):
        engine.assess(h, ["solar_pv"])


@pytest.mark.parametrize("changes", [
    {"budget_gbp": 21999},
    {"excluded_retrofits": ["heat_pump"]},
    {"heat_pump_ready": False},
])
def test_joint_only_pv_requires_a_permitted_affordable_load_creator(changes):
    result = engine.assess(home(electricity_kwh=0, **changes))
    assert "solar_pv" not in result["selected_retrofits"]
    assert not next(r for r in result["recommendations"] if r["id"] == "solar_pv")["feasible"]


def test_greedy_prunes_joint_only_solar_when_heat_pump_did_not_fit():
    result = engine.assess(home(electricity_kwh=0, budget_gbp=22000))
    assert "heat_pump" not in result["selected_retrofits"]
    assert "solar_pv" not in result["selected_retrofits"]
    assert result["scenario"]["net_saving_kwh"] > 0


def test_joint_relevance_also_preserves_zero_standalone_heat_pump():
    h = home(electricity_kwh=0, boiler_efficiency=1, heat_pump_spf=1, budget_gbp=22000)
    result = engine.assess(h, ["heat_pump", "solar_pv"])
    assert result["scenario"]["net_saving_kwh"] == pytest.approx(1215)
    assert all(r["joint_only"] for r in result["recommendations"] if r["id"] in ("heat_pump", "solar_pv"))


@pytest.mark.parametrize("rid", ["loft_insulation", "double_glazing", "smart_controls"])
def test_existing_pv_safe_gas_only_changes_match_no_pv_gas_physics(rid):
    h = home(solar_kwp=4, electricity_kwh=0)
    result = engine.assess(h, [rid])["scenario"]
    without_pv = engine.calculate_scenario({**h, "solar_kwp": 0}, [rid])
    assert result == without_pv
    assert result["electricity_kwh"] == result["electricity_saving_kwh"] == 0
    assert result["gas_saving_kwh"] > 0


@pytest.mark.parametrize("heating", ["heat_pump", "electric_resistance"])
@pytest.mark.parametrize("imports", [0, 3500])
def test_existing_pv_electrical_changes_remain_unsupported(heating, imports):
    result = engine.assess(home(solar_kwp=3, heating=heating, electricity_kwh=imports))
    assert result["selected_retrofits"] == []
    assert result["potential"]["status"] == "unsupported"
    assert result["scenario"]["net_saving_kwh"] == 0  # unchanged is still true


@pytest.mark.parametrize("excluded", [
    None, "solar_pv", {}, [None], [True], [[]], ["invented"],
    ["solar_pv", "solar_pv"], list(engine.RETROFITS) + ["solar_pv"],
])
def test_exclusion_input_is_strict_and_fails_closed(excluded):
    h = home(excluded_retrofits=excluded)
    assert engine.validate_home(h)
    with pytest.raises(ValueError, match="excluded_retrofits"):
        engine.assess(h)


def test_exclusions_default_detachment_and_explicit_selection_enforcement():
    empty = engine.assess(home(), [])
    assert empty["home"]["excluded_retrofits"] == []
    h = home(excluded_retrofits=["loft_insulation", "solar_pv"])
    before = deepcopy(h)
    result = engine.assess(h)
    for rec in result["recommendations"]:
        if rec["id"] in h["excluded_retrofits"]:
            assert rec["status"] == "excluded" and not rec["feasible"]
            with pytest.raises(ValueError, match="Excluded"):
                engine.assess(h, [rec["id"]])
    assert h == before
    result["home"]["excluded_retrofits"].append("heat_pump")
    assert h == before


@pytest.mark.parametrize("changes,status", [
    ({"solar_kwp": None}, "insufficient_evidence"),
    ({"gas_kwh": None}, "insufficient_evidence"),
    ({"electricity_kwh": 0, "gas_kwh": 0}, "insufficient_evidence"),
    ({"budget_gbp": 0}, "no_affordable_option"),
    ({"space_heat_fraction": 0, "solar_self_consumption_fraction": 0}, "no_modelled_benefit"),
    ({"excluded_retrofits": list(engine.RETROFITS)}, "no_modelled_benefit"),
])
def test_potential_status_is_not_selected_noop_arithmetic(changes, status):
    result = engine.assess(home(**changes), [])
    assert result["potential"]["status"] == status
    assert result["potential"]["reason"]
    assert result["scenario"]["net_saving_kwh"] == (None if changes.get("gas_kwh", 0) is None else 0)


@pytest.mark.parametrize("field,value", [
    ("electricity_kwh", 1e308), ("gas_kwh", 10**308),
    ("electricity_kwh", 10_000_001), ("floor_area_m2", 1e-308),
    ("floor_area_m2", 100_001), ("solar_kwp", 10_001),
    ("budget_gbp", 1_000_000_001), ("current_value_gbp", 1e308),
])
def test_direct_entry_points_share_finite_input_bounds(field, value):
    h = home(**{field: value})
    for fn in (engine.assess, engine.calculate_score, lambda h: engine.calculate_scenario(h, [])):
        with pytest.raises(ValueError):
            fn(h)


def test_small_valid_efficiency_does_not_underflow_gas_only_physics():
    h = home(boiler_efficiency=5e-324)
    actual = engine.calculate_scenario(h, ["loft_insulation"])
    expected = engine.calculate_scenario(home(), ["loft_insulation"])
    assert actual["gas_kwh"] == expected["gas_kwh"]
    assert actual["gas_saving_kwh"] == expected["gas_saving_kwh"]
    json.dumps(engine.assess(h), allow_nan=False)


def test_maximum_supported_inputs_are_json_finite():
    h = home(electricity_kwh=10_000_000, gas_kwh=10_000_000,
             floor_area_m2=0.01, current_value_gbp=1e12, budget_gbp=1e9)
    result = engine.assess(h)
    json.dumps(result, allow_nan=False)
    assert result["baseline"]["purchased_kwh"] == 20_000_000


def test_score_uses_unrounded_components_for_boundary_classification():
    result = engine.calculate_score(home(epc_rating="D", electricity_kwh=36937.57, gas_kwh=0))
    assert sum(c["contribution"] for c in result["components"]) == pytest.approx(29.5)
    assert result["total"] == 29
    assert result["classification"] == "Very poor"
