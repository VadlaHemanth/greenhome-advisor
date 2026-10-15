"""Finite stress-grid decision support, not probabilistic or market validation."""
from __future__ import annotations

from collections import defaultdict
from itertools import product
import math

from greenhome import engine

STRESS_VALUES = {
    "space_heat_fraction": (0.6, 0.8, 1.0),
    "heat_pump_spf": (2.0, 3.0, 4.0),
    "solar_self_consumption_fraction": (0.25, 0.45, 0.65),
}
TOLERANCE_KWH = 1e-8
ASSUMPTIONS = [
    "Analyst-selected stress cases, not probabilities, calibrated uncertainty or measured outcomes.",
    "Only space-heating fraction, heat-pump SPF and solar self-consumption vary hypothetically. "
    "Supplied zero fractions stay fixed at zero. All supplied meter totals, property facts, "
    "permissions, exclusions, costs and other parameters stay fixed.",
    "The nominal calculation uses the supplied assumptions, with disclosed engine defaults for omissions. "
    "A distinct nominal point is included alongside up to 27 stress combinations; inputs are never clamped.",
    "Only packages with positive nominal energy benefit (plus no-action) are compared. "
    "A hypothetical change to a fixed zero cannot create an actionable recommendation.",
    "Minimax regret minimises the largest purchased-energy saving gap to the best feasible package "
    "in each tested scenario. Ties within 1e-8 kWh/year use lower upper cost, then catalogue-ordered IDs.",
    "Budget feasibility uses upper indicative package costs. Unknown permissions never become approvals.",
    "Carbon and costs are reported separately, not blended into the energy objective. "
    "Synthetic property-value predictions and cohort ML predictions do not influence ranking.",
    "Ranges are extrema of a finite analyst grid, not confidence intervals. "
    "Performance outside the tested assumptions and real-world savings are not guaranteed.",
]
QUESTIONS = {
    "space_heat_fraction": "Can you estimate the share of heating-fuel use serving space heating, "
    "separately from hot water and cooking?",
    "heat_pump_spf": "Can an installer provide a site-specific seasonal heat-pump performance estimate?",
    "solar_self_consumption_fraction": "Can you obtain daytime electricity-load evidence and a "
    "roof/yield assessment to refine expected solar self-consumption?",
}


def _unavailable(reason: str, field: str | None = None) -> dict:
    return {
        "status": "unavailable", "objective": "purchased_energy",
        "recommended_package": None, "nominal_package": None, "greedy_package": None,
        "stable": None, "scenario_count": None, "feasible_package_count": None,
        "regret_kwh": None,
        "next_check": {
            "field": field,
            "question": "Confirm the missing evidence or obtain an assessment beyond the supported model before comparing packages.",
            "reason": reason,
        },
        "packages": None, "scenarios": None,
        "assumptions": list(ASSUMPTIONS), "warnings": [reason],
    }


def _stress_grid(home: dict) -> list[dict]:
    axes = [(0.0,) if home.get(field, engine.DEFAULT_ASSUMPTIONS[field]) == 0 else values
            for field, values in STRESS_VALUES.items()]
    return [dict(zip(STRESS_VALUES, values)) for values in product(*axes)]


def stress_points(home: dict) -> list[dict]:
    """Up to 27 stresses, preserving fixed zeros, plus a distinct nominal point."""
    points = _stress_grid(home)
    nominal = {field: home.get(field, engine.DEFAULT_ASSUMPTIONS[field]) for field in STRESS_VALUES}
    if nominal not in points:
        points.append(nominal)
    return points


def _tie_key(package: dict):
    return package["cost_gbp"][1], tuple(package["retrofits"])


def _choose(values: list[float], packages: list[dict], *, maximise: bool) -> int:
    best = max(values) if maximise else min(values)
    candidates = [i for i, value in enumerate(values) if abs(value - best) <= TOLERANCE_KWH]
    return min(candidates, key=lambda i: _tie_key(packages[i]))


