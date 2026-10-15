"""Explainable screening calculations for UK homes, not an EPC assessment."""
from __future__ import annotations

from copy import deepcopy
from math import floor, isfinite
from typing import Any

EMISSIONS = {
    "electricity": 0.13096,
    "gas": 0.18231,
    "unit": "kgCO2e/kWh",
    "year": 2026,
    "boundary": "UK operational electricity generation and mains gas combustion; excludes upstream energy, T&D, embodied carbon and refrigerants",
    "gas_basis": "gross calorific value",
    "url": "https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026",
}
SOURCES = [
    {"label": "DESNZ 2026 conversion factors", "url": EMISSIONS["url"]},
    {"label": "NEED 2026 anonymised data", "url": "https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026"},
]
RETROFITS = {
    "loft_insulation": {"name": "Loft insulation", "cost_gbp": [800, 1600], "order": 0},
    "double_glazing": {"name": "Double glazing", "cost_gbp": [4000, 10000], "order": 1},
    "smart_controls": {"name": "Smart heating controls", "cost_gbp": [150, 350], "order": 2},
    "heat_pump": {"name": "Air-source heat pump", "cost_gbp": [9000, 15000], "order": 3},
    "solar_pv": {"name": "3 kWp rooftop solar", "cost_gbp": [4500, 7000], "order": 4},
}
EPC_SCORES = {"A": 100, "A/B": 92.5, "B": 85, "C": 70, "D": 55, "E": 40, "F": 25, "G": 10}
DEFAULT_ASSUMPTIONS = {
    "space_heat_fraction": 0.80,
    "boiler_efficiency": 0.85,
    "heat_pump_spf": 3.0,
    "solar_yield_kwh_per_kwp": 900.0,
    "solar_self_consumption_fraction": 0.45,
}
NUMERIC_BOUNDS = {
    "electricity_kwh": (0, 10_000_000), "gas_kwh": (0, 10_000_000),
    "solar_kwp": (0, 10_000), "budget_gbp": (0, 1_000_000_000),
    "floor_area_m2": (0.01, 100_000), "current_value_gbp": (0, 1_000_000_000_000),
}


def demo_homes() -> list[dict]:
    """Fictional scenarios, explicitly separated from NEED observations."""
    base = {
        "age_band": 2, "region": "E12000007", "heating": "gas_boiler",
        "solar_kwp": 0.0, "smart_controls": False, "roof_access": True,
        "listed_building": False, "consent_confirmed": False, "heat_pump_ready": True,
        "current_value_gbp": 350000.0, "budget_gbp": None, "data_kind": "synthetic_demo",
        **DEFAULT_ASSUMPTIONS,
    }
    return [
        {**base, "property_id": "DEMO-01", "property_type": "Semi detached",
         "floor_area_m2": 100.0, "epc_rating": "E", "electricity_kwh": 4800.0,
         "gas_kwh": 12000.0, "insulation": "poor", "glazing": "single"},
        {**base, "property_id": "DEMO-02", "property_type": "Flat", "floor_area_m2": 65.0,
         "epc_rating": "D", "electricity_kwh": 2700.0, "gas_kwh": 7000.0,
         "insulation": "partial", "glazing": "double", "roof_access": False,
         "heat_pump_ready": False, "current_value_gbp": 220000.0, "budget_gbp": 1000.0},
        {**base, "property_id": "DEMO-03", "property_type": "Detached", "floor_area_m2": 160.0,
         "epc_rating": "B", "electricity_kwh": 3500.0, "gas_kwh": 0.0,
         "heating": "heat_pump", "insulation": "good", "glazing": "triple",
         "smart_controls": True, "solar_kwp": 4.0, "current_value_gbp": 480000.0},
        {**base, "property_id": "DEMO-04", "property_type": "Mid terrace", "floor_area_m2": None,
         "epc_rating": None, "electricity_kwh": 2200.0, "gas_kwh": None,
         "insulation": "unknown", "glazing": "double", "heat_pump_ready": None},
    ]


