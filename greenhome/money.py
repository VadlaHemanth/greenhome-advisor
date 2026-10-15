"""Model-free GBP comparisons over the engine's feasible, affordable packages."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, field_validator

from greenhome import engine


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


UnitPence = Annotated[
    Decimal, Field(ge=0, le=200, allow_inf_nan=False),
    WithJsonSchema({"type": "number", "minimum": 0, "maximum": 200}, mode="validation"),
]
StandingPence = Annotated[
    Decimal, Field(ge=0, le=1000, allow_inf_nan=False),
    WithJsonSchema({"type": "number", "minimum": 0, "maximum": 1000}, mode="validation"),
]


class TariffInput(StrictModel):
    """Explicit pence, never GBP/kWh; no implicit illustrative tariff."""

    electricity_pence: UnitPence | None = None
    gas_pence: UnitPence | None = None
    source: Literal["illustrative", "user_entered"] = "user_entered"
    as_of: date | None = None
    electricity_standing_before_pence_per_day: StandingPence | None = None
    electricity_standing_after_pence_per_day: StandingPence | None = None
    gas_standing_before_pence_per_day: StandingPence | None = None
    gas_standing_after_pence_per_day: StandingPence | None = None

    @field_validator(
        "electricity_pence", "gas_pence",
        "electricity_standing_before_pence_per_day",
        "electricity_standing_after_pence_per_day",
        "gas_standing_before_pence_per_day", "gas_standing_after_pence_per_day",
        mode="before",
    )
    @classmethod
    def finite_number(cls, value):
        if value is None:
            return value
        if type(value) not in (int, float, Decimal):
            raise ValueError("A finite number of pence is required.")
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("A finite number of pence is required.")
        return result

    @field_validator("as_of", mode="before")
    @classmethod
    def iso_date(cls, value):
        if value is None or type(value) is date:
            return value
        if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError("Use an ISO calendar date or null.")
        return date.fromisoformat(value)


Number = Annotated[float, Field(allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
CostRange = Annotated[list[Nonnegative], Field(min_length=2, max_length=2)]


class Amounts(StrictModel):
    before_gbp: Number | None
    after_gbp: Number | None
    saving_gbp: Number | None


class Payback(StrictModel):
    low: Nonnegative
    high: Nonnegative


class MoneyResult(StrictModel):
    status: Literal["available", "partial", "unavailable"]
    electricity: Amounts
    gas: Amounts
    total: Amounts
    monthly_average_gbp: Number | None
    payback_years: Payback | None
    cost_gbp: CostRange
    standing_charge_note: str


class MoneyPackage(StrictModel):
    id: str
    retrofits: Annotated[list[str], Field(min_length=1, max_length=5)]
    cost_gbp: CostRange
    net_saving_kwh: Number | None
    improvement_percent: Number | None
    carbon_reduction_kgco2e: Number | None
    money_saving_gbp: Number | None
    recommendation_reason: str


class Picks(StrictModel):
    energy: str | None
    bills: str | None
    lowest_cost: str | None


class TariffOutput(StrictModel):
    """Numeric JSON rates, rather than Pydantic's default Decimal strings."""

    electricity_pence: Annotated[Number, Field(ge=0, le=200)] | None
    gas_pence: Annotated[Number, Field(ge=0, le=200)] | None
    source: Literal["illustrative", "user_entered"]
    as_of: str | None
    electricity_standing_before_pence_per_day: Annotated[Number, Field(ge=0, le=1000)] | None
    electricity_standing_after_pence_per_day: Annotated[Number, Field(ge=0, le=1000)] | None
    gas_standing_before_pence_per_day: Annotated[Number, Field(ge=0, le=1000)] | None
    gas_standing_after_pence_per_day: Annotated[Number, Field(ge=0, le=1000)] | None


class MoneyPlanResponse(StrictModel):
    money: MoneyResult
    packages: list[MoneyPackage]
    picks: Picks
    tariffs: TariffOutput
    warnings: list[str]


PENNY = Decimal("0.01")
PENCE_PER_POUND = Decimal("100")
DAYS_PER_YEAR = Decimal("365")


def _rounded(value: Decimal) -> Decimal:
    result = value.quantize(PENNY, rounding=ROUND_HALF_UP)
    return abs(result) if result == 0 else result


