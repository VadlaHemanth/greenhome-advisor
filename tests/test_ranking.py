"""Nominal home-ranking contract and independent, finite reference comparisons."""
from copy import deepcopy
from decimal import ROUND_DOWN, localcontext
from fractions import Fraction
from itertools import permutations, product
import json
import subprocess
import sys

import pytest

from greenhome import engine, ranking


def home(**changes):
    return {**engine.demo_homes()[0], **changes}


@pytest.fixture(autouse=True)
def no_assessment_models_or_decision_grid(monkeypatch):
    monkeypatch.setattr(engine, "assess", lambda *a, **k: pytest.fail("Ranking must not use ML-backed assess."))
    monkeypatch.setitem(sys.modules, "greenhome.ml", None)


def test_exact_contract_and_finite_json():
    result = ranking.rank_homes([home()])
    assert set(result) == {"policy", "rows", "warnings"}
    assert result["policy"] == "Maximum nominal purchased-energy reduction under each stated budget; upper indicative costs"
    row = result["rows"][0]
    assert set(row) == {
        "property_id", "rank", "status", "reason", "score", "classification", "flagged",
        "improvement_percent", "baseline_kwh", "selected_retrofits",
        "electricity_saving_kwh", "gas_saving_kwh", "carbon_reduction_kgco2e",
        "cost_gbp", "budget_gbp",
    }
    assert row["rank"] == 1 and row["status"] == "available"
    assert row["score"] == 37 and row["classification"] == "Poor" and row["flagged"]
    assert row["baseline_kwh"] == 16800
    assert row["improvement_percent"] == pytest.approx(8879.856 / 16800 * 100)
    assert row["selected_retrofits"] == list(engine.RETROFITS)
    assert result["warnings"]
    json.dumps(result, allow_nan=False)


def test_audit_reversal_uses_best_nominal_percentage_not_greedy_or_absolute_saving():
    a = home(property_id="A", gas_kwh=6000, budget_gbp=7350)
    b = home(property_id="B", gas_kwh=10000, insulation="good", budget_gbp=7350)
    rows = ranking.rank_homes([b, a])["rows"]
    assert [r["property_id"] for r in rows] == ["A", "B"]
    assert [r["rank"] for r in rows] == [1, 2]
    assert rows[0]["improvement_percent"] == pytest.approx(1551 / 10800 * 100)
    assert rows[1]["improvement_percent"] == pytest.approx(1775 / 14800 * 100)
    assert all(r["selected_retrofits"] == ["smart_controls", "solar_pv"] for r in rows)
    assert rows[0]["electricity_saving_kwh"] + rows[0]["gas_saving_kwh"] < (
        rows[1]["electricity_saving_kwh"] + rows[1]["gas_saving_kwh"])


@pytest.mark.parametrize("gas,electricity,budget", list(product(
    (3000, 6000, 12000), (2400, 4800), (3000, 7350, 17000, 25000),
)))
def test_nominal_best_matches_independent_rational_32_package_reference(gas, electricity, budget):
    ids = ["loft_insulation", "double_glazing", "smart_controls", "heat_pump", "solar_pv"]
    costs = [(800, 1600), (4000, 10000), (150, 350), (9000, 15000), (4500, 7000)]
    options = []
    for mask in range(32):
        selected = [rid for i, rid in enumerate(ids) if mask & (1 << i)]
        cost = [sum(costs[i][j] for i in range(5) if mask & (1 << i)) for j in (0, 1)]
        if cost[1] > budget:
            continue
        remainder = Fraction(1)
        for rid, multiplier in zip(ids[:3], (Fraction(85, 100), Fraction(9, 10), Fraction(93, 100))):
            if rid in selected:
                remainder *= multiplier
        e, g = Fraction(electricity), Fraction(gas)
        if "heat_pump" in selected:
            e += g * Fraction(4, 5) * Fraction(85, 100) * remainder / 3
            g *= Fraction(1, 5)
        else:
            g *= Fraction(1, 5) + Fraction(4, 5) * remainder
        if "solar_pv" in selected:
            e -= min(e, Fraction(1215))
        options.append((Fraction(electricity + gas) - e - g, cost, selected, electricity - e, gas - g))
    expected = min(options, key=lambda p: (-p[0], p[1][1], p[2]))
    row = ranking.rank_homes([home(electricity_kwh=electricity, gas_kwh=gas, budget_gbp=budget)])["rows"][0]
    assert row["selected_retrofits"] == expected[2]
    assert row["cost_gbp"] == expected[1]
    assert row["electricity_saving_kwh"] == pytest.approx(float(expected[3]))
    assert row["gas_saving_kwh"] == pytest.approx(float(expected[4]))
    assert row["improvement_percent"] == pytest.approx(float(expected[0] / (electricity + gas) * 100))


