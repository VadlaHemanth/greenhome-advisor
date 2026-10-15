"""Independent engine audit against the brief and documented screening assumptions.

Only engine behaviour is tested: ML functions are isolated from concurrent training.
Failing tests are intentional regression specifications, not expected-failure markers.
No real personal information, credentials, external services or model files are used.
"""

from copy import deepcopy
from itertools import combinations
import math
import sys
from types import ModuleType

import pytest

from greenhome import engine


@pytest.fixture(autouse=True)
def isolate_models_and_mutable_catalogue(monkeypatch):
    """Do not depend on model availability or leave mutation probes behind."""
    ml = ModuleType("greenhome.ml")
    ml.predict_energy_benchmark = lambda home: None
    ml.predict_value_impact = lambda home, selected: {
        "status": "unavailable",
        "low_gbp": None,
        "high_gbp": None,
        "low_percent": None,
        "high_percent": None,
        "note": "ML deliberately isolated for engine audit.",
    }
    monkeypatch.setitem(sys.modules, "greenhome.ml", ml)
    monkeypatch.setattr(engine, "RETROFITS", deepcopy(engine.RETROFITS))
    monkeypatch.setattr(engine, "SOURCES", deepcopy(engine.SOURCES))


def home(**changes):
    return {**engine.demo_homes()[0], **changes}


@pytest.mark.parametrize(
    "key",
    [
        "floor_area_m2",
        "electricity_kwh",
        "gas_kwh",
        "epc_rating",
        "insulation",
        "heating",
        "glazing",
        "solar_kwp",
        "smart_controls",
    ],
)
def test_missing_score_input_matches_explicit_unknown_without_reweighting(key):
    omitted = home()
    omitted.pop(key)
    unknown = home(**{key: None})
    omitted_result = engine.assess(omitted, [])
    unknown_result = engine.assess(unknown, [])
    assert omitted_result["score"] == unknown_result["score"]
    assert omitted_result["score"]["total"] is None
    assert omitted_result["score"]["classification"] == "Unavailable"
    assert sum(c["weight"] for c in omitted_result["score"]["components"]) == pytest.approx(1)
    assert omitted_result["score"]["issues"]


@pytest.mark.parametrize("missing_gas", [None, "omitted"])
def test_solar_can_report_electricity_but_not_invent_missing_gas(missing_gas):
    h = home(gas_kwh=None)
    if missing_gas == "omitted":
        h.pop("gas_kwh")
    result = engine.assess(h, ["solar_pv"])
    scenario = result["scenario"]
    assert scenario["electricity_saving_kwh"] == pytest.approx(1215)
    assert scenario["gas_kwh"] is None
    for key in (
        "gas_saving_kwh",
        "net_saving_kwh",
        "improvement_percent",
        "carbon_reduction_kgco2e",
    ):
        assert scenario[key] is None
    assert scenario["warnings"]


@pytest.mark.parametrize("state", [None, "omitted"], ids=["null", "omitted"])
@pytest.mark.parametrize("retrofit", ["solar_pv", "heat_pump"])
def test_unknown_listing_status_is_not_confirmed_absence_of_consent_constraints(
    state, retrofit
):
    """Missing consent-relevant facts must not silently become a safe 'false'."""
    h = home(listed_building=None, consent_confirmed=False)
    if state == "omitted":
        h.pop("listed_building")
    try:
        result = engine.assess(h, [])
    except ValueError:
        # Rejecting incomplete feasibility input is also a safe contract.
        return
    recommendation = next(r for r in result["recommendations"] if r["id"] == retrofit)
    assert not recommendation["feasible"], (
        f"{retrofit} is offered with unknown listing status and no confirmed consent: "
        f"{recommendation['reason']}"
    )
    with pytest.raises(ValueError):
        engine.assess(h, [retrofit])


def test_explicitly_unlisted_home_does_not_require_irrelevant_listing_consent():
    result = engine.assess(home(listed_building=False, consent_confirmed=False), ["solar_pv"])
    assert result["selected_retrofits"] == ["solar_pv"]


