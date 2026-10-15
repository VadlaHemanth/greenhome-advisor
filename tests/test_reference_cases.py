"""Independent reference fixtures and leakage/integrity tests; no provider."""
from copy import deepcopy
from fractions import Fraction as F
import json

import pytest

from scripts import evaluate_reference_cases as ref
from scripts import evaluate_benchmark_baselines as benchmark


def test_hand_calculated_signed_full_package():
    # Literal hand ledger: 9600 gas for space heat; retained demand .71145;
    # heat pump adds 1935.144 electricity; PV offsets 1215; other gas = 2400.
    got = ref.simulate(ref.base_home(), list(ref.IDS))
    assert got["electricity_kwh"] == F("5520.144")
    assert got["gas_kwh"] == 2400
    assert got["electricity_saving_kwh"] == F("-720.144")
    assert got["gas_saving_kwh"] == 9600
    assert got["net_saving_kwh"] == F("8879.856")
    assert got["cost_gbp"] == [18450, 33950]


def test_hand_calculated_fabric_interaction():
    h = ref.base_home()
    package = ref.simulate(h, list(ref.IDS[:3]))
    assert package["gas_saving_kwh"] == F("2770.08")
    additive = sum(ref.simulate(h, [r])["gas_saving_kwh"] for r in ref.IDS[:3])
    assert additive == 3072
    assert additive - package["gas_saving_kwh"] == F("301.92")


@pytest.mark.parametrize("heating,fuel,gas", [("gas_boiler", "gas_saving_kwh", 12000),
                                            ("heat_pump", "electricity_saving_kwh", 0),
                                            ("electric_resistance", "electricity_saving_kwh", 0)])
def test_loft_reduces_only_heating_share(heating, fuel, gas):
    h = {**ref.base_home(), "heating": heating, "gas_kwh": gas}
    got = ref.simulate(h, ["loft_insulation"])
    assert got[fuel] == (1440 if heating == "gas_boiler" else 576)
    assert got["electricity_saving_kwh" if fuel == "gas_saving_kwh" else "gas_saving_kwh"] == 0


@pytest.mark.parametrize("e,g,expected", [(4800, 12000, F(0)), (0, 0, None), (4800, None, None)])
def test_noop_missing_and_zero(e, g, expected):
    h = {**ref.base_home(), "electricity_kwh": e, "gas_kwh": g}
    got = ref.simulate(h, [])
    assert got["improvement_percent"] == expected
    assert got["electricity_saving_kwh"] == 0
    assert got["gas_saving_kwh"] == (None if g is None else 0)


def test_partial_fuel_solar_not_total_savings():
    h = {**ref.base_home(), "gas_kwh": None}
    got = ref.simulate(h, ["solar_pv"])
    assert got["electricity_saving_kwh"] == 1215
    assert got["gas_saving_kwh"] is None
    assert got["net_saving_kwh"] is None
    assert got["carbon_reduction_kgco2e"] is None


def test_pv_cap_applies_after_switching_not_before():
    h = {**ref.base_home(), "electricity_kwh": 200}
    assert ref.simulate(h, ["solar_pv"])["electricity_saving_kwh"] == 200
    got = ref.simulate(h, ["heat_pump", "solar_pv"])
    assert got["electricity_kwh"] == 1705
    assert got["electricity_saving_kwh"] == -1505


def test_existing_pv_gas_only_not_fuel_switching():
    h = {**ref.base_home(), "solar_kwp": 4}
    assert ref.accepted(h, ["loft_insulation", "smart_controls"])
    assert ref.simulate(h, ["loft_insulation"])["electricity_saving_kwh"] == 0
    assert not ref.accepted(h, ["heat_pump"])
    assert not ref.accepted(h, ["solar_pv"])
    assert ref.ranking_reference(h)["status"] == "available"


