#!/usr/bin/env python3
"""Offline chronological memory experiment through the REAL standalone router.

No main API, frontend, provider, real customer, model training or model artifact.
Two private TestClients share temporary file SQLite. All state changes happen
through workspace HTTP endpoints. Three arms use the same real ranker/controller:
persisted prefix, forgotten history (intake only), and explicit current facts.
This is a designed state-retention experiment, not observed customer benefit.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.cookies import SimpleCookie
import importlib.abc
import json
import math
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = "/api/workspace"
VERSION = "chronological-memory-v1"
START = int(datetime(2026, 10, 10, 12, tzinfo=timezone.utc).timestamp())
REPORT = ROOT / "reports/memory_evaluation.json"
MEASURES = ("loft_insulation", "double_glazing", "smart_controls", "heat_pump", "solar_pv")
UPPER_COST = dict(zip(MEASURES, (1600, 10000, 350, 15000, 7000)))
COMPLETION_FEATURE = {
    "loft_insulation": ("insulation", "good"), "double_glazing": ("glazing", "double"),
    "smart_controls": ("smart_controls", True), "heat_pump": ("heating", "heat_pump"),
    "solar_pv": ("solar_kwp", 3.0),
}
PHASES = ("cold_start", "metadata_only", "deferred", "budget_changed", "future_rejected",
          "completed", "unconfirmed_restore_rejected", "baseline_refreshed")
STRATEGIES = ("with_memory", "without_memory", "reentered_current_facts")
# Set before the first candidate run. No candidate outputs enter the frozen plan.
PLAN_SHA256 = "9d3554f14d4989c2d4863050844e2f55df23aeb8e488c26218efb40a32227ae1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")


def intake_home(slot, i):
    """Written fictional intake, NOT engine.demo_homes or NEED-derived labels."""
    return {
        "property_id": f"DEMO-0{slot}", "property_type": (
            "Detached", "Semi detached", "Mid terrace", "End terrace",
            "Bungalow", "Flat", "Mid terrace", "Detached")[i],
        "age_band": 1 + i % 4, "region": "W92000004" if i == 6 else f"E1200000{i % 9 + 1}",
        "floor_area_m2": 70.0 + 12 * i, "epc_rating": "D" if i % 2 else "E",
        "electricity_kwh": 3600.0 + 200 * i, "gas_kwh": 10000.0 + 500 * i,
        "heating": "gas_boiler", "insulation": "poor", "glazing": "single",
        "solar_kwp": 0.0, "smart_controls": False, "roof_access": True,
        "listed_building": i == 6, "consent_confirmed": i == 6, "heat_pump_ready": True,
        "space_heat_fraction": 0.8, "boiler_efficiency": 0.85, "heat_pump_spf": 3.0,
        "solar_yield_kwh_per_kwp": 900.0, "solar_self_consumption_fraction": 0.45,
        "current_value_gbp": 250000.0 + 20000 * i, "budget_gbp": None,
        "data_kind": "synthetic_demo", "excluded_retrofits": [],
    }


def frozen_episodes():
    """Eight customers, one episode/property each; split BEFORE event expansion."""
    settings = [
        ("loft_insulation", ["solar_pv"], 1950.0, {}),
        ("smart_controls", ["heat_pump"], 350.0, {}),
        ("double_glazing", ["loft_insulation"], 10000.0, {}),
        ("solar_pv", ["heat_pump"], 7000.0, {}),
        ("loft_insulation", ["solar_pv"], 1950.0,
         {"heating": "electric_resistance", "gas_kwh": 0.0, "electricity_kwh": 16000.0}),
        ("smart_controls", ["double_glazing"], 350.0,
         {"heating": "heat_pump", "gas_kwh": 0.0, "electricity_kwh": 7200.0}),
        ("double_glazing", ["solar_pv"], 10000.0, {}),
        ("heat_pump", ["double_glazing"], 15000.0, {}),
    ]
    episodes = []
    for i, (completion, deferred, budget, overrides) in enumerate(settings):
        slot, split = i % 4 + 1, "dev" if i < 4 else "test"
        customer = f"MEM-{split.upper()}-C{slot:02}"
        home = {**intake_home(slot, i), **overrides}
        # Fictional replacement meter inputs are explicit numbers, not calculator
        # targets. Their changes must not be presented as measured energy saving.
        replacement = {"electricity_kwh": 6000.0 if completion == "heat_pump" else home["electricity_kwh"] + 100,
                       "gas_kwh": 2400.0 if completion == "heat_pump" else home["gas_kwh"]}
        start = START + 1000 * (i + 1)
        steps = [
            {"id": "intake", "at": start, "kind": "intake", "home": home},
            {"id": "cold_start", "at": start + 10, "kind": "query"},
            {"id": "metadata_write", "at": start + 20, "kind": "metadata"},
            {"id": "metadata_only", "at": start + 30, "kind": "query"},
            {"id": "defer_write", "at": start + 40, "kind": "defer", "deferred": deferred},
            {"id": "deferred", "at": start + 50, "kind": "query"},
            {"id": "budget_write", "at": start + 60, "kind": "budget", "budget_gbp": budget},
            {"id": "budget_changed", "at": start + 70, "kind": "query"},
            {"id": "select_for_completion", "at": start + 80, "kind": "select", "retrofit_id": completion},
            {"id": "future_attempt", "at": start + 90, "kind": "future_attempt",
             "retrofit_id": completion, "completed_on": "2026-10-11"},
            {"id": "future_rejected", "at": start + 100, "kind": "query"},
            # Occurrence is yesterday, but the fact is unavailable until recorded.
            {"id": "complete_write", "at": start + 110, "kind": "complete",
             "retrofit_id": completion, "completed_on": "2026-10-09"},
            {"id": "completed", "at": start + 120, "kind": "query"},
            {"id": "unconfirmed_restore", "at": start + 130, "kind": "unconfirmed_restore",
             "fuels": replacement},
            {"id": "unconfirmed_restore_rejected", "at": start + 140, "kind": "query"},
            {"id": "confirmed_restore", "at": start + 150, "kind": "restore", "fuels": replacement},
            {"id": "baseline_refreshed", "at": start + 160, "kind": "query"},
        ]
        episodes.append({
            "episode_id": f"{customer}-E01", "customer_id": customer,
            "property_group_id": f"{customer}-PROPERTY01", "workspace_group": split,
            "slot": slot, "split": split, "home": home, "steps": steps,
        })
    return episodes


def validate_plan(episodes):
    for key in ("customer_id", "property_group_id", "episode_id"):
        if len({e[key] for e in episodes}) != len(episodes):
            raise ValueError(f"Duplicate/cross-split {key}")
    all_ids = []
    for e in episodes:
        times = [s["at"] for s in e["steps"]]
        if times != sorted(set(times)):
            raise ValueError("Events/queries must have strictly increasing times.")
        phases = tuple(s["id"] for s in e["steps"] if s["kind"] == "query")
        if phases != PHASES:
            raise ValueError("The frozen query phases changed.")
        all_ids.extend(f"{e['episode_id']}/{s['id']}" for s in e["steps"])
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Duplicate episode step ID")


def prefix_truth(episode, query_at):
    """Independent authored-history projection: knowledge time, NOT event date.

    Only this customer's immutable episode is an input. Rejected future/stale
    baseline attempts have no effect. The reference is never made by a store or
    candidate call. Do not apply a later event merely because it is backdated.
    """
    home, events, completed = None, [], []
    status = "current"
    for step in episode["steps"]:
        if step["at"] >= query_at:
            continue
        kind = step["kind"]
        if kind == "intake":
            home = deepcopy(step["home"])
        elif kind == "defer":
            home["excluded_retrofits"] = list(step["deferred"])
        elif kind == "budget":
            home["budget_gbp"] = step["budget_gbp"]
        elif kind == "complete":
            rid = step["retrofit_id"]
            key, value = COMPLETION_FEATURE[rid]
            home[key] = value
            home["electricity_kwh"] = home["gas_kwh"] = None
            status = "needs_update"
            completed.append(rid)
            events.append({"kind": "completed", "retrofit_id": rid, "completed_on": step["completed_on"],
                           "created_at": iso(step["at"])})
        elif kind == "restore":
            home.update(step["fuels"])
            status = "current"
    if home is None:
        raise ValueError("No legitimate intake prefix")
    return {"home": home, "events": events, "completed": completed, "baseline_status": status}


class ForbiddenImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ("greenhome.api", "greenhome.explain", "dotenv") or fullname.startswith(("google.genai", "sklearn", "joblib")):
            raise RuntimeError(f"Disallowed experiment import: {fullname}")
        return None


@contextmanager
def offline_runtime(database_path, *, public=True):
    """Reject network connections rather than relying on a 'no network' label."""
    counters = {"network_attempts": 0, "ml_stub_calls": 0, "persistence_ranker_calls": 0}

    def no_network(*args, **kwargs):
        counters["network_attempts"] += 1
        raise RuntimeError("Network connections are forbidden in this experiment.")

    def no_ml(*args, **kwargs):
        counters["ml_stub_calls"] += 1
        return None

    fake = ModuleType("greenhome.ml")
    fake.predict_energy_benchmark = no_ml
    fake.predict_value_impact = no_ml
    finder = ForbiddenImport()
    overrides = {
        "GREENHOME_WORKSPACE_DATABASE_URL": f"sqlite:///{database_path}",
        "GREENHOME_WORKSPACE_MAX_WORKSPACES": "10", "GREENHOME_WORKSPACE_MAX_CREATIONS_PER_DAY": "10",
        "GREENHOME_PUBLIC_MODE": str(public).lower(), "GREENHOME_ALLOWED_ORIGINS": "",
        "GREENHOME_LIVE_GEMINI": "false", "GREENHOME_WARM_MODELS": "false",
        "GEMINI_API_KEY": "", "GEMINI_KEY": "", "GREENHOME_GATEWAY_TOKEN": "",
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, overrides))
        previous_ml = sys.modules.get("greenhome.ml")
        sys.modules["greenhome.ml"] = fake
        for target in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex"):
            stack.enter_context(patch(target, no_network))
        sys.meta_path.insert(0, finder)
        try:
            yield counters
        finally:
            sys.meta_path.remove(finder)
            if previous_ml is None:
                sys.modules.pop("greenhome.ml", None)
            else:
                sys.modules["greenhome.ml"] = previous_ml


def home_model():
    """Minimal strict standalone injection, NOT an import of production main API.

    The real router narrows the fictional IDs; real engine validation still
    validates all saved selections. Main HomeInput/proxy/UI integration is not
    claimed by this experiment.
    """
    from pydantic import BaseModel, ConfigDict, create_model
    from typing import Literal
    defaults = intake_home(1, 0)
    fields = {}
    for name, value in defaults.items():
        if name in ("budget_gbp", "current_value_gbp", "electricity_kwh", "gas_kwh",
                    "floor_area_m2", "solar_kwp"):
            kind = float | None
        elif name == "excluded_retrofits":
            kind = list[str]
        else:
            kind = type(value) | None if name in (
                "property_id", "property_type", "age_band", "region", "epc_rating", "heating", "insulation", "glazing",
                "smart_controls", "roof_access", "listed_building", "consent_confirmed", "heat_pump_ready") else type(value)
        fields[name] = (kind, ...)
    fields["data_kind"] = (Literal["synthetic_demo"], ...)
    class StrictHome(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    return create_model("MemoryEvaluationHome", __base__=StrictHome, **fields)


def build_app(clock, counters):
    from fastapi import FastAPI, Request
    from greenhome.workspace_api import create_workspace_router

    def no_persisted_ranking(homes):
        counters["persistence_ranker_calls"] += 1
        raise RuntimeError("Persistence may not call the injected ranker.")

    app = FastAPI()
    router = create_workspace_router(home_model(), no_persisted_ranking)
    router.workspace_store.clock = lambda: clock[0]
    app.include_router(router)

    def probe(request):
        # Never reflect the cookie value, even for disposable test credentials.
        return {"workspace_cookie_present": any("greenhome_workspace" in k for k in request.cookies)}

    # Avoid a postponed string annotation whose locally imported Request is not
    # in the module globals used by FastAPI's dependency inspection.
    probe.__annotations__["request"] = Request
    app.get("/_memory_cookie_probe")(probe)
    return app, router.workspace_store


def controller(home):
    from greenhome import engine
    from greenhome.ranking import rank_homes
    # The same deterministic controller is used in all three arms.
    row = rank_homes([deepcopy(home)])["rows"][0]
    screened = engine.screen_home(deepcopy(home))
    return {
        "selected": row["selected_retrofits"], "status": row["status"],
        "improvement_percent": row["improvement_percent"], "cost_gbp": row["cost_gbp"],
        "electricity_saving_kwh": row["electricity_saving_kwh"], "gas_saving_kwh": row["gas_saving_kwh"],
        "feasible": sorted(r["id"] for r in screened["recommendations"] if r["feasible"]),
    }


def evaluate_plan_output(output, truth):
    """Independent behavioural criteria, not candidate-generated success labels."""
    if "error" in output:
        return {
            "deferred": False if truth["home"]["excluded_retrofits"] else None,
            "budget": False if truth["home"]["budget_gbp"] is not None else None,
            "completed": False if truth["completed"] else None,
            "fuel_abstention": False if truth["baseline_status"] == "needs_update" else None,
            "evidence_status": False,
        }
    home = truth["home"]
    selected, feasible = set(output["selected"]), set(output["feasible"])
    offered = selected | feasible
    excluded = set(home["excluded_retrofits"])
    completed = set(truth["completed"])
    budget = home["budget_gbp"]
    if truth["baseline_status"] == "needs_update":
        abstained = (output["status"] == "insufficient_evidence" and not selected
                     and all(output[k] is None for k in
                             ("improvement_percent", "cost_gbp", "electricity_saving_kwh", "gas_saving_kwh")))
        evidence_ok = abstained
    else:
        abstained = None
        evidence_ok = (output["status"] in ("available", "no_affordable_option", "no_modelled_benefit")
                       and isinstance(output["improvement_percent"], (int, float))
                       and math.isfinite(output["improvement_percent"]))
    # Recommendation feasibility is individual, so only the chosen package cost
    # is summed. A null unassessable package is safe but must pass evidence checks.
    budget_ok = (not selected or
                 (all(r in UPPER_COST for r in selected) and sum(UPPER_COST[r] for r in selected) <= budget)) if budget is not None else None
    return {
        "deferred": not bool(offered & excluded) if excluded else None,
        "budget": budget_ok,
        "completed": not bool(offered & completed) if completed else None,
        "fuel_abstention": abstained, "evidence_status": evidence_ok,
    }


def extract_customer(workspace, customer_id):
    matching = [c for c in workspace.get("customers", []) if c["id"] == customer_id]
    if len(matching) != 1:
        raise RuntimeError("Expected one scoped customer.")
    return matching[0]


def update_payload(customer):
    return {k: deepcopy(customer[k]) for k in ("version", "home", "preferences", "selected_retrofits", "review_status")}


def source_hashes():
    names = ("scripts/evaluate_memory.py", "greenhome/workspace_store.py", "greenhome/workspace_api.py",
             "greenhome/engine.py", "greenhome/ranking.py", "greenhome/security.py",
             "docs/EVALUATION_PROTOCOL.md", "docs/MEMORY_EVALUATION.md")
    return {name: file_hash(ROOT / name) for name in names}


def protocol_record():
    raw = (ROOT / "docs/EVALUATION_PROTOCOL.md").read_bytes()
    original = json.loads((ROOT / "data/reference_cases_manifest.json").read_text())
    core_hash = hashlib.sha256(raw).hexdigest()
    if core_hash != original["protocol_sha256"]:
        raise ValueError("The original frozen reference protocol changed.")
    return {
        "original_frozen_protocol_sha256": core_hash, "original_frozen_protocol_unchanged": True,
        "memory_protocol_path": "docs/MEMORY_EVALUATION.md",
        "memory_protocol_sha256": file_hash(ROOT / "docs/MEMORY_EVALUATION.md"),
        "legacy_reference_full_file_hash_matches": True,
        "parent_action": "Original protocol fully restored; no reference-verifier, manifest or label changes needed. Rerun evaluations after candidate modules change.",
    }


def summarize_queries(queries):
    summary = {}
    for split in ("dev", "test", "all"):
        records = [q for q in queries if split == "all" or q["split"] == split]
        summary[split] = {}
        for arm in STRATEGIES:
            result = {"queries": len(records), "episodes": len({q["episode_id"] for q in records})}
            for metric in ("deferred", "budget", "completed", "fuel_abstention", "evidence_status"):
                values = [q["arms"][arm]["criteria"][metric] for q in records
                          if q["arms"][arm]["criteria"][metric] is not None]
                result[metric] = {"eligible_queries": len(values), "satisfied": sum(values),
                                  "violations": len(values) - sum(values),
                                  "rate": sum(values) / len(values) if values else None}
            result["all_applicable_constraints_satisfied"] = sum(
                all(v is not False for v in q["arms"][arm]["criteria"].values()) for q in records)
            result["input_matches_legitimate_prefix"] = sum(q["arms"][arm]["input_matches_prefix"] for q in records)
            summary[split][arm] = result
    paired = {}
    for metric in ("deferred", "budget", "completed", "fuel_abstention", "evidence_status"):
        eligible = [q for q in queries if q["arms"]["with_memory"]["criteria"][metric] is not None]
        outcomes = Counter()
        for q in eligible:
            with_ok = q["arms"]["with_memory"]["criteria"][metric]
            without_ok = q["arms"]["without_memory"]["criteria"][metric]
            outcomes["memory_only_satisfied" if with_ok and not without_ok else
                     "without_memory_only_satisfied" if without_ok and not with_ok else
                     "both_satisfied" if with_ok else "both_violated"] += 1
        paired[metric] = {"eligible_queries": len(eligible), **dict(outcomes)}
    return {"by_split": summary, "paired_query_outcomes": paired}


def run_experiment(*, controller_fn=None):
    episodes = frozen_episodes()
    validate_plan(episodes)
    if digest(episodes) != PLAN_SHA256:
        raise ValueError("Frozen episode specification hash changed; no silent retargeting.")
    protocol = protocol_record()
    before = source_hashes()
    controller_fn = controller if controller_fn is None else controller_fn
    queries, operations, checks, exceptions = [], [], [], []

    def check(name, passed, *, episode=None, **detail):
        checks.append({"name": name, "passed": bool(passed),
                       **({"episode_id": episode} if episode else {}), **detail})

    with tempfile.TemporaryDirectory(prefix="greenhome-memory-evaluation-") as tmp:
        database_path = Path(tmp) / "workspace" / "memory.sqlite3"
        with offline_runtime(database_path, public=True) as counters:
            from fastapi.testclient import TestClient
            from greenhome.workspace_api import PUBLIC_COOKIE_NAME
            from greenhome.workspace_store import WorkspaceStore
            clock = [START]
            app, store = build_app(clock, counters)
            with ExitStack() as clients_context:
                clients_context.callback(store.close)
                clients = {split: clients_context.enter_context(TestClient(app, base_url="https://testserver"))
                           for split in ("dev", "test")}
                workspaces = {}

                def request(client, method, path, *, body=None, expected=200, episode=None, action=None):
                    response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
                    operations.append({"episode_id": episode, "action": action or method,
                                       "method": method.upper(), "endpoint": (
                                           BASE + "/customers/{customer_id}/events" if path.endswith("/events") else
                                           BASE + "/customers/{customer_id}" if "/customers/" in path else path),
                                       "at": iso(clock[0]), "expected_status": expected,
                                       "actual_status": response.status_code})
                    check("http_status", response.status_code == expected, episode=episode,
                          action=action, expected=expected, actual=response.status_code)
                    return response

                try:
                    for split, client in clients.items():
                        request(client, "get", BASE, expected=401, action="before_opt_in")
                        if not workspaces:
                            check("no_storage_before_first_consent", not database_path.exists(), scope=split)
                        response = request(client, "post", BASE, body={"consent": True}, action="opt_in")
                        if response.status_code != 200:
                            raise RuntimeError("Workspace creation failed; evaluation incomplete.")
                        workspaces[split] = response.json()
                        cookie = SimpleCookie()
                        cookie.load(response.headers.get("set-cookie", ""))
                        morsel = cookie.get(PUBLIC_COOKIE_NAME)
                        flags = ({"httponly": bool(morsel["httponly"]), "secure": bool(morsel["secure"]),
                                  "same_site": morsel["samesite"], "path": morsel["path"],
                                  "host_only": not bool(morsel["domain"])} if morsel else {})
                        check("public_cookie_attributes", flags == {"httponly": True, "secure": True,
                              "same_site": "strict", "path": "/", "host_only": True}, scope=split, attributes=flags)
                        check("no_cache_workspace", response.headers.get("cache-control") == "no-store", scope=split)
                        # TestClient's real cookie jar scopes host and Secure; no
                        # browser JavaScript/SameSite enforcement claim is made.
                        different_host = request(client, "get", "https://other.invalid" + BASE,
                                                 expected=401, action="foreign_host_cookie_scope")
                        check("foreign_host_no_workspace", "customers" not in different_host.json(), scope=split)
                        request(client, "get", "http://testserver" + BASE, expected=403, action="public_http_denied")
                        http_probe = request(client, "get", "http://testserver/_memory_cookie_probe",
                                             action="secure_cookie_http_probe").json()
                        check("secure_cookie_not_sent_over_http", http_probe["workspace_cookie_present"] is False, scope=split)
                        ids = {c["id"] for c in workspaces[split]["customers"]}
                        check("four_seeded_customers", len(ids) == 4, scope=split)
                    a, b = workspaces["dev"], workspaces["test"]
                    check("distinct_private_workspace_and_customer_ids", a["id"] != b["id"]
                          and not ({c["id"] for c in a["customers"]} & {c["id"] for c in b["customers"]}))

                    for episode in episodes:
                        eid, split = episode["episode_id"], episode["split"]
                        owner, other = clients[split], clients["test" if split == "dev" else "dev"]
                        current = workspaces[split]["customers"][episode["slot"] - 1]
                        cid = current["id"]
                        path = f"{BASE}/customers/{cid}"
                        for step in episode["steps"]:
                            clock[0] = step["at"]
                            kind = step["kind"]
                            if kind == "query":
                                response = request(owner, "get", path, episode=eid, action=step["id"])
                                if response.status_code != 200:
                                    raise RuntimeError("A query could not read its persisted prefix.")
                                snapshot = response.json()
                                current = extract_customer(snapshot, cid)
                                truth = prefix_truth(episode, step["at"])
                                actual_events = [{k: e[k] for k in ("kind", "retrofit_id", "completed_on", "created_at")}
                                                 for e in current["events"]]
                                check("exact_recorded_event_prefix", actual_events == truth["events"], episode=eid,
                                      query=step["id"], expected_events=len(truth["events"]), actual_events=len(actual_events))
                                check("no_future_event_leakage", all(e["created_at"] < iso(step["at"]) for e in actual_events),
                                      episode=eid, query=step["id"])
                                check("persisted_home_matches_prefix", current["home"] == truth["home"], episode=eid, query=step["id"])
                                check("completion_baseline_status", current["baseline_status"] == truth["baseline_status"],
                                      episode=eid, query=step["id"])
                                inputs = {"with_memory": current["home"], "without_memory": episode["home"],
                                          "reentered_current_facts": truth["home"]}
                                arms = {}
                                for arm, home in inputs.items():
                                    try:
                                        output = controller_fn(deepcopy(home))
                                    except Exception as exc:
                                        output = {"error": type(exc).__name__}
                                    arms[arm] = {
                                        "input_home": deepcopy(home), "input_sha256": digest(home), "output": output,
                                        "input_matches_prefix": home == truth["home"],
                                        "criteria": evaluate_plan_output(output, truth),
                                    }
                                record = {"episode_id": eid, "customer_id": episode["customer_id"],
                                          "property_group_id": episode["property_group_id"], "split": split,
                                          "query_id": f"{eid}/{step['id']}", "phase": step["id"], "query_at": iso(step["at"]),
                                          "legitimate_recorded_events": truth["events"],
                                          "required_completed": truth["completed"],
                                          "required_baseline_status": truth["baseline_status"], "arms": arms}
                                queries.append(record)
                                check("current_facts_control_same_output", arms["with_memory"]["output"] == arms["reentered_current_facts"]["output"],
                                      episode=eid, query=step["id"])
                                if step["id"] in ("cold_start", "metadata_only"):
                                    check("negative_control_no_memory_advantage", arms["with_memory"]["output"] == arms["without_memory"]["output"],
                                          episode=eid, query=step["id"])
                                if step["id"] == "metadata_only":
                                    first = next(q for q in queries if q["episode_id"] == eid and q["phase"] == "cold_start")
                                    check("metadata_only_does_not_change_plan",
                                          arms["with_memory"]["output"] == first["arms"]["with_memory"]["output"], episode=eid)
                                continue

                            previous = request(owner, "get", BASE, episode=eid, action=f"{step['id']}_read").json()
                            current = extract_customer(previous, cid)
                            body = update_payload(current)
                            endpoint, expected = path, 200
                            if kind == "intake":
                                body["home"] = deepcopy(step["home"])
                                body["preferences"] = {"budget_gbp": None, "deferred_retrofits": [],
                                                       "priority": "energy", "disruption": "flexible"}
                                body["selected_retrofits"] = []
                            elif kind == "metadata":
                                body["review_status"] = "reviewing"
                            elif kind == "defer":
                                body["preferences"]["deferred_retrofits"] = step["deferred"]
                            elif kind == "budget":
                                body["preferences"]["budget_gbp"] = step["budget_gbp"]
                            elif kind == "select":
                                body["selected_retrofits"] = [step["retrofit_id"]]
                            elif kind in ("complete", "future_attempt"):
                                endpoint += "/events"
                                body = {"version": current["version"], "kind": "completed",
                                        "retrofit_id": step["retrofit_id"], "completed_on": step["completed_on"], "confirmed": True}
                                if kind == "future_attempt":
                                    expected = 422
                            elif kind in ("restore", "unconfirmed_restore"):
                                body["home"].update(step["fuels"])
                                body["baseline_confirmed_after_completion"] = kind == "restore"
                                if kind == "unconfirmed_restore":
                                    expected = 422
                            response = request(owner, "post", endpoint, body=body, expected=expected, episode=eid, action=step["id"])
                            after = request(owner, "get", BASE, episode=eid, action=f"{step['id']}_readback").json()
                            current = extract_customer(after, cid)
                            siblings_before = [c for c in previous["customers"] if c["id"] != cid]
                            siblings_after = [c for c in after["customers"] if c["id"] != cid]
                            check("no_sibling_customer_mutation", siblings_before == siblings_after, episode=eid, action=step["id"])
                            if expected != 200:
                                check("rejected_operation_has_no_state_effect", after == previous, episode=eid, action=step["id"])
                            else:
                                old = extract_customer(previous, cid)
                                check("successful_write_increments_version", current["version"] == old["version"] + 1,
                                      episode=eid, action=step["id"])
                            if kind == "complete":
                                check("completion_removed_saved_selection", step["retrofit_id"] not in current["selected_retrofits"],
                                      episode=eid)

                        # Actual two-client read, update and completion attacks,
                        # not fabricated denied labels. Never send foreign cookies.
                        before_owner = request(owner, "get", BASE, episode=eid, action="isolation_owner_before").json()
                        before_other = request(other, "get", BASE, episode=eid, action="isolation_other_before").json()
                        foreign = request(other, "get", path, expected=404, episode=eid, action="foreign_customer_read")
                        check("foreign_read_contains_no_customer_state", "customers" not in foreign.json(), episode=eid)
                        forged_update = update_payload(current)
                        forged_update["review_status"] = "deferred"
                        request(other, "post", path, body=forged_update, expected=404, episode=eid, action="foreign_customer_update")
                        event = {"version": current["version"], "kind": "completed", "retrofit_id": "smart_controls",
                                 "completed_on": "2026-10-09", "confirmed": True}
                        request(other, "post", path + "/events", body=event, expected=404,
                                episode=eid, action="foreign_customer_completion")
                        check("foreign_attempts_leave_both_workspaces_unchanged",
                              request(owner, "get", BASE, episode=eid, action="isolation_owner_after").json() == before_owner
                              and request(other, "get", BASE, episode=eid, action="isolation_other_after").json() == before_other,
                              episode=eid)
                        # A separately constructed store reads the committed file.
                        reopened = WorkspaceStore(f"sqlite:///{database_path}", clock=lambda: clock[0])
                        try:
                            restored = reopened.get(owner.cookies.get(PUBLIC_COOKIE_NAME))
                            check("independent_store_restores_committed_state", restored == before_owner, episode=eid)
                        finally:
                            reopened.close()

                    with sqlite3.connect(database_path) as db:
                        database_counts = {"workspaces": db.execute("SELECT count(*) FROM workspaces").fetchone()[0],
                                           "customers": db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0]}
                        stored_hashes = {r[0] for r in db.execute("SELECT token_hash FROM workspaces")}
                        dump = "\n".join(db.iterdump())
                    tokens = [client.cookies.get(PUBLIC_COOKIE_NAME) for client in clients.values()]
                    check("only_token_hashes_persisted", stored_hashes == {hashlib.sha256(t.encode()).hexdigest() for t in tokens}
                          and all(t not in dump for t in tokens))
                except Exception as exc:
                    # Do not serialize exceptions containing payloads, tokens or URLs.
                    exceptions.append({"type": type(exc).__name__, "stage": "standalone_episode_execution"})
                    database_counts = None
                runtime_counts = dict(counters)
            # Clients/stores close before TemporaryDirectory removes SQLite/WAL.
    after = source_hashes()
    failed_checks = [c for c in checks if not c["passed"]]
    memory_violations = sum(any(v is False for v in q["arms"]["with_memory"]["criteria"].values()) for q in queries)
    complete = len(queries) == len(episodes) * len(PHASES) and not exceptions
    status = ("incomplete" if not complete else "source_changed_rerun_required" if before != after else
              "completed_with_failures" if failed_checks or memory_violations or runtime_counts["network_attempts"] else "completed")
    result = {
        "version": VERSION, "status": status, "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_kind": "fictional_chronological_state_retention_experiment_NOT_real_customer_effect",
        "frozen_plan_sha256": PLAN_SHA256, "frozen_episodes": episodes, "protocol": protocol,
        "design": {
            "splits": {"train": 0, "dev": 4, "test": 4}, "customers": 8, "episodes": 8,
            "properties": 8, "private_workspaces": 2, "queries_per_episode": 8,
            "query_prompt_semantics": "Review my current plan; no historical facts re-entered in the two primary arms.",
            "with_memory": "Actual GET of correct private customer, using persisted projected home.",
            "without_memory": "Same controller with the original intake only; prior facts intentionally unavailable.",
            "reentered_current_facts": "Same controller, manually re-entered legitimate current facts from an independent chronological reducer.",
            "split_caveat": "Disjoint fictional customer/episode/property keys, not unseen archetype or empirical statistical holdout. No fitting or test-based tuning.",
        },
        "counts": {"executed_queries": len(queries), "executed_episodes": len({q["episode_id"] for q in queries}),
                   "controller_outputs": sum(len(q["arms"]) for q in queries), "http_requests": len(operations),
                   "http_status_counts": dict(Counter(str(op["actual_status"]) for op in operations)),
                   "database_rows_before_cleanup": database_counts, "operational_checks": len(checks),
                   "failed_operational_checks": len(failed_checks), "memory_queries_with_violations": memory_violations},
        "metrics": summarize_queries(queries), "queries": queries, "operations": operations,
        "operational_check_summary": {
            name: {"n": len(g := [c for c in checks if c["name"] == name]), "passed": sum(c["passed"] for c in g)}
            for name in sorted({c["name"] for c in checks})},
        "failed_checks": failed_checks, "exceptions": exceptions, "runtime_guards": runtime_counts,
        "source_hashes_before": before, "source_hashes_after": after,
        "limitations": [
            "Memory advantage here means retaining facts absent from the forgetful baseline, not a better learned algorithm or user benefit.",
            "The re-entered-facts arm controls for input freshness; no-memory with all current facts need not underperform memory.",
            "64 within-episode queries are correlated; only eight designed fictional customers, no significance/causal/population claim.",
            "Occurrence dates may predate recording; only records committed before each query are available. No historical-as-of store API is claimed.",
            "Actual standalone workspace router + SQLite exercised; main API HomeInput/proxy/UI, live browser, PostgreSQL and multi-process load are not tested.",
            "HttpOnly/SameSite/Secure attributes and TestClient cookie host/transport scoping checked, not browser JavaScript or SameSite enforcement.",
            "Both clients access all four customers in their own private workspace by design; isolation is between private workspaces, not roles within one.",
            "ML functions stubbed, network connections forbidden, no providers/artifacts/real home data. Temporary database and bearer cookies discarded.",
            "Authored replacement fuel inputs are fictional, not observed or engine-generated savings labels.",
        ],
    }
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = run_experiment()
    REPORT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "metrics": result["metrics"]["by_split"]["all"], "report": str(REPORT)}, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
