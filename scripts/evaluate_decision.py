"""Fixed synthetic decision experiment. No ML test data, tuning, retraining or API calls."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
from itertools import product
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenhome import decision, engine

PROTOCOL = {
    "version": 1,
    "population": "Six fictional DEMO-01 variants; not a household sample",
    "gas_kwh": [3000, 6000, 12000],
    "electricity_kwh": [2400, 4800],
    "budgets_gbp": [3000, 7350, 17000, 25000],
    "development_grid": {key: list(values) for key, values in decision.STRESS_VALUES.items()},
    "verification_grid": {
        "space_heat_fraction": [0.7, 0.9],
        "heat_pump_spf": [2.5, 3.5],
        "solar_self_consumption_fraction": [0.35, 0.55],
    },
    "strategies": ["greedy", "nominal", "robust"],
    "selection": "Freeze choices using nominal/development inputs, then evaluate all on 8 off-grid points",
    "ties": "1e-8 kWh, then lower upper cost, then catalogue-ordered IDs",
    "interpretation": "Designed model stress cases, not probabilities or empirical physical validation",
    "data_policy": "No observed or synthetic ML train/validation/test files are read; no post-result tuning",
}


def _write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate() -> dict:
    started = time.perf_counter()
    verification = [
        dict(zip(PROTOCOL["verification_grid"], values))
        for values in product(*PROTOCOL["verification_grid"].values())
    ]
    cases, dev_rows, verification_rows, timings = [], [], [], []
    violations = []
    base = engine.demo_homes()[0]
    for number, (gas, electricity, budget) in enumerate(product(
        PROTOCOL["gas_kwh"], PROTOCOL["electricity_kwh"], PROTOCOL["budgets_gbp"]
    ), 1):
        case_id = f"DECISION-{number:02d}"
        home = {**base, "property_id": case_id, "gas_kwh": gas,
                "electricity_kwh": electricity, "budget_gbp": budget}
        beginning = time.perf_counter()
        result = decision.decision_check(home)
        timings.append(time.perf_counter() - beginning)
        if result["status"] != "available":
            cases.append({"case_id": case_id, "status": "unavailable", "warnings": result["warnings"]})
            continue
        indexed = {tuple(item["retrofits"]): item for item in result["packages"]}
        plans = {
            "greedy": result["greedy_package"],
            "nominal": result["nominal_package"],
            "robust": result["recommended_package"],
        }
        for name, plan in plans.items():
            if tuple(plan) not in indexed or indexed[tuple(plan)]["cost_gbp"][1] > budget:
                violations.append({"case_id": case_id, "strategy": name})
        case = {
            "case_id": case_id, "status": "available", "gas_kwh": gas,
            "electricity_kwh": electricity, "budget_gbp": budget,
            "feasible_package_count": result["feasible_package_count"],
            "stable": result["stable"], "no_action": result["stable"] is None,
            "next_check": result["next_check"],
            "strategies": {
                name: {
                    "package": list(plan),
                    "cost_gbp": indexed[tuple(plan)]["cost_gbp"],
                    "nominal_saving_kwh": indexed[tuple(plan)]["nominal_saving_kwh"],
                    "nominal_electricity_saving_kwh": indexed[tuple(plan)]["nominal_electricity_saving_kwh"],
                    "nominal_gas_saving_kwh": indexed[tuple(plan)]["nominal_gas_saving_kwh"],
                    "nominal_carbon_kgco2e": indexed[tuple(plan)]["nominal_carbon_kgco2e"],
                    "development_max_regret_kwh": indexed[tuple(plan)]["max_regret_kwh"],
                } for name, plan in plans.items()
            },
        }
        observed_gaps = {name: [] for name in plans}
        for split, points, rows in (
            ("development", [row["assumptions"] for row in result["scenarios"]], dev_rows),
            ("verification", verification, verification_rows),
        ):
            for scenario_number, point in enumerate(points, 1):
                candidates = {
                    key: engine.calculate_scenario({**home, **point}, list(key))["net_saving_kwh"]
                    for key in indexed
                }
                best = max(candidates.values())
                best_plan = min(
                    (key for key, value in candidates.items() if best - value <= decision.TOLERANCE_KWH),
                    key=lambda key: (indexed[key]["cost_gbp"][1], key),
                )
                row = {
                    "case_id": case_id, "scenario_id": f"{split}-{scenario_number:02d}",
                    **point, "best_package": json.dumps(best_plan), "best_saving_kwh": best,
                }
                for name, plan in plans.items():
                    saving = candidates[tuple(plan)]
                    gap = max(0.0, best - saving)
                    row[f"{name}_package"] = json.dumps(plan)
                    row[f"{name}_saving_kwh"] = saving
                    row[f"{name}_regret_kwh"] = gap
                    if split == "verification":
                        observed_gaps[name].append(gap)
                rows.append(row)
        for name in plans:
            case["strategies"][name]["verification_max_regret_kwh"] = max(observed_gaps[name])
        cases.append(case)

    active = [case for case in cases if case["status"] == "available" and not case["no_action"]]
    summaries = {}
    for name in PROTOCOL["strategies"]:
        values = [c["strategies"][name]["verification_max_regret_kwh"] for c in active]
        summaries[name] = {
            "mean_case_verification_max_regret_kwh": statistics.mean(values) if values else None,
            "worst_case_verification_max_regret_kwh": max(values) if values else None,
        }
    comparisons = {}
    for baseline_name in ("greedy", "nominal"):
        better, tied, worse = [], [], []
        nominal_sacrifices = []
        for case in active:
            robust, other = case["strategies"]["robust"], case["strategies"][baseline_name]
            delta = robust["verification_max_regret_kwh"] - other["verification_max_regret_kwh"]
            bucket = tied if abs(delta) <= decision.TOLERANCE_KWH else (better if delta < 0 else worse)
            bucket.append(case["case_id"])
            if robust["nominal_saving_kwh"] < other["nominal_saving_kwh"] - decision.TOLERANCE_KWH:
                nominal_sacrifices.append(case["case_id"])
        comparisons[f"robust_vs_{baseline_name}"] = {
            "better_count": len(better), "tied_count": len(tied), "worse_count": len(worse),
            "better_case_ids": better, "tied_case_ids": tied, "worse_case_ids": worse,
            "lower_nominal_savings_case_ids": nominal_sacrifices,
        }
    metrics = {
        "status": "completed", "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": PROTOCOL,
        "protocol_sha256": hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True).encode()).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("greenhome/decision.py", "greenhome/engine.py", "scripts/evaluate_decision.py")
        },
        "case_count": len(cases), "decision_active_cases": len(active),
        "unavailable_cases": sum(case["status"] != "available" for case in cases),
        "no_action_cases": sum(case.get("no_action", False) for case in cases),
        "stable_active_cases": sum(case["stable"] is True for case in active),
        "development_rows": len(dev_rows), "verification_rows": len(verification_rows),
        "feasibility_or_budget_violations": violations,
        "verification_summary": summaries, "paired_comparisons": comparisons,
        "runtime_seconds": {
            "first_decision_call": timings[0], "max_decision_call": max(timings),
            "median_decision_call": statistics.median(timings),
            "total_evaluation": time.perf_counter() - started,
        },
        "limitations": [
            "All cases and scenario responses are fictional deterministic calculator outputs.",
            "No ML test set, market outcomes, measured retrofit savings, or probability distributions are used.",
            "The six archetypes repeated over four budgets are not 24 independent sampled households.",
            "Development-grid minimax dominance is an optimisation identity, not external validation.",
            "Every off-grid case and nominal-energy sacrifice is reported; no tuning follows this verification.",
        ],
    }
    output = ROOT / "reports"
    output.mkdir(exist_ok=True)
    (output / "decision_metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    (output / "decision_cases.json").write_text(json.dumps(cases, indent=2, allow_nan=False) + "\n")
    _write_csv(output / "decision_development_grid.csv", dev_rows)
    _write_csv(output / "decision_off_grid.csv", verification_rows)
    return metrics


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps({
        "status": result["status"], "cases": result["case_count"],
        "violations": len(result["feasibility_or_budget_violations"]),
        "verification_summary": result["verification_summary"],
        "comparisons": result["paired_comparisons"],
        "runtime_seconds": result["runtime_seconds"],
    }, indent=2))