def _number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except (OverflowError, ValueError):
        return False


def validate_home(home: dict) -> list[str]:
    errors = []
    if not isinstance(home, dict):
        return ["Home must be an object."]
    for key, (low, high) in NUMERIC_BOUNDS.items():
        value = home.get(key)
        if value is not None and (
            not _number(value) or not low <= value <= high
            or (key == "current_value_gbp" and value == 0)
        ):
            errors.append(f"{key} must be a finite number within the supported bounds "
                          f"[{low}, {high}] or missing; current value must be positive.")
    excluded = home.get("excluded_retrofits", [])
    if (not isinstance(excluded, list) or len(excluded) > len(RETROFITS)
            or any(not isinstance(rid, str) or rid not in RETROFITS for rid in excluded)):
        errors.append("excluded_retrofits must be a list of at most five known retrofit IDs.")
    elif len(excluded) != len(set(excluded)):
        errors.append("excluded_retrofits must not contain duplicate IDs.")
    choices = {
        "epc_rating": set(EPC_SCORES) | {None},
        "heating": {"gas_boiler", "heat_pump", "electric_resistance", "unknown", None},
        "insulation": {"poor", "partial", "good", "unknown", None},
        "glazing": {"single", "double", "triple", "unknown", None},
    }
    for key, allowed in choices.items():
        value = home.get(key)
        if not isinstance(value, (str, type(None))) or value not in allowed:
            errors.append(f"Unsupported {key}.")
    for key in ("smart_controls", "roof_access", "listed_building", "consent_confirmed", "heat_pump_ready"):
        if home.get(key) is not None and not isinstance(home[key], bool):
            errors.append(f"{key} must be true, false or unknown.")
    for key in ("space_heat_fraction", "solar_self_consumption_fraction"):
        value = home.get(key, DEFAULT_ASSUMPTIONS[key])
        if not _number(value) or not 0 <= value <= 1:
            errors.append(f"{key} must be between 0 and 1.")
    eta = home.get("boiler_efficiency", DEFAULT_ASSUMPTIONS["boiler_efficiency"])
    if not _number(eta) or not 0 < eta <= 1:
        errors.append("boiler_efficiency must be greater than 0 and no greater than 1.")
    spf = home.get("heat_pump_spf", DEFAULT_ASSUMPTIONS["heat_pump_spf"])
    if not _number(spf) or not 1 <= spf <= 6:
        errors.append("heat_pump_spf must be between 1 and 6.")
    solar_yield = home.get("solar_yield_kwh_per_kwp", DEFAULT_ASSUMPTIONS["solar_yield_kwh_per_kwp"])
    if not _number(solar_yield) or not 0 < solar_yield <= 2000:
        errors.append("solar_yield_kwh_per_kwp must be positive and at most 2000.")
    return errors


def _total(elec, gas):
    return None if elec is None or gas is None else elec + gas