@pytest.mark.parametrize("budget,selected,expected", [
    (350, ["smart_controls"], True), (349.99, ["smart_controls"], False),
    (1950, ["loft_insulation", "smart_controls"], True),
    (1949.99, ["loft_insulation", "smart_controls"], False),
    (0, [], True), (0, ["solar_pv"], False),
])
def test_upper_cost_boundaries(budget, selected, expected):
    assert ref.accepted({**ref.base_home(), "budget_gbp": budget}, selected) is expected


def test_joint_only_and_nonbeneficial_requests():
    h = {**ref.base_home(), "electricity_kwh": 0, "heat_pump_spf": 1,
         "boiler_efficiency": 1, "space_heat_fraction": 1}
    assert ref.simulate(h, ["heat_pump"])["net_saving_kwh"] == 0
    assert ref.eligibility(h, "heat_pump") == "feasible"
    assert ref.eligibility(h, "solar_pv") == "feasible"
    assert not ref.accepted(h, ["heat_pump"])
    assert not ref.accepted(h, ["solar_pv"])
    assert ref.accepted(h, ["heat_pump", "solar_pv"])
    assert ref.simulate(h, ["heat_pump", "solar_pv"])["net_saving_kwh"] == 1215


def test_unknown_infeasible_excluded_and_zero_benefit():
    assert ref.eligibility(ref.base_home(), "not_a_measure") == "unknown_retrofit"
    assert ref.eligibility({**ref.base_home(), "roof_access": None}, "solar_pv") == "unknown"
    assert ref.eligibility({**ref.base_home(), "roof_access": False}, "solar_pv") == "infeasible"
    h = {**ref.base_home(), "excluded_retrofits": ["heat_pump"]}
    assert ref.eligibility(h, "heat_pump") == "excluded"
    zero = {**ref.base_home(), "space_heat_fraction": 0, "solar_self_consumption_fraction": 0}
    assert all(ref.eligibility(zero, r) == "no_modelled_benefit" for r in ref.IDS)
    assert ref.ranking_reference(zero)["status"] == "no_modelled_benefit"


def test_fraction_generation_never_calls_candidate(monkeypatch):
    import greenhome.engine as engine
    def forbidden(*args, **kwargs):
        raise AssertionError("A candidate function was used to generate targets.")
    with monkeypatch.context() as m:
        for name in ("assess", "calculate_scenario", "calculate_score", "validate_home"):
            m.setattr(engine, name, forbidden)
        ref._reference_options.cache_clear()
        rows = ref.generate()
    assert len(rows) == 96
    assert sum(len(r["scenarios"]) for r in rows) == 3168
    ref.check_groups(rows)


def test_frozen_reproducibility_and_counts():
    rows, manifest = ref.load_frozen()
    assert rows == ref.generate()
    assert manifest["counts"]["train"]["customers"] == 24
    assert manifest["counts"]["dev"]["properties"] == 24
    assert manifest["counts"]["test"]["scenarios"] == 792
    assert len({r["archetype"] for r in rows}) == 24
    for split in ("train", "dev", "test"):
        group = [r for r in rows if r["split"] == split]
        assert len({r["home"]["property_type"] for r in group}) == 6
        assert any(r["home"]["region"] == "W92000004" for r in group)


def test_customer_leakage_rejected():
    rows = deepcopy(ref.generate())
    rows[1]["split"] = "test" if rows[0]["split"] == "train" else "train"
    with pytest.raises(ValueError, match="customer_id"):
        ref.check_groups(rows)


def test_duplicate_scenario_rejected():
    rows = deepcopy(ref.generate())
    rows[1]["scenarios"][0]["scenario_id"] = rows[0]["scenarios"][0]["scenario_id"]
    with pytest.raises(ValueError, match="Duplicate scenario"):
        ref.check_groups(rows)


def test_freeze_refuses_overwrite():
    with pytest.raises(FileExistsError):
        ref.freeze()


