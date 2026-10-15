"""Deterministic, offline money/package contracts; literals are hand-calculated."""
from copy import deepcopy
from decimal import Decimal
import builtins

import pytest
from pydantic import ValidationError

from greenhome import engine
from greenhome.money import TariffInput, calculate_money, money_plan


def illustrative(**changes):
    return TariffInput(electricity_pence=25, gas_pence=7, source="illustrative", **changes)


def demo(**changes):
    return {**engine.demo_homes()[0], **changes}


def test_example_preserves_signed_fuels_cost_and_payback():
    result = money_plan(demo(), ["loft_insulation", "heat_pump"], illustrative())
    money = result["money"]
    assert money["status"] == "available"
    assert money["electricity"] == {"before_gbp": 1200, "after_gbp": 1778, "saving_gbp": -578}
    assert money["gas"] == {"before_gbp": 840, "after_gbp": 168, "saving_gbp": 672}
    assert money["total"] == {"before_gbp": 2040, "after_gbp": 1946, "saving_gbp": 94}
    assert money["cost_gbp"] == [9800, 16600]
    assert money["monthly_average_gbp"] == 7.83
    assert money["payback_years"] == {"low": 104.26, "high": 176.6}
    assert "excluded" in money["standing_charge_note"].lower()
    assert result["tariffs"]["source"] == "illustrative"
    assert result["tariffs"]["as_of"] is None
    assert any("illustrative" in warning.lower() for warning in result["warnings"])


@pytest.mark.parametrize("electricity,gas,status", [
    (None, None, "unavailable"), (25, None, "partial"), (None, 7, "partial"),
])
def test_incomplete_tariffs_never_produce_totals_or_bill_pick(electricity, gas, status):
    result = money_plan(demo(), ["loft_insulation"], TariffInput(
        electricity_pence=electricity, gas_pence=gas,
    ))
    assert result["money"]["status"] == status
    assert result["money"]["total"] == {"before_gbp": None, "after_gbp": None, "saving_gbp": None}
    assert result["money"]["monthly_average_gbp"] is None
    assert result["money"]["payback_years"] is None
    assert result["picks"]["bills"] is None
    assert all(package["money_saving_gbp"] is None for package in result["packages"])
    assert result["money"]["cost_gbp"] == [800, 1600]


def test_initial_user_rates_are_unknown_not_illustrative_defaults():
    result = money_plan(demo(), [], TariffInput())
    assert result["tariffs"]["electricity_pence"] is None
    assert result["tariffs"]["gas_pence"] is None
    assert result["tariffs"]["source"] == "user_entered"
    assert result["money"]["status"] == "unavailable"
    assert result["money"]["cost_gbp"] == [0, 0]


def test_explicit_zero_rates_are_available_not_missing_and_have_no_payback():
    result = money_plan(demo(), ["heat_pump"], TariffInput(electricity_pence=0, gas_pence=0))
    assert result["money"]["status"] == "available"
    assert result["money"]["total"] == {"before_gbp": 0, "after_gbp": 0, "saving_gbp": 0}
    assert result["money"]["payback_years"] is None
    assert result["picks"]["bills"] is None
    assert all(package["money_saving_gbp"] == 0 for package in result["packages"])


def test_negative_bill_saving_has_no_payback_and_retains_installation_cost():
    result = money_plan(demo(), ["heat_pump"], illustrative())
    assert result["money"]["total"] == {"before_gbp": 2040, "after_gbp": 2048, "saving_gbp": -8}
    assert result["money"]["monthly_average_gbp"] == -0.67
    assert result["money"]["payback_years"] is None
    assert result["money"]["cost_gbp"] == [9000, 15000]
    assert any("increase" in warning.lower() for warning in result["warnings"])


def test_missing_fuel_stays_unknown_even_at_zero_rate():
    result = money_plan(demo(gas_kwh=None), ["solar_pv"], TariffInput(electricity_pence=25, gas_pence=0))
    assert result["money"]["status"] == "partial"
    assert result["money"]["electricity"]["saving_gbp"] == 303.75
    assert result["money"]["gas"] == {"before_gbp": None, "after_gbp": None, "saving_gbp": None}
    assert result["money"]["total"]["saving_gbp"] is None
    assert result["picks"] == {"energy": None, "bills": None, "lowest_cost": "solar_pv"}
    assert result["packages"][0]["net_saving_kwh"] is None


