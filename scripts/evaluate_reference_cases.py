#!/usr/bin/env python3
"""Independent rational reference checks. NOT empirical retrofit validation.

The reference half uses only the standard library and never imports greenhome.
Candidate imports occur only inside evaluate_candidate(), AFTER frozen targets
are read and hash checked. The documented physical assumptions are shared, not
independently validated; arithmetic, constraint and ranking implementations are
separate. No provider, training, or model artefact writes occur.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from fractions import Fraction as F
from functools import lru_cache
import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path
import platform
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VERSION = "rational-reference-v1"
SEED = "225-independent-reference-20261010-v1"
IDS = ("loft_insulation", "double_glazing", "smart_controls", "heat_pump", "solar_pv")
# These costs/demand reductions are disclosed prototype assumptions, NOT quotes
# or effect sizes inferred from NEED. See EVALUATION_PROTOCOL and source register.
COST = dict(zip(IDS, ((800, 1600), (4000, 10000), (150, 350), (9000, 15000), (4500, 7000))))
FIELDS = ("electricity_kwh", "gas_kwh", "electricity_saving_kwh", "gas_saving_kwh",
          "net_saving_kwh", "improvement_percent", "carbon_reduction_kgco2e")
FUELS = ("electricity_saving_kwh", "gas_saving_kwh")
DATA = ROOT / "data/reference_cases.json"
MANIFEST = ROOT / "data/reference_cases_manifest.json"
PROTOCOL = ROOT / "docs/EVALUATION_PROTOCOL.md"
ABS_TOL = 1e-8


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def q(value) -> F | None:
    return None if value is None else F(str(value))


def wire(value):
    """Exact rational strings; never serialize a reference through binary float."""
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire(v) for v in value]
    return value


def package_cost(selected):
    return [sum(COST[r][i] for r in selected) for i in (0, 1)]


def physical_state(home, rid):
    """Independent positive/negative/unknown labels, not candidate reason text."""
    if rid not in IDS:
        return "unknown_retrofit"
    if rid in home.get("excluded_retrofits", []):
        return "excluded"
    if home.get("solar_kwp") is None:
        return "unknown"
    existing = {"loft_insulation": home.get("insulation") == "good",
                "double_glazing": home.get("glazing") in ("double", "triple"),
                "smart_controls": home.get("smart_controls") is True,
                "heat_pump": home.get("heating") in ("heat_pump", "electric_resistance")}
    if rid == "solar_pv" and home["solar_kwp"] > 0:
        return "unsupported_existing_pv"
    if existing.get(rid):
        return "infeasible"
    if rid == "solar_pv" and home["solar_self_consumption_fraction"] == 0:
        return "no_modelled_benefit"
    if rid != "solar_pv":
        fuel = "gas_kwh" if home.get("heating") == "gas_boiler" else "electricity_kwh"
        if home["space_heat_fraction"] == 0:
            return "no_modelled_benefit"
        if (home.get("heating") in ("gas_boiler", "heat_pump", "electric_resistance")
                and home.get(fuel) == 0 and not (home["solar_kwp"] > 0 and fuel == "electricity_kwh")):
            return "no_modelled_benefit"
        if home["solar_kwp"] > 0 and (home.get("heating") != "gas_boiler" or rid == "heat_pump"):
            return "unsupported_existing_pv"
    if rid != "smart_controls" and home.get("listed_building") is not False and home.get("consent_confirmed") is not True:
        return "unknown"
    if rid in ("loft_insulation", "solar_pv") and home.get("roof_access") is not True:
        return "unknown" if home.get("roof_access") is None else "infeasible"
    if rid == "solar_pv":
        if home.get("electricity_kwh") is None:
            return "unknown"
    else:
        if home.get("heating") not in ("gas_boiler", "heat_pump", "electric_resistance"):
            return "unknown"
        if home.get("electricity_kwh") is None or home.get("gas_kwh") is None:
            return "unknown"
        field_states = {
            "loft_insulation": ("insulation", ("poor", "partial")),
            "double_glazing": ("glazing", ("single",)),
            "smart_controls": ("smart_controls", (False,)),
        }
        if rid in field_states:
            field, states = field_states[rid]
            if home.get(field) in (None, "unknown"):
                return "unknown"
            if home[field] not in states:
                return "infeasible"
        if rid == "heat_pump":
            if home.get("heating") != "gas_boiler" or home["gas_kwh"] <= 0:
                return "infeasible"
            if home.get("heat_pump_ready") is not True:
                return "unknown" if home.get("heat_pump_ready") is None else "infeasible"
    return "feasible"


def affordable(home, selected):
    return home.get("budget_gbp") is None or package_cost(selected)[1] <= home["budget_gbp"]


def known_saving(scenario):
    return sum((scenario[f] for f in FUELS if scenario[f] is not None), F(0))


@lru_cache(maxsize=128)
def _reference_options(encoded_home):
    home = json.loads(encoded_home)
    states = {r: physical_state(home, r) for r in IDS}
    options = {tuple(s): simulate(home, s) for s in subsets()
               if all(states[r] == "feasible" for r in s)}
    gains = {s: known_saving(v) for s, v in options.items()}
    relevant = {r: any(r in s and affordable(home, s) and gains[s] > 0
                       and gains[s] > gains[tuple(k for k in s if k != r)] for s in options)
                for r in IDS}
    unlimited = {r: any(r in s and gains[s] > 0 and gains[s] > gains[tuple(k for k in s if k != r)]
                       for s in options) for r in IDS}
    labels = {r: states[r] if states[r] != "feasible" else
              "feasible" if relevant[r] else "budget" if unlimited[r] else "no_modelled_benefit"
              for r in IDS}
    return options, labels, unlimited


def reference_options(home):
    return _reference_options(json.dumps(home, sort_keys=True))


def eligibility(home, rid):
    return reference_options(home)[1].get(rid, "unknown_retrofit")


def accepted(home, selected):
    if any(eligibility(home, r) != "feasible" for r in selected):
        return False
    if not affordable(home, selected):
        return False
    return not selected or known_saving(simulate(home, selected)) > 0


def simulate(home, selected):
    """End-use ledger in exact rationals; no engine helper/constant is consumed.

    Envelope measures remove fractions of the same space-heat service. A heat
    pump transfers only the remaining service to electricity, leaving other gas
    uses intact. New PV offsets post-measure imports, never exports. Annual PV
    coincidence, fixed SPF, and demand fractions are NOT a dynamic simulation.
    """
    if any(physical_state(home, r) != "feasible" for r in selected):
        raise ValueError("Reference physical gate rejects this request.")
    e, g = q(home.get("electricity_kwh")), q(home.get("gas_kwh"))
    f, eta, spf = (q(home[x]) for x in ("space_heat_fraction", "boiler_efficiency", "heat_pump_spf"))
    retained = F(1)
    reductions = {
        "loft_insulation": F(15, 100) if home.get("insulation") == "poor" else F(7, 100),
        "double_glazing": F(1, 10), "smart_controls": F(7, 100),
    }
    for measure in selected:
        if measure in reductions:
            retained *= 1 - reductions[measure]
    de = None if e is None else F(0)
    dg = None if g is None else F(0)
    if home.get("heating") == "gas_boiler" and g is not None:
        service_input = g * f
        if "heat_pump" in selected:
            dg = service_input
            de = None if e is None else -(service_input * eta * retained / spf)
        else:
            dg = service_input * (1 - retained)
    elif home.get("heating") in ("heat_pump", "electric_resistance") and e is not None:
        de = e * f * (1 - retained)
    if "solar_pv" in selected and e is not None:
        pv = F(3) * q(home["solar_yield_kwh_per_kwp"]) * q(home["solar_self_consumption_fraction"])
        de += min(e - de, pv)
    net = None if de is None or dg is None else de + dg
    base = None if e is None or g is None else e + g
    return {
        "electricity_kwh": None if e is None else e - de,
        "gas_kwh": None if g is None else g - dg,
        "electricity_saving_kwh": de, "gas_saving_kwh": dg,
        "net_saving_kwh": net,
        "improvement_percent": None if base in (None, 0) else net * 100 / base,
        # DESNZ 2026 operational factors: official workbook cells, not fit labels.
        "carbon_reduction_kgco2e": None if net is None else de * F("0.13096") + dg * F("0.18231"),
        "cost_gbp": package_cost(selected),
    }


def subsets():
    return [list(c) for n in range(6) for c in itertools.combinations(IDS, n)]


def optimum(home):
    """Full feasible enumeration; tied packages retained instead of forced ties."""
    options = [(s, simulate(home, s)) for s in subsets() if accepted(home, s)]
    known = [(s, v) for s, v in options if v["improvement_percent"] is not None]
    if not known:
        return None, []
    best = max(v["improvement_percent"] for _, v in known)
    return best, [s for s, v in known if v["improvement_percent"] == best]


def ranking_reference(home):
    base = None if any(home.get(k) is None for k in ("electricity_kwh", "gas_kwh")) else q(home["electricity_kwh"]) + q(home["gas_kwh"])
    if base in (None, 0):
        return {"status": "insufficient_evidence", "improvement_percent": None, "optimal_packages": []}
    # Unknown eligibility must not be promoted to assessed zero opportunity.
    if any(physical_state(home, r) == "unknown" and affordable(home, [r]) for r in IDS):
        return {"status": "insufficient_evidence", "improvement_percent": None, "optimal_packages": []}
    best, packages = optimum(home)
    unlimited = {**home, "budget_gbp": None}
    unconstrained, _ = optimum(unlimited)
    unsupported = any(physical_state(home, r) == "unsupported_existing_pv" and affordable(home, [r]) for r in IDS)
    if best <= 0 and unconstrained <= 0 and unsupported:
        return {"status": "unsupported", "improvement_percent": None, "optimal_packages": []}
    status = "available" if best > 0 else "no_affordable_option" if unconstrained > 0 else "no_modelled_benefit"
    return {"status": status, "improvement_percent": best, "optimal_packages": packages}


def base_home():
    return {
        "property_type": "Semi detached", "age_band": 2, "region": "E12000007",
        "floor_area_m2": 100, "epc_rating": "E", "electricity_kwh": 4800,
        "gas_kwh": 12000, "heating": "gas_boiler", "insulation": "poor",
        "glazing": "single", "smart_controls": False, "solar_kwp": 0,
        "roof_access": True, "listed_building": False, "consent_confirmed": False,
        "heat_pump_ready": True, "space_heat_fraction": 0.8, "boiler_efficiency": 0.85,
        "heat_pump_spf": 3, "solar_yield_kwh_per_kwp": 900,
        "solar_self_consumption_fraction": 0.45, "budget_gbp": None,
        "current_value_gbp": 350000, "data_kind": "synthetic_demo", "excluded_retrofits": [],
    }


def archetypes():
    """24 predeclared, deliberately non-representative boundary archetypes."""
    return [
        ("gas_poor_full", {}),
        ("partial_small", {"insulation": "partial", "floor_area_m2": 48, "epc_rating": "D"}),
        ("electric_resistance", {"heating": "electric_resistance", "gas_kwh": 0, "electricity_kwh": 16000}),
        ("existing_heat_pump", {"heating": "heat_pump", "gas_kwh": 0, "electricity_kwh": 7500}),
        ("flat_no_roof", {"property_type": "Flat", "roof_access": False, "heat_pump_ready": False}),
        ("listed_no_consent", {"listed_building": True}),
        ("listed_with_consent", {"listed_building": True, "consent_confirmed": True}),
        ("missing_fuel", {"gas_kwh": None}),
        ("unknown_evidence", {"heating": "unknown", "insulation": "unknown", "glazing": "unknown",
                              "smart_controls": None, "roof_access": None, "heat_pump_ready": None}),
        ("zero_baseline", {"electricity_kwh": 0, "gas_kwh": 0}),
        ("already_improved_existing_pv", {"insulation": "good", "glazing": "triple", "smart_controls": True,
                              "heating": "heat_pump", "gas_kwh": 0, "roof_access": False, "solar_kwp": 4}),
        ("existing_pv", {"solar_kwp": 4}),
        ("budget_zero", {"budget_gbp": 0}),
        ("budget_controls_exact", {"budget_gbp": 350}),
        ("budget_loft_exact", {"budget_gbp": 1600}),
        ("budget_package_exact", {"budget_gbp": 1950}),
        ("budget_package_below", {"budget_gbp": 1949.99}),
        ("zero_benefit", {"space_heat_fraction": 0, "solar_self_consumption_fraction": 0}),
        ("pv_cap", {"electricity_kwh": 200, "gas_kwh": 10000}),
        ("joint_only_low_spf", {"heat_pump_spf": 1, "boiler_efficiency": 1, "space_heat_fraction": 1,
                               "electricity_kwh": 0}),
        ("unknown_pv", {"solar_kwp": None}),
        ("deferred_measures", {"excluded_retrofits": ["heat_pump", "solar_pv", "double_glazing"]}),
        ("tie_controls_a", {"budget_gbp": 350, "electricity_kwh": 4000, "gas_kwh": 10000}),
        ("tie_controls_b", {"budget_gbp": 350, "electricity_kwh": 4000, "gas_kwh": 10000}),
    ]


def generate():
    customer_ids = [f"REF-C{i:03}" for i in range(1, 49)]
    ordered = sorted(customer_ids, key=lambda c: hashlib.sha256(f"{SEED}/{c}".encode()).hexdigest())
    split_customers = {"train": ordered[:24], "dev": ordered[24:36], "test": ordered[36:]}
    types = ("Detached", "Semi detached", "Mid terrace", "End terrace", "Bungalow", "Flat")
    result = []
    for split, customers in split_customers.items():
        for i in range(len(customers) * 2):
            name, change = archetypes()[i % 24]
            cid = customers[i // 2]
            pid = f"{cid}-P{i % 2 + 1}"
            home = {**base_home(), "property_id": pid, "property_type": types[i % 6],
                    "region": ("W92000004" if i % 10 == 9 else f"E1200000{i % 9 + 1}"),
                    "age_band": 1 + i % 4, "floor_area_m2": 40 + (i * 17) % 240,
                    "epc_rating": "ABCDEFG"[i % 7], **change}
            # Consumption variation is independent of outputs. Preserve deliberate
            # ties and zero/missing inputs; all decimal inputs have exact encoding.
            scale = F(90 + int(hashlib.sha256(cid.encode()).hexdigest()[:4], 16) % 21, 100)
            if not name.startswith("tie_"):
                for fuel in ("electricity_kwh", "gas_kwh"):
                    if home[fuel] is not None:
                        home[fuel] = float(q(home[fuel]) * scale)
            scenarios = []
            for j, selected in enumerate(subsets() + [["unknown_measure"]]):
                ok = accepted(home, selected)
                scenarios.append({"scenario_id": f"{pid}-S{j:02}", "selected": selected,
                                  "kind": "no_op" if not selected else "standalone" if len(selected) == 1 else "package",
                                  "accepted": ok, "reference": wire(simulate(home, selected)) if ok else None})
            result.append({
                "customer_id": cid, "property_id": pid, "split": split,
                "archetype": name, "home": home,
                "evidence_kind": "fictional_rule_reference_NOT_observed_savings",
                "method_id": VERSION,
                "uncertainty": "Exact conditional arithmetic; physical/model uncertainty unquantified; no empirical interval.",
                "feasibility": {r: eligibility(home, r) for r in IDS},
                "scenarios": scenarios, "ranking": wire(ranking_reference(home)),
            })
    for split in split_customers:
        available = sorted([r for r in result if r["split"] == split and r["ranking"]["improvement_percent"] is not None],
                           key=lambda r: (-q(r["ranking"]["improvement_percent"]), r["property_id"]))
        last, rank = None, None
        for pos, row in enumerate(available, 1):
            score = q(row["ranking"]["improvement_percent"])
            if score != last:
                rank = pos
            row["ranking"]["rank"] = rank
            last = score
        for row in result:
            row["ranking"].setdefault("rank", None)
    return result


def counts(rows):
    return {split: {
        "customers": len({r["customer_id"] for r in rows if r["split"] == split}),
        "properties": sum(r["split"] == split for r in rows),
        "scenarios": sum(len(r["scenarios"]) for r in rows if r["split"] == split),
        "accepted": sum(s["accepted"] for r in rows if r["split"] == split for s in r["scenarios"]),
        "feasibility_labels": dict(Counter(v for r in rows if r["split"] == split for v in r["feasibility"].values())),
        "ranking_statuses": dict(Counter(r["ranking"]["status"] for r in rows if r["split"] == split)),
    } for split in ("train", "dev", "test")}


def check_groups(rows):
    for key in ("customer_id", "property_id"):
        membership = defaultdict(set)
        for row in rows:
            membership[row[key]].add(row["split"])
        if any(len(s) != 1 for s in membership.values()):
            raise ValueError(f"Split leakage: {key}")
    if len({r["property_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate property")
    scenario_ids = [s["scenario_id"] for r in rows for s in r["scenarios"]]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("Duplicate scenario")


def freeze():
    if DATA.exists() or MANIFEST.exists():
        raise FileExistsError("Frozen references already exist; no overwrite or silent regeneration.")
    rows = generate()
    check_groups(rows)
    dump(DATA, {"version": VERSION, "seed": SEED, "cases": rows})
    dump(MANIFEST, {
        "version": VERSION, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED, "reference_sha256": sha(DATA), "generator_sha256_at_freeze": sha(Path(__file__)),
        "protocol_sha256": sha(PROTOCOL), "counts": counts(rows),
        "independence": "Separate Fraction ledger, not candidate-generated targets; shared documented assumptions, not independent physical evidence.",
        "split_policy": "48 fictional customers hash-ordered, 24/12/12 train/dev/test, two properties each; split before scenario expansion.",
        "test_policy": "Contract conformance suite, not a pristine empirical holdout after first inspection; never tune labels to candidate.",
        "source_register_sha256_at_freeze": sha(ROOT / "data/source_register.json"),
    })


def load_frozen():
    manifest = json.loads(MANIFEST.read_text())
    if sha(DATA) != manifest["reference_sha256"] or sha(PROTOCOL) != manifest["protocol_sha256"]:
        raise ValueError("Frozen reference/protocol hash mismatch; do not evaluate silently changed labels.")
    rows = json.loads(DATA.read_text())["cases"]
    check_groups(rows)
    if counts(rows) != manifest["counts"]:
        raise ValueError("Reference count mismatch")
    return rows, manifest


def compare_number(actual, reference):
    if reference is None:
        return actual is None
    return (isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and math.isfinite(actual) and abs(actual - float(q(reference))) <= ABS_TOL)


def sign(x):
    return 0 if abs(float(x)) <= ABS_TOL else 1 if x > 0 else -1


def error_summary(records):
    by_field = {}
    for field in FIELDS:
        relevant = [r for r in records if r["field"] == field]
        numeric = [r for r in relevant if r["reference"] is not None and r["numeric"]]
        errors = [r["prediction"] - float(q(r["reference"])) for r in numeric]
        by_field[field] = {
            "reference_numeric": sum(r["reference"] is not None for r in relevant),
            "compared": len(errors), "null_reference": sum(r["reference"] is None for r in relevant),
            "failed_checks": sum(not r["match"] for r in relevant),
            "mae": sum(abs(e) for e in errors) / len(errors) if errors else None,
            "bias": sum(errors) / len(errors) if errors else None,
            "max_abs_error": max(map(abs, errors), default=None),
        }
        if field in FUELS:
            by_field[field]["sign_checks"] = {
                label: {"n": len(group := [r for r in numeric if sign(q(r["reference"])) == val]),
                        "correct": sum(sign(r["prediction"]) == val for r in group)}
                for label, val in (("negative", -1), ("zero", 0), ("positive", 1))}
    return by_field


def baseline_predictions(home, selected, name):
    if name == "zero_savings":
        return {f: F(0) if home[f.replace("_saving", "")] is not None else None for f in FUELS}
    # Deliberately ignores package interactions; useful diagnostic, not physics.
    return {f: None if home[f.replace("_saving", "")] is None else
            sum((simulate(home, [r])[f] for r in selected), F(0)) for f in FUELS}


def pairwise_metrics(expected, predicted):
    """No dropping missing predictions: wrong/missing pair counts explicitly."""
    ids = [pid for pid, val in expected.items() if val is not None]
    groups = Counter()
    for a, b in itertools.combinations(ids, 2):
        true_order = (q(expected[a]) > q(expected[b])) - (q(expected[a]) < q(expected[b]))
        if any(not isinstance(predicted.get(k), (int, float)) or isinstance(predicted.get(k), bool)
               or not math.isfinite(predicted[k]) for k in (a, b)):
            groups["missing"] += 1
            continue
        # Ordering is full precision, unlike approximate numeric-field checks.
        # In particular, never hide float-split mathematical ties with ABS_TOL.
        actual_order = (predicted[a] > predicted[b]) - (predicted[a] < predicted[b])
        groups["ties" if true_order == 0 else "strict_pairs"] += 1
        groups["correct_ties" if true_order == 0 and actual_order == 0 else
               "correct_strict" if true_order != 0 and actual_order == true_order else "incorrect"] += 1
    total = math.comb(len(ids), 2)
    return {**dict(groups), "pairs": total,
            "accuracy_including_ties_and_missing": (groups["correct_ties"] + groups["correct_strict"]) / total if total else None}


def source_snapshot():
    paths = ["greenhome/engine.py", "greenhome/ranking.py", "greenhome/decision.py",
             "docs/FINAL_BUILD_CONTRACT.md", "docs/CALCULATIONS.md", "docs/PROPERTY_RANKING.md",
             "scripts/evaluate_reference_cases.py", "data/source_register.json"]
    return {name: sha(ROOT / name) if (ROOT / name).exists() else None for name in paths}


def evaluate_candidate(splits=("dev", "test")):
    rows, manifest = load_frozen()
    rows = [r for r in rows if r["split"] in splits]
    before = source_snapshot()
    sys.path.insert(0, str(ROOT))
    engine = importlib.import_module("greenhome.engine")
    try:
        ranker = importlib.import_module("greenhome.ranking").rank_homes
    except ModuleNotFoundError as exc:
        if exc.name != "greenhome.ranking":
            raise
        ranker = None
    details, values, failures, feasibility = [], [], [], []
    baseline_errors = defaultdict(list)
    summary = {"status": "completed", "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
               "python": platform.python_version(), "reference_sha256": manifest["reference_sha256"],
               "protocol_sha256": manifest["protocol_sha256"], "splits_evaluated": list(splits),
               "counts": counts(rows), "absolute_tolerance": ABS_TOL,
               "scope": "Synthetic contract conformance ONLY. No observed savings, customer study, value accuracy or memory benefit.",
               "ml_inference": "Energy and synthetic-value functions stubbed; not evaluated by this required-output suite.",
               "source_hashes_before": before}
    with ExitStack() as stack:
        for name in ("predict_energy_benchmark", "predict_value_impact"):
            stack.enter_context(patch(f"greenhome.ml.{name}", return_value=None))
        for case in rows:
            home, pid = case["home"], case["property_id"]
            initial = engine.assess(home, [])
            recs = {r["id"]: r["feasible"] for r in initial["recommendations"]}
            for rid, label in case["feasibility"].items():
                record = {"property_id": pid, "split": case["split"], "retrofit": rid,
                          "reference_state": label, "expected": label == "feasible", "actual": recs.get(rid)}
                record["match"] = record["actual"] is record["expected"]
                feasibility.append(record)
                if not record["match"]:
                    failures.append({"kind": "feasibility", **record})
            for scenario in case["scenarios"]:
                record = {"property_id": pid, "customer_id": case["customer_id"], "split": case["split"],
                          "archetype": case["archetype"], **scenario}
                try:
                    output = engine.assess(home, scenario["selected"])["scenario"]
                    record.update(candidate_accepted=True, candidate=output)
                except ValueError as exc:
                    output = None
                    record.update(candidate_accepted=False, candidate_error=str(exc))
                except Exception as exc:
                    output = None
                    record.update(candidate_accepted=False, candidate_error=f"{type(exc).__name__}: {exc}")
                    failures.append({"kind": "candidate_exception", "scenario_id": scenario["scenario_id"], "error": record["candidate_error"]})
                record["acceptance_match"] = record["candidate_accepted"] == scenario["accepted"]
                if not record["acceptance_match"]:
                    failures.append({"kind": "request_acceptance", "scenario_id": scenario["scenario_id"]})
                if scenario["accepted"]:
                    for field in FIELDS:
                        pred = output.get(field) if output else None
                        ref = scenario["reference"][field]
                        match = bool(output) and field in output and compare_number(pred, ref)
                        numeric = isinstance(pred, (int, float)) and not isinstance(pred, bool) and math.isfinite(pred)
                        values.append({"property_id": pid, "customer_id": case["customer_id"], "split": case["split"],
                                       "kind": scenario["kind"], "field": field, "prediction": pred, "reference": ref,
                                       "match": match, "numeric": numeric})
                        if not match:
                            failures.append({"kind": "numeric_or_null", "scenario_id": scenario["scenario_id"],
                                             "field": field, "reference": ref, "prediction": pred})
                    if output and output.get("cost_gbp") != scenario["reference"]["cost_gbp"]:
                        failures.append({"kind": "package_cost", "scenario_id": scenario["scenario_id"]})
                    for baseline in ("zero_savings", "sum_of_standalone"):
                        predicted = baseline_predictions(home, scenario["selected"], baseline)
                        for field in FUELS:
                            ref = q(scenario["reference"][field])
                            if ref is not None:
                                baseline_errors[(case["split"], baseline, scenario["kind"], field)].append(float(predicted[field] - ref))
                details.append(record)
        ranking_details, ranking_summary = [], {}
        for split in splits:
            group = [r for r in rows if r["split"] == split]
            refs = {r["property_id"]: r["ranking"]["improvement_percent"] for r in group}
            predictions = {}
            if ranker is not None:
                try:
                    ranking_output = ranker([r["home"] for r in reversed(group)])
                    candidate_rows = ranking_output["rows"]
                    by_id = {r["property_id"]: r for r in candidate_rows}
                    if len(by_id) != len(group) or len(candidate_rows) != len(group) or set(by_id) != set(refs):
                        failures.append({"kind": "ranking_membership", "split": split})
                    for case in group:
                        actual, ref = by_id.get(case["property_id"], {}), case["ranking"]
                        predictions[case["property_id"]] = actual.get("improvement_percent")
                        required = {"property_id", "rank", "status", "reason", "score", "classification", "flagged",
                                    "improvement_percent", "baseline_kwh", "selected_retrofits", *FUELS,
                                    "carbon_reduction_kgco2e", "cost_gbp", "budget_gbp"}
                        home = case["home"]
                        baseline = (None if home["electricity_kwh"] is None or home["gas_kwh"] is None else
                                    q(home["electricity_kwh"]) + q(home["gas_kwh"]))
                        checks = {
                            "schema_fields": required.issubset(actual),
                            "status": actual.get("status") == ref["status"],
                            "rank": actual.get("rank") == ref["rank"],
                            "potential": compare_number(actual.get("improvement_percent"), ref["improvement_percent"]),
                            "baseline": compare_number(actual.get("baseline_kwh"), wire(baseline)),
                            "budget": actual.get("budget_gbp") == home["budget_gbp"],
                        }
                        if ref["improvement_percent"] is not None:
                            selected = actual.get("selected_retrofits", [])
                            checks["optimal_feasible_package"] = any(set(selected) == set(s) for s in ref["optimal_packages"])
                            if accepted(case["home"], selected):
                                scenario = simulate(case["home"], selected)
                                for field in (*FUELS, "carbon_reduction_kgco2e"):
                                    checks[field] = compare_number(actual.get(field), wire(scenario[field]))
                                checks["cost"] = actual.get("cost_gbp") == scenario["cost_gbp"]
                        else:
                            checks["unavailable_numerics"] = all(actual.get(f) is None
                                                               for f in (*FUELS, "carbon_reduction_kgco2e", "cost_gbp"))
                        ranking_details.append({"split": split, "property_id": case["property_id"], "reference": ref,
                                                "candidate": actual, "checks": checks})
                        if not all(checks.values()):
                            failures.append({"kind": "home_ranking", "property_id": case["property_id"], "checks": checks})
                    expected_order = sorted(group, key=lambda c: (
                        refs[c["property_id"]] is None,
                        -q(refs[c["property_id"]]) if refs[c["property_id"]] is not None else F(0),
                        c["property_id"]))
                    # Contract prescribes ID order for numerical ties, not order of unknown rows.
                    numeric_order = [r["property_id"] for r in candidate_rows if refs.get(r["property_id"]) is not None]
                    if numeric_order != [r["property_id"] for r in expected_order if refs[r["property_id"]] is not None]:
                        failures.append({"kind": "ranking_order", "split": split})
                except Exception as exc:
                    failures.append({"kind": "ranking_exception", "split": split, "error": f"{type(exc).__name__}: {exc}"})
            split_result = {"candidate": pairwise_metrics(refs, predictions) if ranker else {"status": "pending_ranker"}}
            if ranker:
                checked = [r for r in ranking_details if r["split"] == split]
                split_result["candidate"]["row_checks"] = {
                    "n": len(checked), "status_correct": sum(r["checks"]["status"] for r in checked),
                    "rank_correct": sum(r["checks"]["rank"] for r in checked),
                    "fully_correct": sum(all(r["checks"].values()) for r in checked)}
            for baseline in ("no_action", "best_standalone"):
                predicted = {}
                regrets = []
                for case in group:
                    truth = q(refs[case["property_id"]])
                    if truth is None:
                        predicted[case["property_id"]] = None
                        continue
                    best = F(0) if baseline == "no_action" else max(
                        [F(0)] + [simulate(case["home"], [r])["improvement_percent"]
                                  for r in IDS if accepted(case["home"], [r])])
                    predicted[case["property_id"]] = float(best)
                    regrets.append(float(truth - best))
                split_result[baseline] = {
                    **pairwise_metrics(refs, predicted), "homes": len(regrets),
                    "mean_potential_regret_percentage_points": sum(regrets) / len(regrets) if regrets else None,
                    "max_potential_regret_percentage_points": max(regrets, default=None),
                }
            ranking_summary[split] = split_result
    summary.update(
        scenario_requests=len(details), acceptance_mismatches=sum(not r["acceptance_match"] for r in details),
        feasibility={"n": len(feasibility), "false_positives": sum(r["actual"] is True and not r["expected"] for r in feasibility),
                     "false_negatives": sum(r["actual"] is False and r["expected"] for r in feasibility),
                     "unknown_reference": sum(r["reference_state"] == "unknown" for r in feasibility),
                     "by_state": {state: {"n": len(g := [r for r in feasibility if r["reference_state"] == state]),
                                          "correct": sum(r["match"] for r in g)}
                                  for state in sorted({r["reference_state"] for r in feasibility})}},
        numeric_by_split_and_kind={
            split: {kind: error_summary([r for r in values if r["split"] == split and (kind == "all" or r["kind"] == kind)])
                    for kind in ("all", "no_op", "standalone", "package")} for split in splits},
        fuel_baselines=[{"split": key[0], "strategy": key[1], "kind": key[2], "field": key[3], "n": len(errors),
                         "mae": sum(map(abs, errors)) / len(errors), "bias": sum(errors) / len(errors)}
                        for key, errors in sorted(baseline_errors.items())],
        ranking=ranking_summary, failures=failures, failure_count=len(failures),
        source_hashes_after=source_snapshot(),
    )
    # Within-home scenarios correlate: descriptive customer/property macro errors,
    # not invented independent-row confidence intervals.
    summary["cluster_macro_fuel_mae"] = {}
    for grouping in ("property_id", "customer_id"):
        summary["cluster_macro_fuel_mae"][grouping] = {}
        for field in FUELS:
            groups = defaultdict(list)
            for r in values:
                if r["field"] == field and r["reference"] is not None and r["numeric"]:
                    groups[r[grouping]].append(abs(r["prediction"] - float(q(r["reference"]))))
            means = [sum(es) / len(es) for es in groups.values()]
            summary["cluster_macro_fuel_mae"][grouping][field] = {
                "groups": len(means), "mae": sum(means) / len(means) if means else None}
    if before != summary["source_hashes_after"]:
        summary["status"] = "source_changed_during_run_rerun_required"
    elif failures:
        summary["status"] = "completed_with_mismatches"
    elif ranker is None:
        summary["status"] = "ranking_pending_rerun_required"
    dump(ROOT / "reports/reference_metrics.json", summary)
    dump(ROOT / "reports/reference_predictions.json", {"scenarios": details, "feasibility": feasibility, "ranking": ranking_details})
    text = (
        "# Independent required-output reference evaluation\n\n"
        "**Synthetic arithmetic/contract conformance, NOT observed savings performance.**\n\n"
        f"- Status: `{summary['status']}`\n"
        f"- Evaluated: {len(rows)} fictional properties / {len({r['customer_id'] for r in rows})} customers; "
        f"{len(details)} requests, {sum(r['accepted'] for r in details)} accepted references.\n"
        f"- Feasibility labels: {len(feasibility)}; request-acceptance mismatches: {summary['acceptance_mismatches']}.\n"
        f"- Recorded failed checks: {len(failures)}. See JSON for every mismatch, denominator, split and baseline.\n\n"
        "No-op identities are reported separately. Missing predictions are not silently scored as zero. "
        "The independent Fraction ledger shares the disclosed assumptions, not candidate code. "
        "Neither exact agreement nor grouping supplies physical/causal/market validation or a memory study.\n\n"
        "Run `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_reference_cases.py --evaluate` "
        "after concurrent engine/ranking edits finish. Source hashes before/after bind each run; "
        "later edits require a rerun. Frozen labels/protocol must not be rewritten to make a candidate pass.\n"
    )
    for split in splits:
        m = summary["numeric_by_split_and_kind"][split]["all"]
        text += f"\n## {split}\n\n"
        for field in FUELS:
            mae = "unavailable" if m[field]["mae"] is None else f"{m[field]['mae']:.12g}"
            maximum = "unavailable" if m[field]["max_abs_error"] is None else f"{m[field]['max_abs_error']:.12g}"
            text += (f"- `{field}`: n={m[field]['compared']}, MAE={mae} kWh, "
                     f"max absolute error={maximum} kWh; "
                     f"failed numeric/null checks={m[field]['failed_checks']}.\n")
        text += f"- Cross-home ranking: `{json.dumps(ranking_summary[split]['candidate'], sort_keys=True)}`.\n"
    if failures:
        text += "\n## Checks needing attention (not suppressed)\n\n"
        for failure in failures:
            text += f"- `{json.dumps(failure, sort_keys=True)}`\n"
    (ROOT / "reports/reference_summary.md").write_text(text)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--evaluate", action="store_true")
    parser.add_argument("--split", choices=("dev", "test", "both"), default="both")
    args = parser.parse_args()
    if args.freeze:
        freeze()
        print(json.dumps(json.loads(MANIFEST.read_text())["counts"], indent=2))
    elif args.verify:
        rows, _ = load_frozen()
        if rows != generate():
            raise ValueError("Generator no longer reproduces frozen references.")
        print("Frozen hashes, customer/property separation, counts and exact regeneration verified.")
    else:
        summary = evaluate_candidate(("dev", "test") if args.split == "both" else (args.split,))
        print(json.dumps({k: summary[k] for k in ("status", "scenario_requests", "failure_count")}, indent=2))
        return 0 if summary["status"] == "completed" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