def calculate_score(home: dict) -> dict:
    errors = validate_home(home)
    if errors:
        raise ValueError(" ".join(errors))
    area = home.get("floor_area_m2")
    purchased = _total(home.get("electricity_kwh"), home.get("gas_kwh"))
    intensity = purchased / area if purchased is not None and area else None
    intensity_score = None if intensity is None else max(0, min(100, (400 - intensity) / 3.5))
    values = [
        ("Energy efficiency", .25, EPC_SCORES.get(home.get("epc_rating"))),
        ("Energy consumption intensity", .20, intensity_score),
        ("Insulation", .15, {"poor": 20, "partial": 60, "good": 100}.get(home.get("insulation"))),
        ("Heating system", .15, {"gas_boiler": 60, "heat_pump": 90, "electric_resistance": 30}.get(home.get("heating"))),
        ("Windows and glazing", .10, {"single": 20, "double": 75, "triple": 100}.get(home.get("glazing"))),
        ("Renewable energy", .10, None if home.get("solar_kwp") is None else min(100, home["solar_kwp"] / 4 * 100)),
        ("Smart energy management", .05, None if home.get("smart_controls") is None else (100 if home["smart_controls"] else 0)),
    ]
    components = [{"name": n, "weight": w, "score": s,
                   "contribution": None if s is None else round(w * s, 4)} for n, w, s in values]
    issues = []
    for c in components:
        if c["score"] is None:
            issues.append(f"{c['name']}: required input unavailable.")
        elif c["score"] < 50:
            issues.append(f"{c['name']} is a weak component.")
    if any(c["score"] is None for c in components):
        total, label = None, "Unavailable"
    else:
        total = floor(sum(w * s for _, w, s in values) + .5)
        label = next(label for threshold, label in [(80, "Highly efficient"), (65, "Good"),
                     (50, "Moderate"), (30, "Poor"), (0, "Very poor")] if total >= threshold)
    return {"total": total, "classification": label, "components": components, "issues": issues,
            "intensity_kwh_m2": intensity, "flagged": label in ("Poor", "Very poor")}


def _eligibility(home: dict, retrofit: str) -> tuple[bool, str, str, str]:
    """Physical/evidence gates, before package budgets and marginal relevance."""
    def withheld(status, reason):
        return False, "Low", reason, status

    if retrofit in home.get("excluded_retrofits", []):
        return withheld("excluded", "Excluded or deferred by the household; not considered for this plan.")
    listed = home.get("listed_building") is True and home.get("consent_confirmed") is not True
    if home.get("solar_kwp") is None:
        return withheld("insufficient_evidence", "Confirm whether solar already exists before estimating incremental grid-import savings.")
    if retrofit == "solar_pv" and home["solar_kwp"] > 0:
        return withheld("unsupported", "Solar is already installed; expansion requires a separate site assessment.")
    if retrofit == "loft_insulation" and home.get("insulation") == "good":
        return withheld("already_installed", "Insulation is already good.")
    if retrofit == "double_glazing" and home.get("glazing") in ("double", "triple"):
        return withheld("already_installed", "The model covers single-to-double replacement only.")
    if retrofit == "smart_controls" and home.get("smart_controls") is True:
        return withheld("already_installed", "Controls are already present.")
    if retrofit == "heat_pump" and home.get("heating") in ("heat_pump", "electric_resistance"):
        return withheld("not_applicable", "This scenario supports replacing gas space heating only.")
    if retrofit == "solar_pv":
        if home["solar_self_consumption_fraction"] == 0:
            return withheld("no_modelled_benefit", "Supplied solar self-consumption is zero; this model excludes export income and predicts no purchased-energy benefit.")
    else:
        if home["space_heat_fraction"] == 0:
            return withheld("no_modelled_benefit", "Supplied space-heating fraction is zero; no space-heating energy benefit is modelled.")
        heating_fuel = "gas_kwh" if home.get("heating") == "gas_boiler" else "electricity_kwh"
        if home.get("heating") in ("gas_boiler", "heat_pump", "electric_resistance") and home.get(heating_fuel) == 0:
            # Existing PV can conceal electric heating load; imports alone cannot
            # establish a zero behind-the-meter heating demand.
            if not (home["solar_kwp"] > 0 and heating_fuel == "electricity_kwh"):
                return withheld("no_modelled_benefit", "The stated heating fuel has zero annual consumption; confirm the heating type and meter evidence. Zero is preserved, not replaced.")
    if home["solar_kwp"] > 0 and retrofit != "solar_pv":
        if home.get("heating") != "gas_boiler" or retrofit == "heat_pump":
            return withheld("unsupported", "Existing solar needs behind-the-meter total-load and self-consumption data for changes to electrical demand or fuel switching.")
    if retrofit != "smart_controls" and home.get("listed_building") is None and home.get("consent_confirmed") is not True:
        return withheld("insufficient_evidence", "Listed-building status is unknown; confirm the status or required installation consent first.")
    if retrofit in ("loft_insulation", "solar_pv"):
        if home.get("roof_access") is not True:
            return withheld("insufficient_evidence" if home.get("roof_access") is None else "not_applicable",
                            "Roof access or permission is absent or unconfirmed.")
        if listed:
            return withheld("insufficient_evidence", "Confirm the relevant building consent before a roof intervention.")
    if retrofit == "solar_pv":
        if home.get("electricity_kwh") is None:
            return withheld("insufficient_evidence", "Grid-import consumption is missing.")
        return True, "Medium", "Potential roof option, subject to shading, roof condition and electrical assessment.", "available"
    if home.get("heating") not in ("gas_boiler", "heat_pump", "electric_resistance"):
        return withheld("insufficient_evidence", "Heating type is unknown or outside this prototype's scope.")
    if home.get("electricity_kwh") is None or home.get("gas_kwh") is None:
        return withheld("insufficient_evidence", "Annual electricity and gas figures are required; missing gas is not zero.")
    if retrofit == "loft_insulation":
        if home.get("insulation") not in ("poor", "partial"):
            return withheld("insufficient_evidence", "Insulation condition is unknown.")
        return True, "High", "Reduce space-heating demand before considering heating-system changes.", "available"
    if retrofit == "double_glazing":
        if listed:
            return withheld("insufficient_evidence", "Window changes require confirmed consent for this property.")
        if home.get("glazing") != "single":
            return withheld("insufficient_evidence", "Glazing is unknown; the model covers single-to-double replacement only.")
        return True, "Medium", "Replace single glazing; confirm ventilation and window condition.", "available"
    if retrofit == "smart_controls":
        if home.get("smart_controls") is not False:
            return withheld("insufficient_evidence", "Controls status is unknown.")
        return True, "High", "Improve the heating schedule; achievable savings depend on existing use.", "available"
    if home.get("heat_pump_ready") is not True:
        return withheld("insufficient_evidence" if home.get("heat_pump_ready") is None else "not_applicable",
                        "Installer checks of space, emitters and electrical capacity are not confirmed.")
    if listed:
        return withheld("insufficient_evidence", "Installation consent is not confirmed.")
    return True, "Medium", "Space-heating replacement only; gas hot water/cooking remain in this model.", "available"