def test_known_zero_gas_is_not_missing():
    result = money_plan(demo(gas_kwh=0), ["solar_pv"], illustrative())
    assert result["money"]["status"] == "available"
    assert result["money"]["gas"] == {"before_gbp": 0, "after_gbp": 0, "saving_gbp": 0}
    assert result["money"]["total"]["saving_gbp"] == 303.75


def test_standing_charge_pairs_are_per_fuel_annual_and_signed():
    result = money_plan(demo(), ["loft_insulation", "heat_pump"], illustrative(
        electricity_standing_before_pence_per_day=40,
        electricity_standing_after_pence_per_day=50,
        gas_standing_before_pence_per_day=30,
        gas_standing_after_pence_per_day=20,
    ))
    money = result["money"]
    assert money["electricity"] == {"before_gbp": 1346, "after_gbp": 1960.5, "saving_gbp": -614.5}
    assert money["gas"] == {"before_gbp": 949.5, "after_gbp": 241, "saving_gbp": 708.5}
    assert money["total"] == {"before_gbp": 2295.5, "after_gbp": 2201.5, "saving_gbp": 94}
    assert "365" in money["standing_charge_note"]


def test_explicit_standing_charge_increase_can_remove_positive_payback():
    result = money_plan(demo(), ["loft_insulation", "heat_pump"], illustrative(
        electricity_standing_before_pence_per_day=0,
        electricity_standing_after_pence_per_day=100,
    ))
    assert result["money"]["total"]["saving_gbp"] == -271
    assert result["money"]["payback_years"] is None


def test_retained_gas_never_removes_unchanged_standing_charge():
    result = money_plan(demo(), ["heat_pump"], illustrative(
        gas_standing_before_pence_per_day=30, gas_standing_after_pence_per_day=30,
    ))
    assert result["money"]["gas"] == {"before_gbp": 949.5, "after_gbp": 277.5, "saving_gbp": 672}
    assert "retained" in result["money"]["standing_charge_note"].lower()


def test_half_supplied_standing_pair_is_excluded_not_assumed_zero():
    result = money_plan(demo(), ["heat_pump"], illustrative(gas_standing_before_pence_per_day=30))
    assert result["money"]["gas"] == {"before_gbp": 840, "after_gbp": 168, "saving_gbp": 672}
    note = result["money"]["standing_charge_note"].lower()
    assert "gas" in note and "incomplete" in note and "excluded" in note


def test_decimal_half_penny_rounds_half_up_and_displayed_parts_reconcile():
    home = demo(electricity_kwh=100.5, gas_kwh=100.5)
    scenario = engine.calculate_scenario(home, [])
    money = calculate_money(home, scenario, TariffInput(electricity_pence=1, gas_pence=1))
    assert money["electricity"]["before_gbp"] == 1.01
    assert money["gas"]["before_gbp"] == 1.01
    assert money["total"] == {"before_gbp": 2.02, "after_gbp": 2.02, "saving_gbp": 0}


def test_sub_penny_positive_saving_rounded_to_zero_has_no_displayed_payback():
    home = demo(electricity_kwh=1, gas_kwh=0)
    result = money_plan(home, ["solar_pv"], TariffInput(electricity_pence=0.1, gas_pence=7))
    assert result["money"]["total"]["saving_gbp"] == 0
    assert result["money"]["payback_years"] is None
    assert result["picks"]["bills"] is None


@pytest.mark.parametrize("field,limit", [
    ("electricity_pence", 200), ("gas_pence", 200),
    ("electricity_standing_before_pence_per_day", 1000),
    ("electricity_standing_after_pence_per_day", 1000),
    ("gas_standing_before_pence_per_day", 1000),
    ("gas_standing_after_pence_per_day", 1000),
])
@pytest.mark.parametrize("bad", [True, False, "25", float("nan"), float("inf"), -0.01])
def test_tariffs_reject_non_numbers_nonfinite_and_negative(field, limit, bad):
    with pytest.raises(ValidationError):
        TariffInput(**{field: bad})


@pytest.mark.parametrize("field,limit", [
    ("electricity_pence", 200), ("gas_pence", 200),
    ("electricity_standing_before_pence_per_day", 1000),
    ("electricity_standing_after_pence_per_day", 1000),
    ("gas_standing_before_pence_per_day", 1000),
    ("gas_standing_after_pence_per_day", 1000),
])
def test_tariff_upper_limits_are_inclusive(field, limit):
    assert getattr(TariffInput(**{field: limit}), field) == Decimal(limit)
    with pytest.raises(ValidationError):
        TariffInput(**{field: limit + 0.01})