def _next_evidence(points, winners, regrets, packages, robust_regret) -> dict:
    """Perfect-resolution, worst-branch information check; no probability weights."""
    candidates = []
    for priority, field in enumerate(STRESS_VALUES):
        branches = defaultdict(list)
        matched = defaultdict(set)
        for index, point in enumerate(points):
            branches[point[field]].append(index)
            other_values = tuple(point[key] for key in STRESS_VALUES if key != field)
            matched[other_values].add(winners[index])
        conditional_regrets = [
            min(max(row[s] for s in indices) for row in regrets)
            for indices in branches.values()
        ]
        after = max(conditional_regrets)
        reduction = max(0.0, robust_regret - after)
        switches = sum(len(indices) > 1 for indices in matched.values())
        candidates.append((reduction, switches, -priority, field, after))
    reduction, switches, _, field, after = max(candidates)
    if reduction <= TOLERANCE_KWH and not switches:
        return {
            "field": None,
            "question": "Review the assumptions jointly before choosing a package.",
            "reason": "No single-variable check isolates a lower worst-case regret or a winner switch "
            "on this finite grid. Do not infer a probability or a guaranteed benefit from more data.",
        }
    if reduction > TOLERANCE_KWH:
        reason = (
            f"If this assumption were resolved exactly, the worst remaining conditional minimax "
            f"regret would fall from {robust_regret:.1f} to {after:.1f} kWh/year on this grid. "
            "This is a model-based information check, not a predicted measurement result or saving."
        )
    else:
        reason = (
            "Changing only this assumption changes the energy-optimal package in a matched stress "
            "comparison. Resolving it alone does not reduce the worst remaining grid regret. "
            "The switching comparisons are not probabilities."
        )
    return {"field": field, "question": QUESTIONS[field], "reason": reason}


def _no_action_check(home: dict) -> dict:
    if home.get("solar_kwp") is None:
        return {
            "field": "solar_kwp", "question": "Confirm whether solar is already installed.",
            "reason": "Unknown solar capacity prevents incremental savings estimates; it is not zero opportunity.",
        }
    if home.get("solar_kwp"):
        return {
            "field": None,
            "question": "Obtain behind-the-meter load and existing solar self-consumption evidence.",
            "reason": "The current engine withholds electrical-demand changes and fuel switching for existing PV. "
            "A no-op is not evidence that the home has no improvement potential.",
        }
    for field, question in (
        ("listed_building", "Confirm listed-building status or the required installation consent."),
        ("roof_access", "Confirm roof access and permission before considering roof interventions."),
        ("heat_pump_ready", "Confirm installer readiness before considering a heating-system change."),
    ):
        if home.get(field) is None:
            return {
                "field": field, "question": question,
                "reason": "Unknown eligibility is a hard gate, not a probability or assumed refusal.",
            }
    return {
        "field": None, "question": "Review the budget, existing measures and screening limitations.",
        "reason": "No actionable energy-saving package was found under the confirmed constraints. "
        "This is not a stable-choice success or proof that other improvements cannot help.",
    }