def _json_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _standing_pair(tariffs: TariffInput, fuel: str) -> tuple[Decimal, Decimal, str]:
    before = getattr(tariffs, f"{fuel}_standing_before_pence_per_day")
    after = getattr(tariffs, f"{fuel}_standing_after_pence_per_day")
    if before is None or after is None:
        qualifier = "Incomplete pair; " if before is not None or after is not None else ""
        return Decimal(0), Decimal(0), (
            f"{fuel.capitalize()}: {qualifier}standing charges excluded from before/after totals; "
            "unchanged charges assumed for the saving, not assumed to be zero."
        )
    return before * DAYS_PER_YEAR / PENCE_PER_POUND, after * DAYS_PER_YEAR / PENCE_PER_POUND, (
        f"{fuel.capitalize()}: supplied before/after standing charges included for 365 days."
    )


def calculate_money(home: dict, scenario: dict, tariffs: TariffInput) -> dict:
    """Price a validated engine scenario, preserving unknowns and signed changes.

    Quantize each fuel's annual before/after amounts first. Derive savings and
    totals from those displayed amounts so arithmetic reconciles to the penny.
    """
    fuels, notes = {}, []
    for fuel in ("electricity", "gas"):
        rate = getattr(tariffs, f"{fuel}_pence")
        standing_before, standing_after, note = _standing_pair(tariffs, fuel)
        notes.append(note)

        def amount(kwh, standing):
            if kwh is None or rate is None:
                return None
            return _rounded(Decimal(str(kwh)) * rate / PENCE_PER_POUND + standing)

        before = amount(home.get(f"{fuel}_kwh"), standing_before)
        after = amount(scenario.get(f"{fuel}_kwh"), standing_after)
        saving = None if before is None or after is None else _rounded(before - after)
        fuels[fuel] = {"before_gbp": before, "after_gbp": after, "saving_gbp": saving}
    complete = all(fuel["saving_gbp"] is not None for fuel in fuels.values())
    totals = {
        key: sum((fuel[key] for fuel in fuels.values()), Decimal(0)) if complete else None
        for key in ("before_gbp", "after_gbp", "saving_gbp")
    }
    status = "available" if complete else (
        "partial" if any(value is not None for fuel in fuels.values() for value in fuel.values())
        else "unavailable"
    )
    saving = totals["saving_gbp"]
    costs = [_rounded(Decimal(str(value))) for value in scenario["cost_gbp"]]
    payback = None
    if saving is not None and saving > 0:
        payback = {key: float(_rounded(cost / saving)) for key, cost in zip(("low", "high"), costs)}
    gas_after = scenario.get("gas_kwh")
    if gas_after is not None and gas_after > 0:
        notes.append("Gas use is retained; no standing-charge removal is inferred from a heat pump.")
    result = {
        "status": status,
        **{fuel: {key: _json_number(value) for key, value in amounts.items()}
           for fuel, amounts in fuels.items()},
        "total": {key: _json_number(value) for key, value in totals.items()},
        "monthly_average_gbp": None if saving is None else float(_rounded(saving / Decimal(12))),
        "payback_years": payback,
        "cost_gbp": [float(value) for value in costs],
        "standing_charge_note": " ".join(notes),
    }
    return MoneyResult.model_validate(result).model_dump()


def _pick(packages: list[dict], metric: str | None = None) -> str | None:
    candidates = packages if metric is None else [
        package for package in packages
        if package[metric] is not None and package[metric] > 0
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda package: (
        0 if metric is None else -package[metric], package["cost_gbp"][1], package["id"],
    ))["id"]


def _zero_marginal_measures(home: dict, ids: tuple[str, ...], scenarios: dict) -> list[str]:
    """Find removals that leave both modelled fuel outputs unchanged.

    A measure's standalone relevance is insufficient: PV can offset new heat
    pump demand, or fully cover demand that fabric work would otherwise reduce.
    Missing subpackages (e.g. zero-benefit standalone PV) are evaluated through
    the engine's model-free kernel and cached only for this request.
    """
    full = scenarios[ids]
    redundant = []
    for rid in ids:
        smaller = tuple(other for other in ids if other != rid)
        if smaller not in scenarios:
            scenarios[smaller] = engine.calculate_scenario(home, list(smaller))
        if all(full[fuel] == scenarios[smaller][fuel] for fuel in ("electricity_kwh", "gas_kwh")):
            redundant.append(rid)
    return redundant