def test_equal_potential_has_equal_competition_rank_and_property_id_tie_order():
    rows = ranking.rank_homes([
        home(property_id="Z"), home(property_id="A"),
        home(property_id="B", budget_gbp=0),
    ])["rows"]
    assert [r["property_id"] for r in rows] == ["A", "Z", "B"]
    assert [r["rank"] for r in rows] == [1, 1, 3]


@pytest.mark.parametrize("gas_delta", [0.00001, 0.0001, 0.001])
def test_rank_precision_does_not_merge_materially_distinct_percentages(gas_delta):
    rows = ranking.rank_homes([
        home(property_id="A", gas_kwh=6000 + gas_delta, budget_gbp=7350),
        home(property_id="Z", gas_kwh=6000, budget_gbp=7350),
    ])["rows"]
    assert round(rows[0]["improvement_percent"], 4) == round(rows[1]["improvement_percent"], 4)
    assert rows[0]["improvement_percent"] - rows[1]["improvement_percent"] > 1e-9
    assert [r["rank"] for r in rows] == [1, 2]
    assert rows[0]["property_id"] == "Z"


@pytest.mark.parametrize("electricity,gas,budget", list(product(
    (2100, 3700), (6300, 11100), (350, 1600, 1950),
)))
def test_proportional_homes_have_identical_published_percentages_and_tied_ranks(electricity, gas, budget):
    # Generic metered-energy scaling, not copied reference records or labels.
    homes = [home(
        property_id=f"SCALE-{index}", electricity_kwh=electricity * scale,
        gas_kwh=gas * scale, floor_area_m2=100 * scale, budget_gbp=budget,
    ) for index, scale in enumerate((0.1, 0.3, 1, 1.7, 2.5))]
    before = deepcopy(homes)
    rows = ranking.rank_homes(homes)["rows"]
    assert [r["property_id"] for r in rows] == sorted(h["property_id"] for h in homes)
    assert [r["rank"] for r in rows] == [1] * len(homes)
    assert len({r["improvement_percent"] for r in rows}) == 1
    # Independent rational gas-only reference; no candidate helper as the oracle.
    remaining = {350: Fraction(93, 100), 1600: Fraction(85, 100),
                 1950: Fraction(85, 100) * Fraction(93, 100)}[budget]
    expected = Fraction(gas, electricity + gas) * Fraction(4, 5) * (1 - remaining) * 100
    for row in rows:
        assert abs(Fraction(str(row["improvement_percent"])) - expected) <= Fraction(1, 2_000_000_000)
    for reordered in (list(reversed(homes)), homes[2:] + homes[:2]):
        assert ranking.rank_homes(reordered)["rows"] == rows
    assert homes == before


def test_proportional_tie_groups_keep_competition_gaps_and_unranked_rows():
    homes = [
        home(property_id=identifier, electricity_kwh=2100 * scale, gas_kwh=6300 * scale,
             budget_gbp=budget)
        for identifier, scale, budget in (
            ("HIGH-B", 0.3, 1600), ("LOW-B", 2.5, 350),
            ("HIGH-A", 1.7, 1600), ("LOW-A", 0.1, 350),
        )
    ]
    homes += [home(property_id="ZERO", budget_gbp=0), home(property_id="UNKNOWN", gas_kwh=None)]
    rows = ranking.rank_homes(homes)["rows"]
    assert [r["property_id"] for r in rows] == ["HIGH-A", "HIGH-B", "LOW-A", "LOW-B", "ZERO", "UNKNOWN"]
    assert [r["rank"] for r in rows] == [1, 1, 3, 3, 5, None]
    assert [r["improvement_percent"] for r in rows] == [9.0, 9.0, 4.2, 4.2, 0.0, None]


@pytest.mark.parametrize("value,expected", [
    (None, None), (0.0, 0.0), (-0.0, 0.0),
    (12.1234567894, 12.123456789),
    (12.1234567895, 12.123456790),
    (12.1234567885, 12.123456789),  # half-up, not half-even
    (-12.1234567885, -12.123456789),
    (0.00000000049, 0.0), (0.0000000005, 0.000000001),
    (99.9999999995, 100.0),
])
def test_shared_percentage_quantization_has_explicit_decimal_half_up_boundaries(value, expected):
    assert ranking.RANK_PERCENT_QUANTUM == Fraction(1, 1_000_000_000)
    assert ranking.quantize_improvement_percent(value) == expected
    assert ranking.quantize_improvement_percent(expected) == expected  # idempotent
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        assert ranking.quantize_improvement_percent(value) == expected