def decision_check(home: dict) -> dict:
    """Return the React handoff schema using shared, entirely model-free search."""
    errors = engine.validate_home(home)
    if errors:
        raise ValueError("Invalid home input for decision check.")
    for field in ("electricity_kwh", "gas_kwh"):
        if home.get(field) is None:
            return _unavailable(
                "Annual electricity and gas must both be known; missing consumption is not zero.", field
            )
    total = home["electricity_kwh"] + home["gas_kwh"]
    try:
        finite_total = math.isfinite(total)
    except OverflowError:
        finite_total = False
    if not finite_total or total <= 0:
        return _unavailable("Purchased-energy baseline is zero or non-finite; no ranking is available.")

    assessment = engine.screen_home(home)
    baseline = assessment["home"]
    if len(assessment["packages"]) == 1 and assessment["potential"]["status"] in (
        "insufficient_evidence", "unsupported",
    ):
        result = _unavailable(assessment["potential"]["reason"])
        result["next_check"] = _no_action_check(baseline)
        result["warnings"] = list(dict.fromkeys(result["warnings"] + assessment["warnings"]))
        return result
    budget = baseline.get("budget_gbp")
    points = stress_points(baseline)
    grid_count = len(_stress_grid(baseline))
    packages, savings = [], []
    for option in assessment["packages"]:
        selected, nominal = option["retrofits"], option["scenario"]
        cost = nominal["cost_gbp"]
        row = [
            engine.calculate_scenario({**baseline, **point}, selected)["net_saving_kwh"]
            for point in points
        ]
        values = [
            *row, nominal["net_saving_kwh"], nominal["carbon_reduction_kgco2e"],
            nominal["electricity_saving_kwh"], nominal["gas_saving_kwh"],
        ]
        if any(value is None or not math.isfinite(value) for value in values):
            return _unavailable("The calculator could not provide finite, complete per-fuel estimates.")
        packages.append({
            "retrofits": selected, "cost_gbp": cost,
            "nominal_saving_kwh": nominal["net_saving_kwh"],
            "min_saving_kwh": min(row), "max_saving_kwh": max(row),
            "max_regret_kwh": 0.0,
            "nominal_carbon_kgco2e": nominal["carbon_reduction_kgco2e"],
            # Additive detail: retain signed per-fuel changes, never just the aggregate.
            "nominal_electricity_saving_kwh": nominal["electricity_saving_kwh"],
            "nominal_gas_saving_kwh": nominal["gas_saving_kwh"],
        })
        savings.append(row)
    best_savings = [max(row[s] for row in savings) for s in range(len(points))]
    winners = [
        _choose([row[s] for row in savings], packages, maximise=True)
        for s in range(len(points))
    ]
    regrets = [
        [max(0.0, best_savings[s] - value) for s, value in enumerate(row)]
        for row in savings
    ]
    for package, row in zip(packages, regrets):
        package["max_regret_kwh"] = max(row)
    robust = _choose([p["max_regret_kwh"] for p in packages], packages, maximise=False)
    nominal = _choose([p["nominal_saving_kwh"] for p in packages], packages, maximise=True)
    robust_regret = packages[robust]["max_regret_kwh"]
    no_action = len(packages) == 1 or max(p["nominal_saving_kwh"] for p in packages) <= TOLERANCE_KWH
    stable = None if no_action else robust_regret <= TOLERANCE_KWH
    warnings = list(assessment["warnings"])
    warnings.extend(engine.calculate_scenario(baseline, assessment["selected_retrofits"])["warnings"])
    warnings.extend(
        f"{r['name']} withheld: {r['reason']}"
        for r in assessment["recommendations"] if not r["feasible"]
    )
    if no_action:
        warnings.append("Only no-action or zero-benefit choices are supported. "
                        "Do not count this as a stable or improved retrofit decision.")
        next_check = _no_action_check(baseline)
    elif stable:
        next_check = {
            "field": None,
            "question": "No additional check changes the choice within the tested assumption grid.",
            "reason": "The recommended package is energy-optimal across the tested cases. "
            "This only covers currently feasible packages and the listed assumptions, not unknown permissions "
            "or unmodelled risks. It is not a guarantee.",
        }
    else:
        next_check = _next_evidence(points, winners, regrets, packages, robust_regret)
    if budget is None:
        warnings.append("No budget was supplied; comparison is not constrained by affordability.")
    return {
        "status": "available", "objective": "purchased_energy",
        "recommended_package": list(packages[robust]["retrofits"]),
        "nominal_package": list(packages[nominal]["retrofits"]),
        "greedy_package": list(assessment["selected_retrofits"]),
        "stable": stable, "scenario_count": len(points), "feasible_package_count": len(packages),
        "regret_kwh": robust_regret, "next_check": next_check,
        "packages": packages,
        "scenarios": [
            {"id": f"stress-{s + 1:02d}" if s < grid_count else "nominal",
             "assumptions": dict(point), "best_package": list(packages[winners[s]]["retrofits"]),
             "best_saving_kwh": best_savings[s]}
            for s, point in enumerate(points)
        ],
        "assumptions": list(ASSUMPTIONS), "warnings": list(dict.fromkeys(warnings)),
    }