def money_plan(home: dict, selected_retrofits: list[str], tariffs: TariffInput | dict) -> dict:
    """Return a validated money/package response without ML, persistence or I/O."""
    tariffs = tariffs if isinstance(tariffs, TariffInput) else TariffInput.model_validate(tariffs)
    if (not isinstance(selected_retrofits, list) or len(selected_retrofits) > len(engine.RETROFITS)
            or any(type(rid) is not str or rid not in engine.RETROFITS for rid in selected_retrofits)):
        raise ValueError("Selected retrofits must be a bounded list of known IDs.")
    screening = engine.screen_home(home)
    selected = tuple(sorted(set(selected_retrofits), key=lambda rid: (engine.RETROFITS[rid]["order"], rid)))
    scenarios = {tuple(package["retrofits"]): package["scenario"] for package in screening["packages"]}
    if selected not in scenarios:
        raise ValueError("The selection is infeasible, unsupported or exceeds the upper-cost budget.")
    money = calculate_money(screening["home"], scenarios[selected], tariffs)
    marginal_scenarios = dict(scenarios)
    redundant = {
        ids: _zero_marginal_measures(screening["home"], ids, marginal_scenarios)
        for ids in scenarios
    }
    packages = []
    for ids, scenario in scenarios.items():
        if not ids or redundant[ids]:
            continue
        priced = calculate_money(screening["home"], scenario, tariffs)
        packages.append({
            "id": "+".join(ids), "retrofits": list(ids), "cost_gbp": priced["cost_gbp"],
            "net_saving_kwh": scenario["net_saving_kwh"],
            "improvement_percent": scenario["improvement_percent"],
            "carbon_reduction_kgco2e": scenario["carbon_reduction_kgco2e"],
            "money_saving_gbp": priced["total"]["saving_gbp"],
            "recommendation_reason": "",
        })
    packages.sort(key=lambda package: (package["cost_gbp"][1], package["id"]))
    picks = {
        "energy": _pick(packages, "improvement_percent"),
        "bills": _pick(packages, "money_saving_gbp"),
        "lowest_cost": _pick(packages),
    }
    reasons = {
        "energy": "Largest known purchased-energy percentage reduction among compared packages.",
        "bills": "Largest positive estimated annual bill saving at the supplied rates among compared packages.",
        "lowest_cost": "Lowest upper indicative installation cost among compared nonempty packages.",
    }
    for package in packages:
        chosen = [reason for objective, reason in reasons.items() if picks[objective] == package["id"]]
        if not chosen:
            chosen = ["Feasible, energy-relevant alternative within the supplied upper-cost budget, if any."]
        if package["money_saving_gbp"] is None:
            chosen.append("Bill comparison is unavailable: both fuel readings and unit rates are required.")
        elif package["money_saving_gbp"] < 0:
            chosen.append("Estimated bills increase; the signed loss is retained.")
        if screening["potential"]["status"] in ("insufficient_evidence", "unsupported"):
            chosen.append("Evidence or model coverage is incomplete; this is not a whole-home optimum.")
        package["recommendation_reason"] = " ".join(chosen)
    warnings = [
        *screening["warnings"], *scenarios[selected]["warnings"],
        "Screening estimates for England and Wales, in GBP; not installer quotes or savings guarantees.",
        "Installation cost ranges are prototype assumptions. No grants or subsidies are assumed.",
        "Monthly average means annual bill saving divided by 12, not a predicted monthly bill.",
        "Simple payback excludes financing, maintenance, replacement, discounting, tariff changes and export revenue.",
        "Standing-charge inputs apply to every compared package; no tariff or supply disconnection is inferred.",
        money["standing_charge_note"],
    ]
    for rid in redundant[selected]:
        info = engine.RETROFITS[rid]
        low, high = info["cost_gbp"]
        warnings.append(
            f"Selected {rid} ({info['name']}; GBP {low:g}–{high:g} indicative installation cost) "
            "has zero marginal modelled purchased-energy benefit in this combination. "
            "Your explicit selection and full costs are preserved; this package is omitted "
            "from comparisons and picks."
        )
    if tariffs.source == "illustrative":
        warnings.append("Illustrative rates explicitly supplied by the client; not a current-tariff claim.")
    else:
        warnings.append("User-entered rates and their as-of date are not independently verified.")
    if money["status"] != "available":
        warnings.append("Both annual fuel readings and both unit rates are required for totals and bill picks; missing is not zero.")
    if money["total"]["saving_gbp"] is not None and money["total"]["saving_gbp"] < 0:
        warnings.append("Estimated annual bills increase. Negative savings are retained; simple payback is unavailable.")
    if picks["bills"] is None and money["status"] == "available":
        warnings.append("No compared package has a positive estimated annual bill saving at these rates.")
    tariff_output = {
        key: float(value) if isinstance(value, Decimal) else value.isoformat() if isinstance(value, date) else value
        for key, value in tariffs.model_dump().items()
    }
    return MoneyPlanResponse.model_validate({
        "money": money, "packages": packages, "picks": picks, "tariffs": tariff_output,
        "warnings": list(dict.fromkeys(warnings)),
    }).model_dump(mode="json")