def test_quantized_tie_buckets_are_transitive_and_do_not_chain_nearby_values():
    # Adjacent pairs are less than 1e-9 apart; an isclose-based comparator could
    # transitively merge all three or make output depend on input order.
    values = [10.0000000001, 10.0000000007, 10.0000000013]
    expected = {values[0]: 10.0, values[1]: 10.000000001, values[2]: 10.000000001}
    for order in permutations(values):
        actual = {value: ranking.quantize_improvement_percent(value) for value in order}
        assert actual == expected
    assert ranking.quantize_improvement_percent(10.00000000049) == 10.0
    assert ranking.quantize_improvement_percent(10.00000000051) == 10.000000001


def test_rank_precision_does_not_round_fuel_savings_or_change_package_selection():
    h = home(electricity_kwh=3712.3, gas_kwh=11987.9, budget_gbp=7350)
    screened = engine.screen_home(h)
    best = min(screened["packages"], key=lambda p: (
        -p["scenario"]["net_saving_kwh"], p["scenario"]["cost_gbp"][1], tuple(p["retrofits"]),
    ))
    row = ranking.rank_homes([h])["rows"][0]
    scenario = best["scenario"]
    assert row["selected_retrofits"] == best["retrofits"]
    for field in ("electricity_saving_kwh", "gas_saving_kwh", "carbon_reduction_kgco2e", "cost_gbp"):
        assert row[field] == scenario[field]
    assert row["improvement_percent"] == ranking.quantize_improvement_percent(scenario["improvement_percent"])
    assert row["improvement_percent"] != scenario["improvement_percent"]
    assert abs(row["improvement_percent"] - scenario["improvement_percent"]) <= 5e-10
    assert json.loads(json.dumps(row, allow_nan=False)) == row


def test_positive_subquantum_potential_keeps_its_status_and_signed_fuel_evidence():
    h = home(space_heat_fraction=1e-11, budget_gbp=350)
    row = ranking.rank_homes([h])["rows"][0]
    assert row["status"] == "available"
    assert row["gas_saving_kwh"] > 0
    assert row["improvement_percent"] == 0.0
    assert row["selected_retrofits"] == ["smart_controls"]


@pytest.mark.parametrize("changes", [
    {"gas_kwh": None}, {"electricity_kwh": None},
    {"electricity_kwh": 0, "gas_kwh": 0}, {"solar_kwp": None},
    {"insulation": "unknown"}, {"roof_access": None}, {"heat_pump_ready": None},
    {"listed_building": None}, {"listed_building": True, "consent_confirmed": False},
    {"heating": "unknown"},
])
def test_missing_energy_or_relevant_eligibility_evidence_stays_unranked(changes):
    rows = ranking.rank_homes([home(property_id="UNKNOWN", **changes), home(property_id="KNOWN")])["rows"]
    assert rows[0]["property_id"] == "KNOWN"
    row = rows[1]
    assert row["status"] == "insufficient_evidence"
    assert row["rank"] is None
    for key in ("improvement_percent", "electricity_saving_kwh", "gas_saving_kwh",
                "carbon_reduction_kgco2e", "cost_gbp"):
        assert row[key] is None
    assert row["selected_retrofits"] == []
    assert row["reason"]


@pytest.mark.parametrize("changes,status", [
    ({"budget_gbp": 0}, "no_affordable_option"),
    ({"space_heat_fraction": 0, "solar_self_consumption_fraction": 0}, "no_modelled_benefit"),
    ({"excluded_retrofits": list(engine.RETROFITS)}, "no_modelled_benefit"),
])
def test_known_zero_opportunity_is_ranked_zero_with_specific_reason(changes, status):
    row = ranking.rank_homes([home(**changes)])["rows"][0]
    assert row["status"] == status
    assert row["rank"] == 1
    assert row["improvement_percent"] == 0
    assert row["electricity_saving_kwh"] == row["gas_saving_kwh"] == row["carbon_reduction_kgco2e"] == 0
    assert row["cost_gbp"] == [0, 0] and row["selected_retrofits"] == []


def test_unknown_unaffordable_or_excluded_options_do_not_block_known_budget_potential():
    # These missing facts cannot change the currently permitted search universe.
    h = home(roof_access=None, heat_pump_ready=None, budget_gbp=350)
    row = ranking.rank_homes([h])["rows"][0]
    assert row["status"] == "available"
    assert row["selected_retrofits"] == ["smart_controls"]
    h = home(roof_access=None, excluded_retrofits=["loft_insulation", "solar_pv"])
    assert ranking.rank_homes([h])["rows"][0]["status"] == "available"


