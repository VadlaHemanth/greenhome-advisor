#!/usr/bin/env python3
"""Independent, frozen, offline customer -> property HTTP/store evaluation.

No trained estimator, NEED identity inference, old evaluator import or provider.
Only the explicit --freeze command creates references; --run cannot rewrite them.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = "/api/workspace"
CASES = ROOT / "data/ownership_cases.json"
MANIFEST = ROOT / "data/ownership_cases_manifest.json"
REPORT = ROOT / "reports/ownership_evaluation.json"
VERSION = "ownership-http-v1"
START = 1791633600  # 2026-10-10T12:00:00Z, an authored simulation clock.
UPPER = {"loft_insulation": 1600, "double_glazing": 10000,
         "smart_controls": 350, "heat_pump": 15000, "solar_pv": 7000}
SPLITS = ("train", "validation", "test")
ARMS = ("scoped_memory", "owner_blind_memory", "explicit_current_facts")
METRICS = ("exact_property_facts", "exclusions_respected", "budget_respected",
           "completed_not_reoffered", "baseline_availability", "all_semantics")
PROTOCOL = {
    "version": VERSION,
    "population": "15 authored fictional customers; no NEED/customer linkage",
    "assignment": "IDs first; sort SHA256('225-ownership-v1:'+customer_id); first 9 train, next 3 validation, last 3 test",
    "expansion": "Within each assigned split, cycle 1,2,4 properties, then author chronological steps",
    "train_use": "design-only; not executed, no fit, no trained metrics or model selection",
    "execution": "validation then test; same fixed protocol, no tuning between partitions",
    "knowledge": "Only successfully recorded prefix available at each actual HTTP query; completion occurrence is not knowledge time",
    "reference": "Authored raw state and semantic constraints, not engine outputs",
    "costs_gbp_upper": UPPER,
    "arms": {
        "scoped_memory": "HTTP GET of requested customer/property, real engine/ranker",
        "owner_blind_memory": "Same engine/ranker, latest written property snapshot per customer; property key discarded",
        "explicit_current_facts": "Same engine/ranker, independently authored prefix facts supplied afresh",
    },
    "negative_control": "Owner-blind single-property history must tie; multi-property mismatches demonstrate lost binding, not superior algorithm",
    "metrics": list(METRICS),
    "aggregation": "Separate validation/test, cardinality and per customer; overlapping query criteria, no independent-row confidence intervals",
    "acceptance": "Every scoped semantic and operational check; explicit-facts parity; source stability; zero network/provider/model-load attempts",
    "limits": "SQLite standalone production router with production HomeInput; not browser, PostgreSQL, migration, provider accuracy, population benefit or physical savings",
}
PROTECTED = (
    "scripts/evaluate_memory.py", "docs/MEMORY_EVALUATION.md",
    "docs/EVALUATION_PROTOCOL.md", "reports/memory_evaluation.json",
    "data/reference_cases.json", "data/reference_cases_manifest.json",
    "reports/reference_metrics.json", "reports/reference_predictions.json",
    "reports/training_metrics.json", "reports/training.log",
    "reports/test_predictions.csv", "reports/validation_predictions.csv",
    "data/energy_splits.csv", "data/synthetic_value_properties.csv",
    "data/synthetic_value_scenarios.csv", "models/energy_benchmark.joblib",
    "models/synthetic_value.joblib",
)
SOURCES = ("greenhome/workspace_api.py", "greenhome/workspace_store.py",
           "greenhome/workspace_migration.py",
           "greenhome/api.py", "greenhome/engine.py", "greenhome/ranking.py",
           "greenhome/service.py", "greenhome/security.py",
           "docs/MULTI_PROPERTY_CONTRACT.md", "scripts/evaluate_ownership.py",
           "tests/test_ownership_evaluation.py")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def hashes(names):
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names if (ROOT / name).is_file()}


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path, value, *, exclusive=False):
    with path.open("x" if exclusive else "w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def authored_home(index, slot):
    """Raw plausible fiction. Deliberately not engine.demo_homes()/candidate output."""
    return {
        "property_id": f"OWN-C{index:03d}-P{slot + 1:02d}",
        "property_type": ("Detached", "Semi detached", "Mid terrace", "Bungalow")[slot],
        "age_band": 1 + index % 4,
        "region": "W92000004" if index % 3 == 0 else "E12000007",
        "floor_area_m2": float(75 + slot * 25 + index),
        "epc_rating": "E", "electricity_kwh": float(3200 + slot * 400 + index * 10),
        "gas_kwh": float(12000 + slot * 1200 + index * 100),
        "heating": "gas_boiler", "insulation": "poor", "glazing": "single",
        "solar_kwp": 0.0, "smart_controls": False, "roof_access": True,
        "listed_building": False, "consent_confirmed": True, "heat_pump_ready": True,
        "current_value_gbp": float(220000 + slot * 30000), "budget_gbp": None,
        "data_kind": "synthetic_demo", "excluded_retrofits": [],
    }


def empty_preferences():
    return {"budget_gbp": None, "deferred_retrofits": [],
            "priority": "energy", "disruption": "flexible"}


def make_case(customer_id, split, cardinality, index):
    props = [
        {"logical_property_id": f"{customer_id}-P{i+1:02d}",
         "home": authored_home(index, i), "preferences": empty_preferences(),
         "selected_retrofits": [], "events": [], "baseline_status": "current",
         "review_status": "new"}
        for i in range(cardinality)
    ]
    start = START + index * 1000
    steps = []

    def step(kind, **values):
        steps.append({"at": start + 10 * (len(steps) + 1), "kind": kind, **values})

    step("query", phase="initial")
    step("local_exclusion", property=0, deferred=["solar_pv"])
    step("query", phase="local_exclusion")
    step("customer_exclusion", deferred=["smart_controls"])
    step("query", phase="customer_exclusion")
    step("exclusion_rejections")
    step("plan_and_budget", property=0, selected=["loft_insulation"], budget_gbp=2000.0)
    step("query", phase="property_budget")
    step("shared_cap", cap=1950.0)
    step("query", phase="shared_cap")
    step("allocation_rejections")
    step("future_completion_rejected", completed_on="2026-10-12")
    step("query", phase="before_recording_backdated_event")
    step("complete", property=0, retrofit_id="loft_insulation", completed_on="2026-10-09")
    step("query", phase="after_recording_backdated_event")
    step("duplicate_and_unconfirmed_rejected")
    step("query", phase="replacement_not_confirmed")
    step("refresh", property=0, electricity_kwh=3900.0 + index, gas_kwh=11000.0 + index)
    step("query", phase="replacement_confirmed")
    case = {"customer_id": customer_id, "split": split, "property_count": cardinality,
            "properties": props, "steps": steps}
    # Materialize labels before candidate import/execution. The reducer uses only
    # authored inputs and contract rules, not engine/store helpers.
    for s in steps:
        if s["kind"] == "query":
            s["expected"] = reference_prefix(case, s["at"])
    return case


def reference_prefix(case, query_at, *, owner_blind=False):
    state = deepcopy(case["properties"])
    customer_exclusions, cap, last_touched = [], None, len(state) - 1
    for s in case["steps"]:
        if s["at"] >= query_at:
            break
        kind = s["kind"]
        if kind == "local_exclusion":
            state[0]["preferences"]["deferred_retrofits"] = s["deferred"][:]
            last_touched = 0
        elif kind == "customer_exclusion":
            customer_exclusions = s["deferred"][:]
        elif kind == "plan_and_budget":
            state[0]["preferences"]["budget_gbp"] = s["budget_gbp"]
            state[0]["selected_retrofits"] = s["selected"][:]
            last_touched = 0
        elif kind == "shared_cap":
            cap = s["cap"]
        elif kind == "complete":
            state[0]["home"]["insulation"] = "good"
            state[0]["home"]["electricity_kwh"] = None
            state[0]["home"]["gas_kwh"] = None
            state[0]["selected_retrofits"] = []
            state[0]["baseline_status"] = "needs_update"
            state[0]["events"] = [{
                "kind": "completed", "retrofit_id": "loft_insulation",
                "completed_on": s["completed_on"], "created_at": iso(s["at"]),
                "planning_cost_upper_gbp": 1600,
            }]
            last_touched = 0
        elif kind == "refresh":
            state[0]["home"]["electricity_kwh"] = s["electricity_kwh"]
            state[0]["home"]["gas_kwh"] = s["gas_kwh"]
            state[0]["baseline_status"] = "current"
            last_touched = 0
    planned = sum(UPPER[r] for p in state for r in p["selected_retrofits"])
    reserved = sum(e["planning_cost_upper_gbp"] for p in state for e in p["events"])
    for p in state:
        p["home"]["budget_gbp"] = p["preferences"]["budget_gbp"]
        p["home"]["excluded_retrofits"] = sorted(
            set(customer_exclusions) | set(p["preferences"]["deferred_retrofits"]))
    if owner_blind:
        # Plausible legacy customer-root memory: remembers facts but not which
        # property they describe. Settings still apply at customer scope.
        state = [{**deepcopy(state[last_touched]),
                  "logical_property_id": p["logical_property_id"],
                  "home": {**deepcopy(state[last_touched]["home"]),
                           "property_id": p["home"]["property_id"]}}
                 for p in state]
    return {
        "properties": state, "customer_exclusions": customer_exclusions,
        "portfolio_budget_gbp": cap,
        "budget_summary": {
            "planned_upper_gbp": planned, "completed_reserved_gbp": reserved,
            "total_reserved_gbp": planned + reserved,
            "remaining_gbp": None if cap is None else cap - planned - reserved,
            "status": "unlimited" if cap is None else "within_budget",
        },
    }


def generate_cases():
    # Intentionally separated phases: no property or event exists during split.
    identities = [f"OWN-C{i:03d}" for i in range(1, 16)]
    ordered = sorted(identities, key=lambda cid: hashlib.sha256(
        f"225-ownership-v1:{cid}".encode()).hexdigest())
    assignments = [{"customer_id": cid, "split": SPLITS[0 if j < 9 else 1 if j < 12 else 2]}
                   for j, cid in enumerate(ordered)]
    cases = []
    for split in SPLITS:
        for n, assignment in enumerate(a for a in assignments if a["split"] == split):
            cid = assignment["customer_id"]
            cases.append(make_case(cid, split, (1, 2, 4)[n % 3], int(cid[-3:])))
    return {"protocol": deepcopy(PROTOCOL), "assignments_before_expansion": assignments,
            "cases": cases}


def validate_cases(data):
    if data["protocol"] != PROTOCOL:
        raise ValueError("Protocol changed: do not relabel an existing freeze.")
    if data != generate_cases():
        raise ValueError("Reference differs from the independent authored specification.")
    customers, properties = set(), set()
    for case in data["cases"]:
        cid = case["customer_id"]
        if cid in customers:
            raise ValueError("Customer appears in multiple episodes/splits.")
        customers.add(cid)
        for p in case["properties"]:
            if p["logical_property_id"] in properties:
                raise ValueError("Property crosses customers/splits.")
            properties.add(p["logical_property_id"])
        stamps = [s["at"] for s in case["steps"]]
        if stamps != sorted(set(stamps)):
            raise ValueError("Recording/query time must strictly increase.")
    return data


def freeze():
    if CASES.exists() or MANIFEST.exists():
        raise ValueError("Freeze already exists; refusing to overwrite reference evidence.")
    data = validate_cases(generate_cases())
    originals = {
        name: hashlib.sha256((Path("/home/ubuntu/Downloads") / name).read_bytes()).hexdigest()
        for name in ("LLOYDS-ps2.pdf", "PS2 Green Home Score - condensed.pptx",
                     "megathon-x-guidelines.pdf", "megathon-x-deliverables.pdf")
    }
    manifest = {
        "version": VERSION, "frozen_at_utc": iso(datetime.now(timezone.utc).timestamp()),
        "candidate_executed_before_freeze": False, "reference_sha256": sha(data),
        "protocol_sha256": sha(PROTOCOL), "protected_files_sha256": hashes(PROTECTED),
        "source_at_freeze_sha256": hashes(SOURCES), "original_materials_sha256": originals,
    }
    write_json(CASES, data, exclusive=True)
    write_json(MANIFEST, manifest, exclusive=True)
    return manifest


def load_frozen():
    data = validate_cases(json.loads(CASES.read_text()))
    manifest = json.loads(MANIFEST.read_text())
    if sha(data) != manifest["reference_sha256"] or sha(PROTOCOL) != manifest["protocol_sha256"]:
        raise ValueError("Frozen reference/protocol hash mismatch.")
    if hashes(PROTECTED) != manifest["protected_files_sha256"]:
        raise ValueError("Pre-existing evaluation/model/reference evidence changed.")
    return data, manifest


@contextmanager
def offline_guard(database_path):
    """Block connections/provider imports/loaders before importing candidate code."""
    counts = Counter(network_attempts=0, provider_attempts=0, model_load_attempts=0,
                     benchmark_stub_calls=0, value_stub_calls=0, dotenv_calls_blocked=0)

    def no_network(*args, **kwargs):
        counts["network_attempts"] += 1
        raise AssertionError("Ownership evaluation forbids external connections.")

    class NoProviders(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith(("google.genai", "google.generativeai", "openai", "anthropic")):
                counts["provider_attempts"] += 1
                raise AssertionError("Ownership evaluation forbids provider SDK imports.")
            return None

    fake = ModuleType("greenhome.ml")

    def benchmark(home):
        counts["benchmark_stub_calls"] += 1
        return None

    def value(home, selected):
        counts["value_stub_calls"] += 1
        return {"status": "unavailable", "low_gbp": None, "high_gbp": None,
                "low_percent": None, "high_percent": None, "note": "Offline ownership test stub."}

    def no_model(*args, **kwargs):
        counts["model_load_attempts"] += 1
        raise AssertionError("Fitted models are outside the ownership evaluation.")

    def no_dotenv(*args, **kwargs):
        counts["dotenv_calls_blocked"] += 1
        return False

    def no_provider(*args, **kwargs):
        counts["provider_attempts"] += 1
        raise AssertionError("Ownership evaluation forbids provider transports.")

    fake.predict_energy_benchmark, fake.predict_value_impact = benchmark, value
    overrides = {
        "GREENHOME_WORKSPACE_DATABASE_URL": f"sqlite:///{database_path}",
        "GREENHOME_WORKSPACE_MAX_WORKSPACES": "1000",
        "GREENHOME_WORKSPACE_MAX_CREATIONS_PER_DAY": "1000",
        "GREENHOME_PUBLIC_MODE": "false", "GREENHOME_WARM_MODELS": "false",
        "GREENHOME_LIVE_GEMINI": "false", "GREENHOME_LIVE_LLM": "false",
        "GREENHOME_LLM_PROVIDER": "gemini", "GREENHOME_GATEWAY_TOKEN": "",
        "GEMINI_API_KEY": "", "GEMINI_KEY": "", "XKIRO_API_KEY": "",
        "GREENHOME_ALLOWED_ORIGINS": "http://testserver",
        "GREENHOME_ALLOWED_HOSTS": "testserver,localhost",
    }
    finder = NoProviders()
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, overrides))
        stack.enter_context(patch.dict(sys.modules, {"greenhome.ml": fake}))
        for name in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex"):
            stack.enter_context(patch(name, no_network))
        # Do not read .env at all. No existing credentials are copied or logged.
        stack.enter_context(patch("dotenv.load_dotenv", no_dotenv))
        import joblib
        stack.enter_context(patch.object(joblib, "load", no_model))
        sys.meta_path.insert(0, finder)
        try:
            from greenhome import explain, providers
            stack.enter_context(patch.object(explain, "_sdk_transport", no_provider))
            stack.enter_context(patch.object(providers, "xkiro_transport", no_provider))
            yield counts
        finally:
            sys.meta_path.remove(finder)


def controller(home):
    from greenhome import engine
    from greenhome.ranking import rank_homes
    row = rank_homes([deepcopy(home)])["rows"][0]
    screened = engine.screen_home(deepcopy(home))
    return {
        "selected": row["selected_retrofits"], "status": row["status"],
        "feasible": sorted(r["id"] for r in screened["recommendations"] if r["feasible"]),
        "improvement_percent": row["improvement_percent"],
        "electricity_saving_kwh": row["electricity_saving_kwh"],
        "gas_saving_kwh": row["gas_saving_kwh"],
    }


def semantic_criteria(actual_home, output, expected):
    truth = expected["home"]
    offered = set(output["selected"]) | set(output["feasible"])
    completed = {e["retrofit_id"] for e in expected["events"]}
    budget = truth["budget_gbp"]
    missing = expected["baseline_status"] == "needs_update"
    raw_equal = all(
        sorted(actual_home.get(k, [])) == sorted(v) if k == "excluded_retrofits"
        else actual_home.get(k) == v
        for k, v in truth.items()
    )
    criteria = {
        "exact_property_facts": raw_equal,
        "exclusions_respected": not (offered & set(truth["excluded_retrofits"]))
        if truth["excluded_retrofits"] else None,
        "budget_respected": sum(UPPER.get(r, float("inf")) for r in output["selected"]) <= budget
        if budget is not None else None,
        "completed_not_reoffered": not (offered & completed) if completed else None,
        "baseline_availability": (
            output["status"] == "insufficient_evidence" and not output["selected"]
            and all(output[k] is None for k in ("improvement_percent",
                                               "electricity_saving_kwh", "gas_saving_kwh"))
        ) if missing else (
            output["status"] in ("available", "no_affordable_option", "no_modelled_benefit")
            and output["improvement_percent"] is not None
        ),
    }
    criteria["all_semantics"] = all(v for v in criteria.values() if v is not None)
    return criteria


class BoundaryUnavailable(RuntimeError):
    pass


class Harness:
    """All candidate state mutations are real HTTP requests, never store callbacks."""

    def __init__(self, clock):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        # Production HomeInput, with .env blocked by offline_guard before import.
        from greenhome.api import HomeInput
        from greenhome.workspace_api import create_workspace_router

        def no_ranker(*args, **kwargs):
            raise AssertionError("Persistence unexpectedly invoked a ranking callback.")

        self.router = create_workspace_router(HomeInput, no_ranker)
        self.router.workspace_store.clock = lambda: clock[0]
        app = FastAPI()
        app.include_router(self.router)
        paths = [r.path for r in self.router.routes]
        if not any(path.endswith("/properties") for path in paths):
            self.router.workspace_mutations.close()
            self.router.workspace_store.close()
            raise BoundaryUnavailable("V2 /customers/{cid}/properties route is not implemented yet.")
        self.client = TestClient(app)

    def close(self):
        self.client.close()
        self.router.workspace_mutations.close()
        self.router.workspace_store.close()


class Episode:
    def __init__(self, case, harness, foreign, clock):
        self.case, self.harness, self.foreign, self.clock = case, harness, foreign, clock
        self.client = harness.client
        self.checks, self.requests, self.queries = [], [], []
        self.workspace, self.cid, self.pids = None, None, []
        self.step = "setup"
        self.events_created = 0
        self.identity_map = {}

    def check(self, name, condition, **evidence):
        self.checks.append({"customer_id": self.case["customer_id"], "phase": self.step,
                            "name": name, "passed": bool(condition), **evidence})
        return bool(condition)

    def request(self, method, path, body=None, *, client=None, expected=200):
        client = client or self.client
        response = client.request(method, path, **({"json": body} if body is not None else {}))
        record = {"method": method, "path": path, "phase": self.step,
                  "at": iso(self.clock[0]), "status": response.status_code}
        if response.status_code != 200:
            record["error_code"] = response.json().get("detail", {}).get("code")
        self.requests.append(record)
        self.check(f"HTTP {method} {path}", response.status_code == expected,
                   expected_status=expected, actual_status=response.status_code)
        return response

    def read(self):
        response = self.request("GET", BASE)
        if response.status_code != 200:
            raise RuntimeError("Workspace read failed.")
        self.workspace = response.json()
        return self.workspace

    def read_foreign(self):
        return self.request("GET", BASE, client=self.foreign.client).json()

    def customer(self, workspace=None):
        return next(c for c in (workspace or self.workspace)["customers"] if c["id"] == self.cid)

    def prop(self, i, workspace=None):
        return next(p for p in self.customer(workspace)["properties"] if p["id"] == self.pids[i])

    def path(self, i=0, *, cid=None):
        return f"{BASE}/customers/{cid or self.cid}/properties/{self.pids[i]}"

    def payload(self, i=0, **overrides):
        p = self.prop(i)
        result = {key: deepcopy(p[key]) for key in (
            "version", "home", "preferences", "selected_retrofits", "review_status")}
        result["customer_version"] = self.customer()["version"]
        result.update(overrides)
        return result

    def completion(self, **overrides):
        return {"customer_version": self.customer()["version"], "version": self.prop(0)["version"],
                "kind": "completed", "retrofit_id": "loft_insulation",
                "completed_on": "2026-10-09", "confirmed": True, **overrides}

    def save(self, i=0, **changes):
        before = deepcopy(self.workspace)
        response = self.request("POST", self.path(i), self.payload(i, **changes))
        self.read()
        if response.status_code == 200:
            old = self.prop(i, before)
            self.check("property version increments once", self.prop(i)["version"] == old["version"] + 1)
            self.check("customer version increments once",
                       self.customer()["version"] == self.customer(before)["version"] + 1)
            self.siblings_unchanged(before, i)
        return response

    def siblings_unchanged(self, before, target):
        for i in range(len(self.pids)):
            if i != target:
                self.check("sibling property byte-equivalent including version",
                           self.prop(i) == self.prop(i, before), sibling=i)
        old_others = [c for c in before["customers"] if c["id"] != self.cid]
        self.check("other customers unchanged",
                   [c for c in self.workspace["customers"] if c["id"] != self.cid] == old_others)

    def settings_body(self, **overrides):
        c = self.customer()
        body = {key: deepcopy(c[key]) for key in (
            "version", "customer_preferences", "portfolio_budget_gbp", "legacy_completed_reserve_gbp")}
        body.update(overrides)
        return body

    def settings(self, **changes):
        self.request("POST", f"{BASE}/customers/{self.cid}/settings", self.settings_body(**changes))
        self.read()

    def reject(self, path, payload, status, *, client=None, method="POST", code=None):
        before = deepcopy(self.workspace)
        foreign_before = self.read_foreign()
        response = self.request(method, path, payload, client=client, expected=status)
        self.read()
        self.check("rejected operation has no local side effects", self.workspace == before)
        self.check("rejected operation has no foreign side effects",
                   self.read_foreign() == foreign_before)
        if code:
            self.check("explicit conflict code", response.json().get("detail", {}).get("code") == code)

    def setup(self):
        self.request("POST", BASE, {"consent": True})
        self.request("POST", BASE, {"consent": True}, client=self.foreign.client)
        self.read()
        self.check("canonical schema v2", self.workspace.get("schema_version") == 2)
        self.cid = self.workspace["customers"][0]["id"]
        initial = self.customer()["properties"][0]
        self.pids = [initial["id"]]
        for i in range(1, self.case["property_count"]):
            before = deepcopy(self.customer()["properties"])
            response = self.request("POST", f"{BASE}/customers/{self.cid}/properties",
                                    {"customer_version": self.customer()["version"], "template_id": "DEMO-01"})
            if response.status_code != 200:
                raise RuntimeError("Property expansion failed.")
            self.read()
            new = [p for p in self.customer()["properties"] if p["id"] not in self.pids]
            if len(new) != 1:
                raise RuntimeError("Expansion did not create exactly one new property.")
            p = new[0]
            self.check("addition creates independent empty state",
                       p["events"] == [] and p["selected_retrofits"] == []
                       and p["preferences"]["deferred_retrofits"] == [])
            self.check("addition leaves existing property versions and state unchanged",
                       [p for p in self.customer()["properties"] if p["id"] in self.pids] == before)
            self.pids.append(p["id"])
        for i, raw in enumerate(self.case["properties"]):
            home = {**deepcopy(raw["home"]), "property_id": self.prop(i)["home"]["property_id"]}
            self.save(i, home=home, preferences=deepcopy(raw["preferences"]),
                      selected_retrofits=[], review_status="new")
        homes = [p["home"]["property_id"] for c in self.workspace["customers"] for p in c["properties"]]
        self.check("all workspace home identifiers unique", len(homes) == len(set(homes)))
        self.check("all properties bind to correct parent",
                   all(p["customer_id"] == self.cid for p in self.customer()["properties"]))
        self.identity_map = {
            "logical_customer_id": self.case["customer_id"],
            "workspace_id": self.workspace["id"], "runtime_customer_id": self.cid,
            "properties": [
                {"logical_property_id": p["logical_property_id"], "resource_id": self.pids[i],
                 "engine_home_id": self.prop(i)["home"]["property_id"]}
                for i, p in enumerate(self.case["properties"])
            ],
            "support_customers_not_cohort_members": 7,
            "support_properties_not_cohort_members": 7,
            "total_workspaces_created": 2,
            "total_customer_records_created": 8,
            "total_property_records_created": 7 + len(self.pids),
        }
        self.scope_checks()

    def scope_checks(self):
        other_cid = next(c["id"] for c in self.workspace["customers"] if c["id"] != self.cid)
        for i in range(len(self.pids)):
            for client, cid in ((self.client, other_cid), (self.foreign.client, self.cid)):
                self.reject(self.path(i, cid=cid), None, 404, client=client, method="GET")
                self.reject(self.path(i, cid=cid), self.payload(i), 404, client=client)
                body = {**self.completion(), "version": self.prop(i)["version"]}
                self.reject(self.path(i, cid=cid) + "/events", body, 404, client=client)
        for suffix, body in (
            ("settings", self.settings_body()),
            ("properties", {"customer_version": self.customer()["version"], "template_id": "DEMO-01"}),
        ):
            self.reject(f"{BASE}/customers/{self.cid}/{suffix}", body, 404, client=self.foreign.client)
        body = self.payload()
        body.pop("customer_version")
        body["version"] = self.customer()["version"]
        if len(self.pids) == 1:
            self.request("POST", f"{BASE}/customers/{self.cid}", body)
            self.read()
        else:
            self.reject(f"{BASE}/customers/{self.cid}", body, 409, code="property_required")
            legacy_event = self.completion()
            legacy_event.pop("customer_version")
            legacy_event["version"] = self.customer()["version"]
            self.reject(f"{BASE}/customers/{self.cid}/events", legacy_event, 409, code="property_required")
        bad = self.payload()
        bad["home"]["property_id"] = "FORGED-PROPERTY-ID"
        self.reject(self.path(), bad, 422)
        bad = self.payload()
        bad["customer_version"] -= 1
        self.reject(self.path(), bad, 409)
        bad = self.payload()
        bad["version"] -= 1
        self.reject(self.path(), bad, 409)

    def query(self, step):
        truth = step["expected"]
        blind = reference_prefix(self.case, step["at"], owner_blind=True)
        self.read()
        c = self.customer()
        self.check("customer exclusions match raw reference",
                   sorted(c["customer_preferences"]["deferred_retrofits"]) == sorted(truth["customer_exclusions"]))
        self.check("shared cap exact reference", c["portfolio_budget_gbp"] == truth["portfolio_budget_gbp"])
        self.check("planning totals exact independent reference",
                   all(c["budget_summary"].get(k) == v for k, v in truth["budget_summary"].items()))
        for i, expected in enumerate(truth["properties"]):
            response = self.request("GET", self.path(i))
            p = self.prop(i, response.json())
            expected = deepcopy(expected)
            expected["home"]["property_id"] = self.identity_map["properties"][i]["engine_home_id"]
            self.check("engine home identifier remains immutable",
                       p["home"]["property_id"] == expected["home"]["property_id"], property=i)
            self.check("raw property preferences stay separate", p["preferences"] == expected["preferences"], property=i)
            self.check("saved selection exact reference", p["selected_retrofits"] == expected["selected_retrofits"], property=i)
            self.check("baseline flag exact reference", p["baseline_status"] == expected["baseline_status"], property=i)
            event_projection = [{k: e.get(k) for k in (
                "kind", "retrofit_id", "completed_on", "created_at", "planning_cost_upper_gbp")} for e in p["events"]]
            self.check("recorded history equals available prefix", event_projection == expected["events"], property=i)
            self.check("history event IDs are unique",
                       len({e["id"] for e in p["events"]}) == len(p["events"]), property=i)
            blind_home = deepcopy(blind["properties"][i]["home"])
            blind_home["property_id"] = expected["home"]["property_id"]
            # Portfolio cap is planning accounting, not an individual ranking
            # objective. Both references and actual homes use per-property budget.
            inputs = {"scoped_memory": deepcopy(p["home"]), "owner_blind_memory": blind_home,
                      "explicit_current_facts": deepcopy(expected["home"])}
            arms = {}
            for arm, home in inputs.items():
                output = controller(home)
                arms[arm] = {"input": home, "output": output,
                             "criteria": semantic_criteria(home, output, expected)}
            self.check("scoped result satisfies raw semantic reference",
                       arms["scoped_memory"]["criteria"]["all_semantics"], property=i)
            self.check("same-controller explicit-current-facts parity",
                       arms["scoped_memory"]["output"] == arms["explicit_current_facts"]["output"], property=i)
            self.queries.append({
                "customer_id": self.case["customer_id"], "split": self.case["split"],
                "property_count": self.case["property_count"],
                "logical_property_id": expected["logical_property_id"],
                "phase": step["phase"], "query_at": iso(step["at"]),
                "available_completion_events": len(p["events"]),
                "expected_available_completion_events": len(expected["events"]),
                "actual_property_state": {k: deepcopy(p[k]) for k in (
                    "id", "customer_id", "version", "updated_at", "preferences",
                    "selected_retrofits", "review_status", "baseline_status", "events")},
                "actual_customer_version": c["version"],
                "expected_property_state": expected, "arms": arms,
            })

    def run_step(self, s):
        self.clock[0], self.step = s["at"], s.get("phase", s["kind"])
        kind = s["kind"]
        if kind == "query":
            self.query(s)
        elif kind == "local_exclusion":
            prefs = {**self.prop(0)["preferences"], "deferred_retrofits": s["deferred"]}
            self.save(preferences=prefs)
        elif kind == "customer_exclusion":
            prefs = {**self.customer()["customer_preferences"], "deferred_retrofits": s["deferred"]}
            self.settings(customer_preferences=prefs)
        elif kind == "exclusion_rejections":
            self.reject(self.path(), self.payload(selected_retrofits=["solar_pv"]), 422)
            for i in range(len(self.pids)):
                self.reject(self.path(i), self.payload(i, selected_retrofits=["smart_controls"]), 422)
            if len(self.pids) > 1:
                # Local exclusion must not prohibit an affordable sibling plan.
                self.save(1, selected_retrofits=["solar_pv"])
                self.save(1, selected_retrofits=[])
        elif kind == "plan_and_budget":
            self.save(preferences={**self.prop(0)["preferences"], "budget_gbp": s["budget_gbp"]},
                      selected_retrofits=s["selected"])
        elif kind == "shared_cap":
            self.settings(portfolio_budget_gbp=s["cap"])
        elif kind == "allocation_rejections":
            self.reject(f"{BASE}/customers/{self.cid}/settings",
                        self.settings_body(portfolio_budget_gbp=1599.0), 409)
            self.reject(f"{BASE}/customers/{self.cid}/settings", self.settings_body(
                customer_preferences={**self.customer()["customer_preferences"],
                                      "deferred_retrofits": ["loft_insulation"]}), 409)
            self.reject(self.path(), self.payload(preferences={
                **self.prop(0)["preferences"], "budget_gbp": 1500.0}), 422)
            if len(self.pids) > 1:
                self.reject(self.path(1), self.payload(1, selected_retrofits=["loft_insulation"]), 409)
        elif kind == "future_completion_rejected":
            self.reject(self.path() + "/events", self.completion(completed_on=s["completed_on"]), 422)
        elif kind == "complete":
            before = deepcopy(self.workspace)
            response = self.request("POST", self.path() + "/events", self.completion())
            self.read()
            if response.status_code == 200:
                self.events_created += 1
            self.siblings_unchanged(before, 0)
            self.check("completion increments target property version once",
                       self.prop(0)["version"] == self.prop(0, before)["version"] + 1)
            self.check("completion increments customer version once",
                       self.customer()["version"] == self.customer(before)["version"] + 1)
            self.check("completion preserves planning allocation",
                       self.customer()["budget_summary"]["total_reserved_gbp"]
                       == self.customer(before)["budget_summary"]["total_reserved_gbp"])
        elif kind == "duplicate_and_unconfirmed_rejected":
            self.reject(self.path() + "/events", self.completion(), 422)
            home = {**self.prop(0)["home"], "electricity_kwh": 3900.0, "gas_kwh": 11000.0}
            self.reject(self.path(), self.payload(home=home), 422)
        elif kind == "refresh":
            home = {**self.prop(0)["home"], "electricity_kwh": s["electricity_kwh"],
                    "gas_kwh": s["gas_kwh"]}
            self.save(home=home, baseline_confirmed_after_completion=True)
        else:
            raise ValueError(f"Unknown frozen step {kind}")

    def replay_audit(self):
        """Assert against the actual captured HTTP-prefix inputs, not timeline labels."""
        before = [q for q in self.queries if q["phase"] == "before_recording_backdated_event"]
        after = [q for q in self.queries if q["phase"] == "after_recording_backdated_event"]
        a, b = before[0], after[0]
        self.check("real prior query saw poor insulation and known fuels",
                   a["arms"]["scoped_memory"]["input"]["insulation"] == "poor"
                   and a["arms"]["scoped_memory"]["input"]["gas_kwh"] is not None)
        self.check("real subsequent query saw completion and unknown fuels",
                   b["arms"]["scoped_memory"]["input"]["insulation"] == "good"
                   and b["arms"]["scoped_memory"]["input"]["gas_kwh"] is None)
        self.check("backdated occurrence was unavailable before recording",
                   a["available_completion_events"] == 0 and b["available_completion_events"] == 1
                   and "2026-10-09" < a["query_at"] < b["query_at"])
        if len(self.pids) > 1:
            self.check("actual sibling queries unchanged across completion",
                       all(x["arms"]["scoped_memory"] == y["arms"]["scoped_memory"]
                           for x, y in zip(before[1:], after[1:])))
        else:
            self.check("one-property negative control ties on every query",
                       all(q["arms"]["scoped_memory"]["output"] == q["arms"]["owner_blind_memory"]["output"]
                           for q in self.queries))

    def concurrency(self):
        if len(self.pids) < 2:
            return
        self.step = "concurrent_sibling_reservations"
        self.settings(customer_preferences={**self.customer()["customer_preferences"], "deferred_retrofits": []})
        second = Harness(self.clock)
        try:
            second.client.cookies.update(self.client.cookies)
            before = deepcopy(self.workspace)
            bodies = [self.payload(i, selected_retrofits=["smart_controls"]) for i in (0, 1)]
            barrier = threading.Barrier(2)

            def send(i):
                barrier.wait(timeout=10)
                return (self.client if i == 0 else second.client).post(self.path(i), json=bodies[i])

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(send, i) for i in (0, 1)]
                responses = [f.result(timeout=30) for f in futures]
            for i, response in enumerate(responses):
                self.requests.append({"method": "POST", "path": self.path(i), "phase": self.step,
                                      "at": iso(self.clock[0]), "status": response.status_code})
            self.read()
            self.check("independent stores allow exactly one sibling allocation",
                       sorted(r.status_code for r in responses) == [200, 409])
            winners = [i for i, r in enumerate(responses) if r.status_code == 200]
            if len(winners) == 1:
                winner = winners[0]
                self.siblings_unchanged(before, winner)
                self.check("winning property incremented once",
                           self.prop(winner)["version"] == self.prop(winner, before)["version"] + 1)
            self.check("customer race increments once", self.customer()["version"] == self.customer(before)["version"] + 1)
            self.check("completion reserve cannot be double-spent",
                       self.customer()["budget_summary"]["total_reserved_gbp"] == 1950
                       and self.customer()["budget_summary"]["remaining_gbp"] == 0)
            self.reject(f"{BASE}/customers/{self.cid}/settings",
                        self.settings_body(portfolio_budget_gbp=1949.0), 409)
        finally:
            second.close()

    def export_delete(self):
        self.step = "restart_export_delete"
        self.read()
        exported = self.request("GET", BASE + "/export")
        self.check("export equals all authorized canonical records", exported.json() == self.workspace)
        self.check("export has attachment disposition", "attachment" in exported.headers.get("content-disposition", ""))
        reopened = Harness(self.clock)
        try:
            reopened.client.cookies.update(self.client.cookies)
            self.check("new store reads committed SQL state",
                       self.request("GET", BASE, client=reopened.client).json() == self.workspace)
            foreign_before = self.read_foreign()
            self.request("POST", BASE + "/delete", {"confirm": True})
            self.request("GET", BASE, client=reopened.client, expected=401)
            # Logical records, not unverifiable forensic disk erasure.
            from sqlalchemy import func, select
            from greenhome.workspace_store import workspaces, customers, properties
            with self.harness.router.workspace_store._transaction(readonly=True) as conn:
                self.check("deleted workspace absent from SQL", conn.execute(
                    select(func.count()).select_from(workspaces).where(
                        workspaces.c.id == self.workspace["id"])).scalar_one() == 0)
                self.check("deleted customers absent from SQL", conn.execute(
                    select(func.count()).select_from(customers).where(
                        customers.c.workspace_id == self.workspace["id"])).scalar_one() == 0)
                self.check("deleted properties absent from SQL", conn.execute(
                    select(func.count()).select_from(properties).where(
                        properties.c.workspace_id == self.workspace["id"])).scalar_one() == 0)
            self.check("deletion leaves other workspace unchanged", self.read_foreign() == foreign_before)
            self.request("POST", BASE + "/delete", {"confirm": True}, client=self.foreign.client)
        finally:
            reopened.close()

    def run(self):
        self.setup()
        for s in self.case["steps"]:
            self.run_step(s)
        self.replay_audit()
        self.concurrency()
        self.export_delete()


def metric_summary(queries):
    result = {}
    for arm in ARMS:
        result[arm] = {}
        for metric in METRICS:
            values = [q["arms"][arm]["criteria"][metric] for q in queries
                      if q["arms"][arm]["criteria"][metric] is not None]
            result[arm][metric] = {
                "denominator_queries": len(values), "satisfied": sum(values),
                "violations": len(values) - sum(values),
                "rate": sum(values) / len(values) if values else None,
            }
    result["paired_all_semantics"] = dict(Counter(
        ("both_satisfied" if a and b else "scoped_only" if a else "owner_blind_only" if b else "neither")
        for q in queries
        for a, b in [(q["arms"]["scoped_memory"]["criteria"]["all_semantics"],
                      q["arms"]["owner_blind_memory"]["criteria"]["all_semantics"])]
    ))
    return result


def evaluate(data, manifest):
    before = hashes(SOURCES)
    customer_groups = {split: {c["customer_id"] for c in data["cases"] if c["split"] == split}
                       for split in SPLITS}
    property_groups = {split: {p["logical_property_id"] for c in data["cases"]
                               if c["split"] == split for p in c["properties"]} for split in SPLITS}
    report = {
        "version": VERSION, "started_at_utc": iso(datetime.now(timezone.utc).timestamp()),
        "reference_sha256": sha(data), "protocol_sha256": sha(PROTOCOL),
        "frozen_at_utc": manifest["frozen_at_utc"],
        "status": "not_executed", "source_before_sha256": before,
        "fit_performed": False, "train_results": None,
        "train_partition_use": PROTOCOL["train_use"],
        "case_results": [], "queries": [], "checks": [], "requests": [],
        "group_overlaps": {
            f"{a}_{b}_{unit}": len(groups[a] & groups[b])
            for unit, groups in (("customers", customer_groups), ("properties", property_groups))
            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))
        },
        "counts": {
            split: {"customers": sum(c["split"] == split for c in data["cases"]),
                    "properties": sum(c["property_count"] for c in data["cases"] if c["split"] == split),
                    "authored_completion_events": sum(c["split"] == split for c in data["cases"]),
                    "authored_property_queries": sum(c["property_count"] * 9 for c in data["cases"] if c["split"] == split)}
            for split in SPLITS
        },
    }
    # Runtime scratch only; no live state, source, old reports or credentials.
    with tempfile.TemporaryDirectory(prefix="greenhome-ownership-") as directory:
        clock = [START]
        with offline_guard(Path(directory) / "ownership.sqlite3") as counters:
            for case in data["cases"]:
                if case["split"] == "train":
                    continue
                clock[0] = case["steps"][0]["at"] - 5
                # Each episode owns two independent workspaces. Clock never runs
                # backwards within a workspace; a new SQL file per episode avoids
                # timestamp reversal across independent customer partitions.
                with patch.dict(os.environ, {
                    "GREENHOME_WORKSPACE_DATABASE_URL": f"sqlite:///{directory}/{case['customer_id']}.sqlite3"
                }):
                    harness = foreign = episode = None
                    row = {"customer_id": case["customer_id"], "split": case["split"],
                           "properties": case["property_count"], "status": "not_executed"}
                    try:
                        harness, foreign = Harness(clock), Harness(clock)
                        episode = Episode(case, harness, foreign, clock)
                        episode.run()
                        row["status"] = "passed" if all(c["passed"] for c in episode.checks) else "failed"
                    except BoundaryUnavailable as exc:
                        row.update(status="blocked_interface", reason=str(exc))
                    except Exception as exc:
                        # Do not reflect exception details: driver errors can contain URLs.
                        row.update(status="execution_error", exception_type=type(exc).__name__)
                    finally:
                        for instance in (harness, foreign):
                            if instance:
                                instance.close()
                        if episode:
                            report["queries"].extend(episode.queries)
                            report["checks"].extend(episode.checks)
                            report["requests"].extend(episode.requests)
                            row.update(
                                queries=len(episode.queries), http_requests=len(episode.requests),
                                completion_events_recorded=episode.events_created,
                                checks=len(episode.checks), failed_checks=sum(not c["passed"] for c in episode.checks),
                                identity_map=episode.identity_map,
                                authored_timeline_steps=len(case["steps"]),
                                completion_http_attempts=sum(r["method"] == "POST" and r["path"].endswith("/events")
                                                             for r in episode.requests),
                                successful_http_mutations=sum(r["method"] == "POST" and r["status"] == 200
                                                              for r in episode.requests),
                            )
                        report["case_results"].append(row)
            report["offline_guards"] = dict(counters)
    report["source_after_sha256"] = hashes(SOURCES)
    report["source_stable"] = before == report["source_after_sha256"]
    report["changed_sources_during_run"] = [
        name for name in set(before) | set(report["source_after_sha256"])
        if before.get(name) != report["source_after_sha256"].get(name)
    ]
    report["protected_evidence_unchanged"] = hashes(PROTECTED) == manifest["protected_files_sha256"]
    report["raw_reference_unchanged"] = sha(json.loads(CASES.read_text())) == manifest["reference_sha256"]
    report["operational_checks"] = {
        "denominator_checks": len(report["checks"]),
        "passed": sum(c["passed"] for c in report["checks"]),
        "failed": sum(not c["passed"] for c in report["checks"]),
        "note": "Overlapping assertions, not independent trials or participants.",
    }
    report["summary"] = {
        split: metric_summary([q for q in report["queries"] if q["split"] == split])
        for split in ("validation", "test")
    }
    report["by_cardinality"] = {
        str(n): metric_summary([q for q in report["queries"] if q["property_count"] == n]) for n in (1, 2, 4)
    }
    report["per_customer_metrics"] = {
        c["customer_id"]: metric_summary([q for q in report["queries"] if q["customer_id"] == c["customer_id"]])
        for c in report["case_results"]
    }
    for split in SPLITS:
        rows = [r for r in report["case_results"] if r["split"] == split]
        report["counts"][split].update(
            executed_customers=sum(r["status"] in ("passed", "failed") for r in rows),
            actual_property_queries=sum(r.get("queries", 0) for r in rows),
            actual_completion_events=sum(r.get("completion_events_recorded", 0) for r in rows),
            actual_http_requests=sum(r.get("http_requests", 0) for r in rows),
            actual_workspaces_created=sum(r.get("identity_map", {}).get("total_workspaces_created", 0) for r in rows),
            actual_customer_records_created=sum(r.get("identity_map", {}).get("total_customer_records_created", 0) for r in rows),
            actual_property_records_created=sum(r.get("identity_map", {}).get("total_property_records_created", 0) for r in rows),
            successful_http_mutations=sum(r.get("successful_http_mutations", 0) for r in rows),
            completion_http_attempts=sum(r.get("completion_http_attempts", 0) for r in rows),
        )
    if all(r["status"] == "blocked_interface" for r in report["case_results"]):
        report["status"] = "blocked_interface"
    else:
        passed = all(r["status"] == "passed" for r in report["case_results"])
        guarded = all(report["offline_guards"][k] == 0 for k in (
            "network_attempts", "provider_attempts", "model_load_attempts"))
        report["status"] = "passed" if (passed and guarded and report["source_stable"]
                                      and report["protected_evidence_unchanged"]
                                      and report["raw_reference_unchanged"]) else "failed"
    report["finished_at_utc"] = iso(datetime.now(timezone.utc).timestamp())
    report["failed_report_gates"] = [
        key for key in ("source_stable", "protected_evidence_unchanged", "raw_reference_unchanged")
        if not report[key]
    ] + [
        key for key in ("network_attempts", "provider_attempts", "model_load_attempts")
        if report["offline_guards"][key]
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Create immutable authored reference before execution.")
    parser.add_argument("--run", action="store_true", help="Execute validation/test HTTP replays against current backend.")
    args = parser.parse_args()
    if args.freeze == args.run:
        parser.error("Choose exactly one of --freeze or --run")
    if args.freeze:
        result = freeze()
        print(json.dumps({"reference_sha256": result["reference_sha256"],
                          "protocol_sha256": result["protocol_sha256"]}, indent=2))
        return 0
    data, manifest = load_frozen()
    report = evaluate(data, manifest)
    write_json(REPORT, report)
    print(json.dumps({k: report[k] for k in ("status", "counts", "offline_guards", "case_results")}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    raise SystemExit(main())
