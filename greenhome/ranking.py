"""Nominal purchased-energy potential, not a selected no-op or ML ranking."""
from __future__ import annotations

from fractions import Fraction

from greenhome import engine

POLICY = "Maximum nominal purchased-energy reduction under each stated budget; upper indicative costs"
# Percentage points, not a relative tolerance or a fraction of total energy.
RANK_PERCENT_QUANTUM = Fraction(1, 1_000_000_000)
WARNINGS = [
    "Estimates under disclosed assumptions, not guaranteed outcomes.",
    "Only supported catalogue measures are compared. Exclusions and confirmed constraints apply; "
    "unavailable evidence is not a zero-opportunity estimate.",
    "Missing budgets mean no affordability constraint. Different stated budgets are not equal-cost comparisons.",
    "Ranking percentages use 1e-9 percentage-point rounding (nearest, half-up) for both ordering "
    "and ties. Fuel savings, carbon and nominal package selection are not rounded by this policy.",
]


def quantize_improvement_percent(value: float | None) -> float | None:
    """One transitive precision policy for published percentages, order and ties.

    Exact rational arithmetic on the float's decimal representation avoids a
    second binary rounding step at half-quanta and any ambient Decimal context.
    Half-quanta round away from zero; missing potential remains missing.
    """
    if value is None:
        return None
    scaled = Fraction(str(value)) / RANK_PERCENT_QUANTUM
    whole, remainder = divmod(abs(scaled.numerator), scaled.denominator)
    ticks = whole + (2 * remainder >= scaled.denominator)
    if scaled < 0:
        ticks = -ticks
    return float(ticks * RANK_PERCENT_QUANTUM)


def rank_homes(homes: list[dict]) -> dict:
    """Rank at most 100 homes at the declared 1e-9 percentage-point precision.

    Every home uses the same bounded engine search. No assessment, API import,
    model load, synthetic value prediction or stress-grid inference is needed.
    """
    if not isinstance(homes, list) or len(homes) > 100:
        raise ValueError("homes must be a list of at most 100 home objects.")
    for home in homes:
        if not isinstance(home, dict) or (
            home.get("property_id") is not None and not isinstance(home["property_id"], str)
        ):
            raise ValueError("Each home must be an object with a string property_id or no ID.")
    rows = []
    for home in homes:
        screened = engine.screen_home(home)
        h, score = screened["home"], screened["score"]
        status, reason = screened["potential"]["status"], screened["potential"]["reason"]
        baseline = engine._total(h.get("electricity_kwh"), h.get("gas_kwh"))
        known = status in ("available", "no_affordable_option", "no_modelled_benefit")
        # Keep nominal package optimization unquantized. The cross-home rank
        # precision policy below must not change energy or affordability choices.
        best = min(screened["packages"], key=lambda p: (
            -p["scenario"]["net_saving_kwh"] if known else 0,
            p["scenario"]["cost_gbp"][1], tuple(p["retrofits"]),
        )) if known else None
        scenario = best["scenario"] if best else None
        rows.append({
            "property_id": h.get("property_id"), "rank": None,
            "status": status, "reason": reason,
            "score": score["total"], "classification": score["classification"],
            "flagged": score["flagged"],
            "improvement_percent": quantize_improvement_percent(
                scenario["improvement_percent"] if scenario else None),
            "baseline_kwh": baseline,
            "selected_retrofits": list(best["retrofits"]) if best else [],
            "electricity_saving_kwh": scenario["electricity_saving_kwh"] if scenario else None,
            "gas_saving_kwh": scenario["gas_saving_kwh"] if scenario else None,
            "carbon_reduction_kgco2e": scenario["carbon_reduction_kgco2e"] if scenario else None,
            "cost_gbp": list(scenario["cost_gbp"]) if scenario else None,
            "budget_gbp": h.get("budget_gbp"),
        })
    rows.sort(key=lambda row: (
        row["improvement_percent"] is None,
        -(row["improvement_percent"] or 0),
        row["property_id"] or "",
    ))
    previous, rank = None, None
    for position, row in enumerate(rows, 1):
        value = row["improvement_percent"]
        if value is None:
            continue
        if value != previous:
            rank = position
        row["rank"] = rank
        previous = value
    return {"policy": POLICY, "rows": rows, "warnings": list(WARNINGS)}