def calculate_scenario(home: dict, selected: list[str]) -> dict:
    """Signed arithmetic kernel; eligibility is enforced by screening/assess."""
    errors = validate_home(home)
    if errors:
        raise ValueError(" ".join(errors))
    if not isinstance(selected, list) or any(not isinstance(r, str) or r not in RETROFITS for r in selected):
        raise ValueError("Selected retrofits must be a list of known IDs.")
    selected = list(dict.fromkeys(selected))
    home = {**DEFAULT_ASSUMPTIONS, **home}
    e0, g0 = home.get("electricity_kwh"), home.get("gas_kwh")
    e1, g1 = e0, g0
    warnings = []
    assumptions = [
        "Screening estimates, not installer quotes, an EPC assessment or savings guarantees.",
        "Costs and demand-reduction parameters are disclosed prototype assumptions, not personalised market quotes.",
        "Gas inputs and boiler efficiency use a gross-calorific-value basis.",
        EMISSIONS["boundary"],
    ]
    cost = [sum(RETROFITS[r]["cost_gbp"][i] for r in selected) for i in (0, 1)]
    remaining = 1.0
    if "loft_insulation" in selected:
        reduction = .15 if home.get("insulation") == "poor" else .07
        remaining *= 1 - reduction
        assumptions.append(f"Loft work reduces remaining space-heating demand by {reduction:.0%}; it does not reduce hot water or appliance use.")
    if "double_glazing" in selected:
        remaining *= .90
        assumptions.append("Single-to-double glazing reduces remaining space-heating demand by 10%.")
    if "smart_controls" in selected:
        remaining *= .93
        assumptions.append("Controls reduce remaining space-heating demand by 7%; this may not hold for already careful usage.")
    f = home["space_heat_fraction"]
    heating = home.get("heating")
    if selected and any(r != "solar_pv" for r in selected):
        assumptions.append(f"{f:.0%} of the heating fuel's annual input is allocated to space heating; this split is an assumption unless measured.")
    if heating == "gas_boiler" and g0 is not None:
        gas_other = g0 * (1 - f)
        heat_after = g0 * f * home["boiler_efficiency"] * remaining
        if "heat_pump" in selected:
            e1 = None if e0 is None else e0 + heat_after / home["heat_pump_spf"]
            g1 = gas_other
            assumptions.append(f"Heat pump SPF {home['heat_pump_spf']:.2f}; gas boiler efficiency {home['boiler_efficiency']:.0%}; only space heating switches fuel.")
        elif remaining != 1:
            # Cancelling the same efficiency algebraically avoids underflow
            # when a valid, very small positive efficiency is supplied.
            g1 = gas_other + g0 * f * remaining
    elif heating in ("heat_pump", "electric_resistance") and e0 is not None and remaining != 1:
        e1 = e0 * (1 - f) + e0 * f * remaining
    if "solar_pv" in selected and e1 is not None:
        generation = 3 * home["solar_yield_kwh_per_kwp"]
        self_consumed = min(e1, generation * home["solar_self_consumption_fraction"])
        e1 -= self_consumed
        assumptions.append(f"New 3 kWp PV at {home['solar_yield_kwh_per_kwp']:g} kWh/kWp/year; {home['solar_self_consumption_fraction']:.0%} of generation self-consumed, capped by post-retrofit load.")
        warnings.append("Annual solar self-consumption is an approximation, not hourly matching. Export revenue and battery storage are excluded.")
    de = None if e0 is None or e1 is None else e0 - e1
    dg = None if g0 is None or g1 is None else g0 - g1
    net = _total(de, dg)
    base = _total(e0, g0)
    potential = net / base * 100 if net is not None and base is not None and base > 0 else None
    carbon = None if de is None or dg is None else de * EMISSIONS["electricity"] + dg * EMISSIONS["gas"]
    if base is None:
        warnings.append("A fuel baseline is missing; aggregate savings, carbon and improvement percentage are unavailable.")
    elif base == 0:
        warnings.append("Purchased-energy baseline is zero; percentage improvement is unavailable.")
    if de is not None and de < 0:
        warnings.append("Electricity use increases. A negative electricity saving is intentional.")
    if any(value is not None and not _number(value)
           for value in (e1, g1, de, dg, net, potential, carbon)):
        raise ValueError("The scenario must produce finite per-fuel and aggregate estimates.")
    return {
        "electricity_kwh": e1, "gas_kwh": g1, "electricity_saving_kwh": de,
        "gas_saving_kwh": dg, "net_saving_kwh": net, "improvement_percent": potential,
        "carbon_reduction_kgco2e": carbon, "cost_gbp": cost,
        "warnings": warnings, "assumptions": assumptions,
    }