@pytest.mark.parametrize("imports", [0.0, 0.01, 10.0, 1215.0, 4800.0])
@pytest.mark.parametrize("self_consumption", [0.0, 0.45, 1.0])
def test_solar_import_cap_fuel_balance_and_carbon(imports, self_consumption):
    h = home(electricity_kwh=imports, solar_self_consumption_fraction=self_consumption)
    # Numerical zeros remain valid, but known-zero actions are no longer plans.
    scenario = engine.calculate_scenario(h, ["solar_pv"])
    if imports == 0 or self_consumption == 0:
        with pytest.raises(ValueError):
            engine.assess(h, ["solar_pv"])
    else:
        assert engine.assess(h, ["solar_pv"])["scenario"] == scenario
    expected = min(imports, 3 * h["solar_yield_kwh_per_kwp"] * self_consumption)
    assert 0 <= scenario["electricity_kwh"] <= imports
    assert scenario["electricity_kwh"] + scenario["electricity_saving_kwh"] == pytest.approx(
        imports
    )
    assert scenario["electricity_saving_kwh"] == pytest.approx(expected)
    assert scenario["gas_kwh"] == h["gas_kwh"]
    assert scenario["gas_saving_kwh"] == 0
    assert scenario["carbon_reduction_kgco2e"] == pytest.approx(
        expected * engine.EMISSIONS["electricity"]
    )


@pytest.mark.parametrize("fraction", [0.0, 0.3, 0.8, 1.0])
@pytest.mark.parametrize("spf", [1.0, 3.0, 6.0])
def test_fuel_switch_follows_explicit_space_heat_split_not_total_gas(fraction, spf):
    h = home(space_heat_fraction=fraction, heat_pump_spf=spf)
    selected = ["solar_pv", "heat_pump", "loft_insulation"]
    scenario = engine.calculate_scenario(h, selected)
    if fraction == 0:
        with pytest.raises(ValueError):
            engine.assess(h, selected)
    else:
        assert engine.assess(h, selected)["scenario"] == scenario
    useful_heat = h["gas_kwh"] * fraction * h["boiler_efficiency"] * 0.85
    expected_electricity = h["electricity_kwh"] + useful_heat / spf
    expected_electricity -= min(
        expected_electricity,
        3 * h["solar_yield_kwh_per_kwp"] * h["solar_self_consumption_fraction"],
    )
    assert scenario["electricity_kwh"] == pytest.approx(expected_electricity)
    assert scenario["gas_kwh"] == pytest.approx(h["gas_kwh"] * (1 - fraction))
    assert scenario["net_saving_kwh"] == pytest.approx(
        h["electricity_kwh"] + h["gas_kwh"]
        - scenario["electricity_kwh"] - scenario["gas_kwh"]
    )
    assert scenario["carbon_reduction_kgco2e"] == pytest.approx(
        scenario["electricity_saving_kwh"] * engine.EMISSIONS["electricity"]
        + scenario["gas_saving_kwh"] * engine.EMISSIONS["gas"]
    )


@pytest.mark.parametrize("heating", ["heat_pump", "electric_resistance"])
def test_existing_electric_heating_envelope_saving_does_not_reduce_other_gas(heating):
    h = home(heating=heating, gas_kwh=2400, space_heat_fraction=0.3)
    scenario = engine.assess(h, ["loft_insulation", "double_glazing"])["scenario"]
    assert scenario["electricity_kwh"] == pytest.approx(
        h["electricity_kwh"] * (0.7 + 0.3 * 0.85 * 0.90)
    )
    assert scenario["gas_kwh"] == 2400
    assert scenario["gas_saving_kwh"] == 0
    with pytest.raises(ValueError):
        engine.assess(h, ["heat_pump"])


BOUNDARY_HOMES = [
    (30, "Very poor", "Poor", dict(
        epc_rating="G", insulation="poor", heating="electric_resistance",
        glazing="single", smart_controls=False,
    )),
    (50, "Poor", "Moderate", dict(
        epc_rating="E", insulation="partial", heating="gas_boiler",
        glazing="double", smart_controls=False,
    )),
    (65, "Moderate", "Good", dict(
        epc_rating="D", insulation="good", heating="gas_boiler",
        glazing="double", smart_controls=True,
    )),
    (80, "Good", "Highly efficient", dict(
        epc_rating="B", insulation="good", heating="heat_pump",
        glazing="triple", smart_controls=True,
    )),
]


@pytest.mark.parametrize("threshold,below,above,changes", BOUNDARY_HOMES)
@pytest.mark.parametrize("offset", [-0.51, -0.50, -0.49])
def test_classification_uses_rounded_score_including_half_up_ties(
    threshold, below, above, changes, offset
):
    h = home(**changes)
    h.update(floor_area_m2=100.0, gas_kwh=0.0, solar_kwp=0.0)
    components = engine.calculate_score(h)["components"]
    fixed = sum(
        c["weight"] * c["score"]
        for c in components
        if c["name"] != "Energy consumption intensity"
    )
    desired_raw = threshold + offset
    h["electricity_kwh"] = (400 - (desired_raw - fixed) / 0.20 * 3.5) * 100
    score = engine.assess(h, [])["score"]
    assert score["total"] == (threshold - 1 if offset < -0.50 else threshold)
    assert score["classification"] == (below if offset < -0.50 else above)
    assert score["flagged"] is (score["classification"] in {"Poor", "Very poor"})