@pytest.mark.parametrize("as_of", ["2026-02-30", "20261015", "2026-10-15T00:00:00", True, 0])
def test_rate_date_requires_real_iso_date_not_coercion(as_of):
    with pytest.raises(ValidationError):
        TariffInput(as_of=as_of)


def test_date_and_rate_provenance_are_echoed_without_asserting_current_tariffs():
    result = money_plan(demo(), [], TariffInput(
        electricity_pence=25.1234, gas_pence=7, source="user_entered", as_of="2026-10-15",
    ))
    assert result["tariffs"]["as_of"] == "2026-10-15"
    assert result["tariffs"]["electricity_pence"] == 25.1234
    assert result["tariffs"]["source"] == "user_entered"
    assert any("not independently verified" in warning.lower() for warning in result["warnings"])


def test_packages_reuse_screening_with_budget_permissions_and_exclusions():
    home = demo(budget_gbp=1800, excluded_retrofits=["smart_controls"])
    result = money_plan(home, ["loft_insulation"], illustrative())
    assert [package["retrofits"] for package in result["packages"]] == [["loft_insulation"]]
    assert result["picks"] == {"energy": "loft_insulation", "bills": "loft_insulation",
                               "lowest_cost": "loft_insulation"}
    assert result["packages"][0]["cost_gbp"] == [800, 1600]
    assert result["packages"][0]["net_saving_kwh"] == 1440
    assert result["packages"][0]["money_saving_gbp"] == 100.8
    assert result["packages"][0]["recommendation_reason"]
    assert all(package["cost_gbp"][1] <= 1800 for package in result["packages"])
    no_roof = money_plan(demo(roof_access=False), [], illustrative())
    assert all(not {"solar_pv", "loft_insulation"} & set(package["retrofits"])
               for package in no_roof["packages"])


def test_energy_bills_and_upfront_cost_are_separate_objectives():
    result = money_plan(demo(budget_gbp=16600), [], illustrative())
    assert result["picks"]["energy"] == "loft_insulation+heat_pump"
    assert result["picks"]["bills"] == "loft_insulation+smart_controls+solar_pv"
    assert result["picks"]["lowest_cost"] == "smart_controls"


def test_zero_budget_has_no_packages_or_picks_but_can_price_unchanged_home():
    result = money_plan(demo(budget_gbp=0), [], illustrative())
    assert result["packages"] == []
    assert result["picks"] == {"energy": None, "bills": None, "lowest_cost": None}
    assert result["money"]["total"] == {"before_gbp": 2040, "after_gbp": 2040, "saving_gbp": 0}


@pytest.mark.parametrize("changes,selected", [
    ({"budget_gbp": 16599}, ["loft_insulation", "heat_pump"]),
    ({"roof_access": False}, ["solar_pv"]),
    ({"excluded_retrofits": ["heat_pump"]}, ["heat_pump"]),
    ({}, ["unknown"]),
    ({}, None),
])
def test_invalid_or_infeasible_explicit_selection_is_not_silently_replaced(changes, selected):
    with pytest.raises(ValueError):
        money_plan(demo(**changes), selected, illustrative())


def test_equal_savings_tie_uses_lower_upper_cost_then_package_ids(monkeypatch):
    # 0.07 * 0.8 * 12000 = 672 gas-kWh; PV can be set to the same saving.
    home = demo(solar_yield_kwh_per_kwp=224, solar_self_consumption_fraction=1,
                excluded_retrofits=["loft_insulation", "double_glazing", "heat_pump"])
    tariff = TariffInput(electricity_pence=7, gas_pence=7)
    result = money_plan({**home, "budget_gbp": 7000}, [], tariff)
    assert result["picks"]["energy"] == "smart_controls"
    assert result["picks"]["bills"] == "smart_controls"
    # Equal upper costs force the final lexicographic-ID tie break.
    catalogue = deepcopy(engine.RETROFITS)
    catalogue["solar_pv"]["cost_gbp"] = [150, 350]
    monkeypatch.setattr(engine, "RETROFITS", catalogue)
    result = money_plan({**home, "budget_gbp": 350}, [], tariff)
    assert result["picks"] == {"energy": "smart_controls", "bills": "smart_controls",
                               "lowest_cost": "smart_controls"}