def test_score_only_missing_data_does_not_impute_score_or_hide_known_fuel_potential():
    row = ranking.rank_homes([home(epc_rating=None, floor_area_m2=None)])["rows"][0]
    assert row["score"] is None and row["classification"] == "Unavailable"
    assert row["status"] == "available" and row["improvement_percent"] > 0


def test_existing_pv_gas_potential_supported_but_electric_potential_unranked():
    rows = ranking.rank_homes([
        home(property_id="GAS", solar_kwp=3),
        home(property_id="ELECTRIC", solar_kwp=3, heating="heat_pump"),
    ])["rows"]
    assert rows[0]["property_id"] == "GAS" and rows[0]["status"] == "available"
    assert rows[0]["electricity_saving_kwh"] == 0 and rows[0]["gas_saving_kwh"] > 0
    assert rows[0]["selected_retrofits"] == ["loft_insulation", "double_glazing", "smart_controls"]
    assert rows[1]["status"] == "unsupported"
    assert rows[1]["rank"] is None and rows[1]["improvement_percent"] is None


def test_exclusions_change_maximum_not_just_presentation():
    first = ranking.rank_homes([home()])["rows"][0]
    excluded = ["heat_pump", "solar_pv"]
    second = ranking.rank_homes([home(excluded_retrofits=excluded)])["rows"][0]
    assert not set(excluded).intersection(second["selected_retrofits"])
    assert second["improvement_percent"] < first["improvement_percent"]
    assert second["gas_saving_kwh"] > 0
    assert second["electricity_saving_kwh"] == 0


def test_joint_only_pv_is_kept_by_nominal_optimizer_and_respects_joint_cost():
    row = ranking.rank_homes([home(electricity_kwh=0, budget_gbp=22000)])["rows"][0]
    assert row["selected_retrofits"] == ["heat_pump", "solar_pv"]
    assert row["cost_gbp"] == [13500, 22000]
    assert row["electricity_saving_kwh"] < 0
    row = ranking.rank_homes([home(electricity_kwh=0, budget_gbp=21999)])["rows"][0]
    assert "solar_pv" not in row["selected_retrofits"]


def test_at_most_32_nominal_scenarios_per_home_and_no_hidden_ml(monkeypatch):
    count = 0
    original = engine.calculate_scenario

    def counted(h, selected):
        nonlocal count
        count += 1
        return original(h, selected)

    monkeypatch.setattr(engine, "calculate_scenario", counted)
    result = ranking.rank_homes([home(property_id=f"H{i}") for i in range(100)])
    assert count == 3200
    assert len(result["rows"]) == 100
    assert all(row["rank"] == 1 for row in result["rows"])


@pytest.mark.parametrize("invalid", [None, {}, (), [None], [1], [{"property_id": []}], [home()] * 101])
def test_invalid_batch_shape_or_limit_rejected(invalid):
    with pytest.raises(ValueError):
        ranking.rank_homes(invalid)


@pytest.mark.parametrize("changes", [
    {"electricity_kwh": 1e308}, {"floor_area_m2": 1e-308},
    {"excluded_retrofits": ["solar_pv", "solar_pv"]},
])
def test_invalid_home_follows_engine_validation_contract(changes):
    with pytest.raises(ValueError):
        ranking.rank_homes([home(**changes)])


def test_empty_batch_and_optional_ids_supported_without_fabrication():
    assert ranking.rank_homes([])["rows"] == []
    row = ranking.rank_homes([home(property_id=None)])["rows"][0]
    assert row["property_id"] is None and row["rank"] == 1


def test_repeated_results_detached_from_input_and_catalogue():
    homes = [home(property_id="B", excluded_retrofits=["solar_pv"]), home(property_id="A")]
    before = deepcopy(homes)
    original = ranking.rank_homes(homes)
    changed = ranking.rank_homes(list(reversed(homes)))
    assert changed == original
    changed["rows"][0]["cost_gbp"][1] = -1
    changed["rows"][0]["selected_retrofits"].clear()
    changed["warnings"].clear()
    assert ranking.rank_homes(homes) == original
    assert homes == before


def test_import_and_execution_do_not_import_api_or_models_in_fresh_process():
    code = """
import sys
from greenhome import engine, ranking
ranking.rank_homes(engine.demo_homes())
assert 'greenhome.api' not in sys.modules
assert 'greenhome.ml' not in sys.modules
assert 'greenhome.decision' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