def test_rating_and_metered_intensity_are_independent_components():
    original = engine.calculate_score(home())["components"]
    changed_rating = engine.calculate_score(home(epc_rating="A"))["components"]
    changed_meter = engine.calculate_score(home(electricity_kwh=9600))["components"]
    assert changed_rating[0]["score"] > original[0]["score"]
    assert changed_rating[1] == original[1]
    assert changed_meter[0] == original[0]
    assert changed_meter[1]["score"] < original[1]["score"]


def test_scaled_area_and_meter_values_preserve_entire_score():
    h = home()
    scaled = {
        **h,
        "floor_area_m2": h["floor_area_m2"] * 3,
        "electricity_kwh": h["electricity_kwh"] * 3,
        "gas_kwh": h["gas_kwh"] * 3,
    }
    assert engine.calculate_score(h) == engine.calculate_score(scaled)


def test_all_demo_packages_preserve_inputs_and_per_fuel_conservation():
    h = home()
    before = deepcopy(h)
    ids = list(engine.RETROFITS)
    for count in range(len(ids) + 1):
        for combination in combinations(ids, count):
            forward = engine.assess(h, list(combination))
            reverse = engine.assess(h, list(reversed(combination)))
            assert forward["scenario"] == reverse["scenario"]
            scenario = forward["scenario"]
            for fuel in ("electricity", "gas"):
                after = scenario[f"{fuel}_kwh"]
                saving = scenario[f"{fuel}_saving_kwh"]
                assert math.isfinite(after) and after >= 0
                assert after + saving == pytest.approx(h[f"{fuel}_kwh"])
            assert 0 <= scenario["improvement_percent"] <= 100
            assert h == before


def test_response_cost_mutation_cannot_change_later_assessments():
    baseline = engine.assess(home(), ["loft_insulation"])["scenario"]["cost_gbp"][:]
    response = engine.assess(home(), [])
    loft = next(r for r in response["recommendations"] if r["id"] == "loft_insulation")
    loft["cost_gbp"][1] = 0
    after = engine.assess(home(), ["loft_insulation"])["scenario"]["cost_gbp"]
    assert after == baseline, (
        "Returned recommendations expose mutable global catalogue costs: "
        f"later cost changed from {baseline} to {after}"
    )


def test_response_source_mutation_cannot_change_later_provenance():
    expected = deepcopy(engine.SOURCES)
    response = engine.assess(home(), [])
    response["sources"][0]["url"] = "audit-only-corrupted-source"
    assert engine.assess(home(), [])["sources"] == expected, (
        "Mutating one response changes source provenance for unrelated later assessments."
    )


def test_oversized_json_integer_returns_validation_error_instead_of_overflow():
    # Valid JSON integers can exceed the native float range.
    h = home(electricity_kwh=10**400)
    errors = engine.validate_home(h)
    assert errors, "An unrepresentable numeric input must be rejected by validation."
    with pytest.raises(ValueError):
        engine.assess(h, [])


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -float("inf")])
def test_non_numeric_or_nonfinite_energy_rejected(value):
    with pytest.raises(ValueError):
        engine.assess(home(electricity_kwh=value), [])


def test_engine_does_not_log_input_or_mutate_caller_data(capsys, caplog):
    # Synthetic marker only. This checks engine logs, not downstream LLM redaction.
    marker = "AUDIT_SYNTHETIC_PRIVATE_MARKER_NOT_REAL_CUSTOMER_DATA"
    h = home(property_id=marker)
    before = deepcopy(h)
    engine.assess(h, ["heat_pump"])
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err + caplog.text
    assert h == before


def test_existing_pv_allows_only_safe_gas_changes_and_discloses_limitations():
    result = engine.assess(home(solar_kwp=3.0))
    assert result["selected_retrofits"] == ["loft_insulation", "double_glazing", "smart_controls"]
    assert result["scenario"]["electricity_saving_kwh"] == 0
    assert result["scenario"]["gas_saving_kwh"] > 0
    for rec in result["recommendations"]:
        if rec["id"] in ("solar_pv", "heat_pump"):
            assert not rec["feasible"] and rec["standalone"] is None
            assert rec["status"] == "unsupported"
    assert any("Existing PV" in message for message in result["warnings"])