def _known_saving(scenario: dict) -> float:
    """Partial-fuel PV estimates remain inspectable, never imply a known total."""
    if scenario["net_saving_kwh"] is not None:
        return scenario["net_saving_kwh"]
    return sum(scenario[field] or 0.0 for field in ("electricity_saving_kwh", "gas_saving_kwh"))


def screen_home(home: dict) -> dict:
    """Shared, model-free screening and at-most-32 nominal package evaluations.

    Recommendation feasibility includes relevance in at least one affordable
    nominal package. A zero standalone can therefore be jointly useful.
    """
    errors = validate_home(home)
    if errors:
        raise ValueError(" ".join(errors))
    h = deepcopy(home)
    h.setdefault("excluded_retrofits", [])
    warnings = []
    for k, v in DEFAULT_ASSUMPTIONS.items():
        if k not in h:
            h[k] = v
            warnings.append(f"Assumed {k}={v}; update if better information is available.")
    if h.get("data_kind") == "synthetic_demo":
        warnings.append("This is a fictional demonstration property, not a government household record.")
    else:
        warnings.append("User-entered information is not independently verified.")
    if h.get("solar_kwp", 0):
        warnings.append("Existing PV is included in current grid imports. Gas-only fabric/controls changes keep imports fixed; electrical demand changes and fuel switching need behind-the-meter data.")
    ids = sorted(RETROFITS, key=lambda rid: (RETROFITS[rid]["order"], rid))
    gates = {rid: _eligibility(h, rid) for rid in ids}
    physical = {rid for rid in ids if gates[rid][0]}
    all_packages = {}
    for mask in range(1 << len(ids)):
        selected = tuple(rid for i, rid in enumerate(ids) if mask & (1 << i))
        if physical.issuperset(selected):
            all_packages[selected] = calculate_scenario(h, list(selected))
    budget = h.get("budget_gbp")
    affordable = {ids_: scenario for ids_, scenario in all_packages.items()
                  if budget is None or scenario["cost_gbp"][1] <= budget}

    def relevant_measures(packages):
        return {
            rid for selected, scenario in packages.items() if _known_saving(scenario) > 0
            for rid in selected
            if _known_saving(scenario) > _known_saving(
                all_packages[tuple(other for other in selected if other != rid)])
        }

    relevant = relevant_measures(affordable)
    unconstrained_relevant = relevant_measures(all_packages)
    recommendations = []
    for rid in ids:
        info = RETROFITS[rid]
        feasible, suitability, reason, status = gates[rid]
        standalone = all_packages.get((rid,))
        if feasible and rid not in relevant:
            feasible, suitability = False, "Low"
            if rid in unconstrained_relevant:
                status = "no_affordable_option"
                reason = "No energy-relevant package containing this measure fits the stated upper-cost budget."
            else:
                status = "no_modelled_benefit"
                reason = "No positive nominal marginal purchased-energy benefit is supported, either alone or jointly."
        joint_only = feasible and _known_saving(standalone) <= 0
        if joint_only:
            reason += " No standalone energy saving: useful only jointly with a load-changing measure in an affordable package."
        recommendations.append({
            "id": rid, "name": info["name"], "feasible": feasible, "suitability": suitability,
            "reason": reason, "status": status, "joint_only": joint_only,
            "cost_gbp": list(info["cost_gbp"]),
            "standalone": standalone if feasible else None,
        })
    packages = [{"retrofits": list(selected), "scenario": scenario}
                for selected, scenario in affordable.items()
                if relevant.issuperset(selected) and (not selected or _known_saving(scenario) > 0)]
    # Retain the established catalogue-order default, but remove redundant
    # nominal measures (including PV if its load-creating partner did not fit).
    selected, running = [], 0
    for rid in ids:
        price = RETROFITS[rid]["cost_gbp"][1]
        if rid in relevant and (budget is None or running + price <= budget):
            selected.append(rid)
            running += price
    for rid in list(reversed(selected)):
        smaller = [other for other in selected if other != rid]
        if _known_saving(all_packages[tuple(selected)]) <= _known_saving(all_packages[tuple(smaller)]):
            selected = smaller
    baseline = _total(h.get("electricity_kwh"), h.get("gas_kwh"))
    missing = [r for r in recommendations if r["status"] == "insufficient_evidence"
               and (budget is None or r["cost_gbp"][1] <= budget)]
    unsupported = [r for r in recommendations if r["status"] == "unsupported"]
    # If nothing could be evaluated at all, a small budget must not turn an
    # unknown opportunity into an asserted lack of modelled benefit.
    if not missing and not relevant and not unconstrained_relevant:
        missing = [r for r in recommendations if r["status"] == "insufficient_evidence"]
    if baseline is None or baseline == 0:
        status, reason = "insufficient_evidence", "Both annual fuel totals and a positive purchased-energy baseline are required; missing is not zero."
    elif missing:
        status, reason = "insufficient_evidence", "Potential is incomplete: " + " ".join(r["reason"] for r in missing)
    elif len(packages) > 1:
        status, reason = "available", "Nominal potential among supported, energy-relevant packages under the stated upper-cost budget."
        if unsupported:
            reason += " Outside this comparison: " + " ".join(r["reason"] for r in unsupported)
    elif unconstrained_relevant:
        status, reason = "no_affordable_option", "Energy-saving options exist, but none fits the stated upper-cost budget."
    elif unsupported:
        status, reason = "unsupported", "Potential cannot be established within this model: " + " ".join(r["reason"] for r in unsupported)
    else:
        status, reason = "no_modelled_benefit", "No positive purchased-energy benefit is modelled under the supplied facts, exclusions and confirmed constraints."
    potential = {"status": status, "reason": reason}
    if status != "available":
        warnings.append(reason)
        if status in ("insufficient_evidence", "unsupported"):
            warnings.append("An unchanged-home scenario is not an estimate of unknown opportunity.")
    warnings.extend(r["reason"] for r in recommendations if r["status"] == "no_modelled_benefit")
    if budget is None:
        warnings.append("No budget was supplied; comparison is not constrained by affordability.")
    return {
        "home": h, "score": calculate_score(h), "recommendations": recommendations,
        "packages": packages, "selected_retrofits": selected, "potential": potential,
        "warnings": list(dict.fromkeys(warnings)),
    }