def test_exact_ranking_ties_and_unknowns():
    rows = [r for r in ref.generate() if r["split"] == "test"]
    ties = [r for r in rows if r["archetype"].startswith("tie_controls")]
    assert len(ties) == 2
    assert ties[0]["ranking"]["rank"] == ties[1]["ranking"]["rank"]
    assert ties[0]["ranking"]["improvement_percent"] == ties[1]["ranking"]["improvement_percent"]
    unknown = [r for r in rows if r["ranking"]["status"] in ("unsupported", "insufficient_evidence")]
    assert unknown
    assert all(r["ranking"]["rank"] is None and r["ranking"]["improvement_percent"] is None for r in unknown)


def test_pair_metrics_penalise_missing_predictions_and_tie_errors():
    got = ref.pairwise_metrics({"a": "1", "b": "1", "c": "2"}, {"a": 1, "b": 2})
    assert got["pairs"] == 3
    assert got["missing"] == 2
    assert got["incorrect"] == 1
    assert got["accuracy_including_ties_and_missing"] == 0


def test_rank_metric_does_not_round_away_float_split_ties():
    got = ref.pairwise_metrics({"a": "4", "b": "4"}, {"a": 4.0, "b": 3.999999999999995})
    assert got["incorrect"] == 1
    assert got["accuracy_including_ties_and_missing"] == 0


@pytest.mark.parametrize("prediction,truth,ok", [
    (None, None, True), (0, None, False), (None, "0", False),
    (float("nan"), "0", False), (float("inf"), "0", False),
    (False, "0", False), (-1.5, "-3/2", True),
])
def test_comparison_does_not_hide_null_nonfinite_or_signed_errors(prediction, truth, ok):
    assert ref.compare_number(prediction, truth) is ok


def training_row(kind="Detached", area="2", value="1000", split="train"):
    return {"split": split, "PROP_TYPE": kind, "FLOOR_AREA_BAND": area,
            "Econs2024": value, "ElecValFlag2024": "V", "Gcons2024": "", "GasValFlag2024": ""}


def test_cohort_median_threshold_and_fallbacks():
    rows = [training_row(value=str(1000 + i)) for i in range(30)]
    rows += [training_row(kind="Flat", area="1", value="5000") for _ in range(29)]
    fitted = benchmark.fit_cohorts(rows, "electricity")
    assert benchmark.predict_cohort(fitted, training_row()) == (1014.5, "type_area", 30)
    assert benchmark.predict_cohort(fitted, training_row(kind="Unknown")) == (1014.5, "area", 30)
    assert benchmark.predict_cohort(fitted, training_row(area="5")) == (1014.5, "type", 30)
    assert benchmark.predict_cohort(fitted, training_row(kind="Flat", area="1"))[1] == "global"


@pytest.mark.parametrize("split", ["validation", "test"])
def test_cohort_fit_rejects_holdout(split):
    with pytest.raises(ValueError, match="only consume training"):
        benchmark.fit_cohorts([training_row(split=split)], "electricity")


def test_cohort_excludes_invalid_fuel_not_zero_fill():
    rows = [training_row(value="1500"), {**training_row(value="999999"), "ElecValFlag2024": "E"},
            training_row(value="")]
    fitted = benchmark.fit_cohorts(rows, "electricity")
    assert fitted["n_train"] == 1
    assert fitted["global"] == 1500


@pytest.mark.training_data
def test_source_register_matches_actual_cached_hashes_and_factors():
    register = json.loads((ref.ROOT / "data/source_register.json").read_text())
    need = next(s for s in register["sources"] if s["id"] == "DESNZ_NEED_2026")
    assert need["licence"]["identifier"] == "OGL-UK-3.0"
    for source in need["files"]:
        assert ref.sha(ref.ROOT / source["file"]) == source["sha256"]
    carbon = next(s for s in register["sources"] if s["id"] == "DESNZ_GHG_2026")
    assert carbon["factors"]["electricity"]["value"] == "0.13096"
    assert carbon["factors"]["gas"]["cell"] == "D42"