def test_no_positive_bill_choice_abstains_but_preserves_loss_in_package():
    home = demo(excluded_retrofits=["loft_insulation", "double_glazing", "smart_controls", "solar_pv"])
    result = money_plan(home, ["heat_pump"], illustrative())
    assert result["picks"]["energy"] == "heat_pump"
    assert result["picks"]["bills"] is None
    assert result["packages"][0]["money_saving_gbp"] == -8


def test_zero_standalone_pv_joint_package_remains_available():
    result = money_plan(demo(electricity_kwh=0, budget_gbp=22000),
                        ["heat_pump", "solar_pv"], illustrative())
    assert any(package["retrofits"] == ["heat_pump", "solar_pv"]
               for package in result["packages"])
    assert not any(package["retrofits"] == ["solar_pv"] for package in result["packages"])
    assert result["money"]["total"]["saving_gbp"] == 295.75
    assert not any("zero marginal" in warning.lower() for warning in result["warnings"])


def test_zero_import_pv_without_load_partner_is_omitted_but_explicit_costs_preserved():
    home = demo(electricity_kwh=0, budget_gbp=22000)
    selected = ["loft_insulation", "solar_pv"]
    result = money_plan(home, selected, illustrative())
    assert all(not ("solar_pv" in package["retrofits"] and "heat_pump" not in package["retrofits"])
               for package in result["packages"])
    assert "loft_insulation+solar_pv" not in result["picks"].values()
    assert result["money"]["total"] == {"before_gbp": 840, "after_gbp": 739.2, "saving_gbp": 100.8}
    assert result["money"]["cost_gbp"] == [5300, 8600]
    assert result["money"]["payback_years"] == {"low": 52.58, "high": 85.32}
    assert selected == ["loft_insulation", "solar_pv"]
    assert any("solar_pv" in warning and "zero marginal" in warning.lower()
               and "4500" in warning and "7000" in warning for warning in result["warnings"])
    assert any(package["retrofits"] == ["heat_pump", "solar_pv"] for package in result["packages"])


def test_saturated_pv_omits_zero_marginal_fabric_alternatives_not_explicit_selection():
    home = demo(heating="electric_resistance", electricity_kwh=1000, gas_kwh=0)
    result = money_plan(home, ["loft_insulation", "solar_pv"], illustrative())
    assert all(package["retrofits"] == ["solar_pv"] for package in result["packages"]
               if "solar_pv" in package["retrofits"])
    assert result["picks"]["energy"] == result["picks"]["bills"] == "solar_pv"
    assert result["money"]["cost_gbp"] == [5300, 8600]
    assert result["money"]["total"]["saving_gbp"] == 250
    assert result["money"]["payback_years"] == {"low": 21.2, "high": 34.4}
    assert any("loft_insulation" in warning and "zero marginal" in warning.lower()
               and "800" in warning and "1600" in warning for warning in result["warnings"])


@pytest.mark.parametrize("rates", [{}, {"electricity_pence": 0, "gas_pence": 0}])
def test_comparison_redundancy_is_not_inferred_from_zero_or_missing_tariffs(rates):
    result = money_plan(demo(), ["loft_insulation", "heat_pump"], TariffInput(**rates))
    assert len(result["packages"]) == 31
    assert result["picks"]["energy"] is not None
    assert not any("zero marginal" in warning.lower() for warning in result["warnings"])


def test_request_does_not_mutate_inputs_or_call_models_or_providers(monkeypatch):
    home, selected, tariff = demo(), ["heat_pump", "loft_insulation"], illustrative()
    before = deepcopy((home, selected, tariff))
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("greenhome.ml", "greenhome.explain", "greenhome.providers", "google")):
            pytest.fail(f"Money calculation attempted a model/provider import: {name}")
        return real_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Money calculation must not call assess() and load models.")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(engine, "assess", forbidden)
    assert money_plan(home, selected, tariff)["money"]["total"]["saving_gbp"] == 94
    assert (home, selected, tariff) == before


def test_repeated_requests_do_not_reuse_previous_tariffs_or_selection():
    money_plan(demo(), ["heat_pump", "loft_insulation"], illustrative())
    result = money_plan(demo(gas_kwh=None), [], TariffInput())
    assert result["money"]["status"] == "unavailable"
    assert result["money"]["total"]["before_gbp"] is None
    assert result["money"]["cost_gbp"] == [0, 0]
    assert result["picks"]["bills"] is None