def assess(home: dict, selected_retrofits: list[str] | None = None) -> dict:
    screening = screen_home(home)
    h = screening["home"]
    warnings = screening["warnings"]
    recommendations = screening["recommendations"]
    possible = {r["id"] for r in recommendations if r["feasible"]}
    if selected_retrofits is None:
        selected = screening["selected_retrofits"]
    else:
        if not isinstance(selected_retrofits, list) or any(not isinstance(x, str) for x in selected_retrofits):
            raise ValueError("Selected retrofits must be a list of known IDs.")
        selected = list(dict.fromkeys(selected_retrofits))
        unknown = set(selected) - set(RETROFITS)
        if unknown:
            raise ValueError("Unknown retrofit: " + ", ".join(sorted(unknown)))
        invalid = set(selected) - possible
        if invalid:
            reasons = [r["reason"] for r in recommendations if r["id"] in invalid]
            raise ValueError("Infeasible retrofit selection. " + " ".join(reasons))
        if h.get("budget_gbp") is not None and sum(RETROFITS[r]["cost_gbp"][1] for r in selected) > h["budget_gbp"]:
            raise ValueError("Package upper indicative cost exceeds the budget. Select a smaller package.")
        if selected and _known_saving(calculate_scenario(h, selected)) <= 0:
            raise ValueError("No modelled energy benefit for this selection. Joint-only measures require a beneficial companion package.")
    selected.sort(key=lambda rid: RETROFITS[rid]["order"])
    value = {"status": "unavailable", "low_gbp": None, "high_gbp": None,
             "low_percent": None, "high_percent": None,
             "note": "Trained synthetic-reference value model is not available. No market premium is assumed."}
    benchmark = None
    try:
        from greenhome.ml import predict_energy_benchmark, predict_value_impact
        benchmark = predict_energy_benchmark(h)
        value = predict_value_impact(h, selected)
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        warnings.append(f"Model output unavailable ({type(exc).__name__}); calculations remain available.")
    return {
        "home": h, "score": screening["score"],
        "baseline": {"electricity_kwh": h.get("electricity_kwh"), "gas_kwh": h.get("gas_kwh"),
                     "purchased_kwh": _total(h.get("electricity_kwh"), h.get("gas_kwh"))},
        "recommendations": recommendations, "selected_retrofits": selected,
        "potential": screening["potential"],
        "scenario": calculate_scenario(h, selected), "value_impact": value,
        "energy_benchmark": benchmark, "warnings": warnings, "sources": deepcopy(SOURCES),
    }
