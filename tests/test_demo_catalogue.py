"""Independent fictional browse catalogue; no models, provider or real workspace."""
from collections import Counter
import ast
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from greenhome import engine
from greenhome.ranking import rank_homes

ROOT = Path(__file__).resolve().parents[1]
TYPES = {"Detached", "Semi detached", "Mid terrace", "End terrace", "Bungalow", "Flat"}
STATUSES = {
    "available", "no_affordable_option", "no_modelled_benefit",
    "insufficient_evidence", "unsupported",
}
RANK_FIELDS = {
    "property_id", "rank", "status", "reason", "score", "classification", "flagged",
    "improvement_percent", "baseline_kwh", "selected_retrofits",
    "electricity_saving_kwh", "gas_saving_kwh", "carbon_reduction_kgco2e",
    "cost_gbp", "budget_gbp",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def catalogue_module():
    # A missing feature should be an explicit assertion failure, not collection error.
    assert importlib.util.find_spec("greenhome.demo_catalogue") is not None, (
        "Task 1 catalogue loader is not implemented"
    )
    return importlib.import_module("greenhome.demo_catalogue")


def generator_module():
    assert (ROOT / "scripts/generate_demo_catalogue.py").is_file(), (
        "Independent catalogue generator is not implemented"
    )
    return importlib.import_module("scripts.generate_demo_catalogue")


@pytest.fixture
def catalogue():
    return catalogue_module().load_catalogue()


@pytest.fixture
def client():
    assert importlib.util.find_spec("greenhome.demo_catalogue_api") is not None, (
        "Bounded catalogue router is not implemented"
    )
    module = importlib.import_module("greenhome.demo_catalogue_api")
    app = FastAPI()
    app.include_router(module.create_demo_catalogue_router())
    with TestClient(app) as result:
        yield result


def test_catalogue_has_200_unique_physical_inputs_and_unchanged_legacy():
    data = catalogue_module().load_catalogue()
    entries = data["entries"]
    assert len(entries) == data["total"] == 200
    homes = [entry["home"] for entry in entries]
    assert {home["property_id"] for home in homes} == {
        f"DEMO-{i:02d}" for i in range(1, 201)
    }
    assert len({digest({k: v for k, v in home.items() if k != "property_id"})
                for home in homes}) == 200
    # A budget, value, ID or exclusion change alone is not another physical home.
    administrative = {"property_id", "current_value_gbp", "budget_gbp",
                      "data_kind", "excluded_retrofits"}
    assert len({digest({k: v for k, v in home.items() if k not in administrative})
                for home in homes}) == 200
    # Coarse structural/energy records must not hide clones behind tiny jitter.
    assert len({(home["property_type"], home["age_band"], home["region"],
                 None if home["floor_area_m2"] is None else round(home["floor_area_m2"] / 5),
                 home["heating"], home["insulation"], home["glazing"],
                 None if home["electricity_kwh"] is None else round(home["electricity_kwh"] / 100),
                 None if home["gas_kwh"] is None else round(home["gas_kwh"] / 500))
                for home in homes}) == 200
    by_id = {home["property_id"]: home for home in homes}
    legacy = engine.demo_homes()
    assert len(legacy) == 4
    assert [by_id[home["property_id"]] for home in legacy] == legacy
    assert digest(legacy) == "543f8d1e3a0c0a0b8566699b5180978458fe656a9dba0f2a7d8a152a64d86f73"
    assert digest(rank_homes(legacy)) == "1bfe6e80ea0f27c000890efface947b39bf028de89f5df7bf7c261dd5963bdff"


def test_generated_homes_cover_types_regions_and_explicit_edge_cases(catalogue):
    entries = catalogue["entries"]
    homes = [entry["home"] for entry in entries]
    assert Counter(entry["kind"] for entry in entries) == {
        "legacy": 4, "generated": 176, "edge_case": 20,
    }
    assert {home["property_type"] for home in homes} == TYPES
    assert {home["region"] for home in homes} == {
        *(f"E1200000{i}" for i in range(1, 10)), "W92000004",
    }
    for home in homes:
        assert engine.validate_home(home) == []
        assert home["data_kind"] == "synthetic_demo"
    for field in ("floor_area_m2", "epc_rating", "electricity_kwh", "gas_kwh",
                  "heating", "insulation", "glazing", "solar_kwp", "smart_controls",
                  "roof_access", "listed_building", "consent_confirmed", "heat_pump_ready",
                  "current_value_gbp", "budget_gbp"):
        assert any(home[field] is None for home in homes), field
    for heating in ("gas_boiler", "heat_pump", "electric_resistance", "unknown"):
        assert any(home["heating"] == heating for home in homes)
    assert any(home["electricity_kwh"] == home["gas_kwh"] == 0 for home in homes)
    assert any(home["budget_gbp"] == 0 for home in homes)
    assert any(home["budget_gbp"] == 349 for home in homes)
    assert any(home["budget_gbp"] == 350 for home in homes)
    assert any(home["age_band"] == 5 for home in homes)
    assert any(home["floor_area_m2"] and home["floor_area_m2"] > 300 for home in homes)
    assert any(home["listed_building"] and home["consent_confirmed"] for home in homes)
    assert any(home["listed_building"] and home["consent_confirmed"] is False for home in homes)
    assert any(home["excluded_retrofits"] == list(engine.RETROFITS)
               for home in homes if "excluded_retrofits" in home)
    assert any(home["property_type"] == "Flat" and home["roof_access"] is True for home in homes)
    assert any(home["property_type"] == "Flat" and home["roof_access"] is False for home in homes)
    assert {entry["ranking"]["status"] for entry in entries} == STATUSES
    assert any(entry["ranking"]["electricity_saving_kwh"] is not None
               and entry["ranking"]["electricity_saving_kwh"] < 0 for entry in entries)


def test_global_ranks_match_individual_engine_rows_and_competition_ties(catalogue):
    entries = catalogue["entries"]
    unranked_seen = False
    previous = None
    previous_rank = None
    previous_id = None
    for position, entry in enumerate(entries, 1):
        home, row = entry["home"], entry["ranking"]
        assert set(entry) == {"home", "label", "kind", "notes", "ranking"}
        assert entry["label"] and isinstance(entry["notes"], list) and entry["notes"]
        assert set(row) == RANK_FIELDS
        expected = rank_homes([home])["rows"][0]
        assert {k: v for k, v in row.items() if k != "rank"} == {
            k: v for k, v in expected.items() if k != "rank"
        }
        value = row["improvement_percent"]
        if value is None:
            unranked_seen = True
            assert row["rank"] is None
        else:
            assert not unranked_seen
            if previous is not None:
                assert value <= previous
            if value == previous:
                assert row["rank"] == previous_rank
                assert row["property_id"] > previous_id
            else:
                assert row["rank"] == position
            previous, previous_rank, previous_id = value, row["rank"], row["property_id"]
    assert any(entry["ranking"]["rank"] and entry["ranking"]["rank"] > 100 for entry in entries)
    zero_ranks = {entry["ranking"]["rank"] for entry in entries
                  if entry["ranking"]["improvement_percent"] == 0}
    assert len(zero_ranks) == 1
    with pytest.raises(ValueError, match="100"):
        rank_homes([entry["home"] for entry in entries[:101]])


def test_global_rank_assignment_discards_batch_ranks_and_handles_ties():
    module = importlib.import_module("greenhome.ranking")
    assert hasattr(module, "assign_global_ranks"), "Global rank assignment extraction is missing"
    rows = [
        {"property_id": "B", "rank": 99, "improvement_percent": 10.0},
        {"property_id": "unknown", "rank": 1, "improvement_percent": None},
        {"property_id": "C", "rank": 1, "improvement_percent": 0.0},
        {"property_id": "A", "rank": 99, "improvement_percent": 10.0},
    ]
    result = module.assign_global_ranks(rows)
    assert [(row["property_id"], row["rank"]) for row in result] == [
        ("A", 1), ("B", 1), ("C", 3), ("unknown", None),
    ]


def test_generator_is_byte_repeatable_and_matches_checked_in_manifest(tmp_path):
    generator = generator_module()
    first, second = tmp_path / "first", tmp_path / "second"
    generator.write_catalogue(first)
    generator.write_catalogue(second)
    for name in ("demo_catalogue.json", "demo_catalogue_manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (first / name).read_bytes() == (ROOT / "data" / name).read_bytes()
    manifest = json.loads((first / "demo_catalogue_manifest.json").read_text())
    assert manifest["sha256"] == hashlib.sha256((first / "demo_catalogue.json").read_bytes()).hexdigest()
    assert manifest["synthetic"] is True
    assert manifest["training_use"] is False
    assert manifest["purpose"] == "demo_only"
    assert manifest["seed"] == 225_20261016
    assert manifest["generator_version"] and manifest["assumptions"]
    assert len(manifest["record_sha256"]) == 200
    loaded = catalogue_module().load_catalogue(
        first / "demo_catalogue.json", first / "demo_catalogue_manifest.json"
    )
    for entry in loaded["entries"]:
        assert manifest["record_sha256"][entry["home"]["property_id"]] == digest(entry["home"])
    assert manifest["distribution"]["property_type"] == dict(Counter(
        entry["home"]["property_type"] for entry in loaded["entries"]
    ))


def test_electric_space_fraction_excludes_appliances_and_hot_water():
    payload, manifest = generator_module().build_catalogue()
    checked = 0
    for entry in payload["entries"]:
        home = entry["home"]
        if entry["kind"] == "legacy" or home["heating"] not in {"heat_pump", "electric_resistance"}:
            continue
        if home["solar_kwp"] != 0:
            continue  # Existing-PV load changes explicitly abstain in the engine.
        trace = manifest["generation_trace"][home["property_id"]]
        efficiency = home["heat_pump_spf"] if home["heating"] == "heat_pump" else 1
        space_input = trace["useful_space_heat_kwh"] / efficiency
        # The engine's fraction applies to the whole electricity meter, not just
        # useful thermal demand. An unchanged 0.8 would incorrectly save appliances.
        assert home["space_heat_fraction"] * home["electricity_kwh"] == pytest.approx(
            space_input, abs=0.01
        )
        assert home["space_heat_fraction"] < 0.8
        checked += 1
    assert checked >= 10


def test_generation_energy_bookkeeping_and_correlated_fabric():
    generator = generator_module()
    payload, manifest = generator.build_catalogue()
    for entry in payload["entries"]:
        if entry["kind"] == "legacy":
            continue
        home = entry["home"]
        trace = manifest["generation_trace"][home["property_id"]]
        overrides = trace["explicit_overrides"]
        if home["electricity_kwh"] is not None and "electricity_kwh" not in overrides:
            assert home["electricity_kwh"] == pytest.approx(
                trace["gross_electricity_kwh"] - trace["self_used_pv_kwh"], abs=5.01
            )
        if home["gas_kwh"] is not None and "gas_kwh" not in overrides:
            assert home["gas_kwh"] == pytest.approx(trace["gross_gas_kwh"], abs=5.01)
        if home["heating"] in {"heat_pump", "electric_resistance"}:
            assert home["gas_kwh"] == 0
        if home["solar_kwp"] is not None:
            assert trace["self_used_pv_kwh"] == pytest.approx(min(
                trace["gross_electricity_kwh"],
                home["solar_kwp"] * home["solar_yield_kwh_per_kwp"]
                * home["solar_self_consumption_fraction"],
            ), abs=0.01)
    controls = {"heating": "gas_boiler", "floor_area_m2": 100.0, "solar_kwp": 0.0}
    poor, _ = generator._home(99, "Detached", "E12000001", {**controls, "insulation": "poor"})
    good, _ = generator._home(99, "Detached", "E12000001", {**controls, "insulation": "good"})
    assert poor["gas_kwh"] > good["gas_kwh"] > 0
    assert poor["electricity_kwh"] == good["electricity_kwh"]


def test_all_homes_validate_against_existing_homeinput_declaration(catalogue):
    # Execute the actual declarations only: importing api.py would initialize
    # its application and read .env. No alternate/home-grown input schema here.
    import math
    from typing import Annotated, Literal
    from pydantic import BaseModel, ConfigDict, Field, field_validator
    source = ROOT / "greenhome/api.py"
    names = {"RetrofitId", "Package", "Energy", "Fraction", "StrictInput", "HomeInput"}
    nodes = [node for node in ast.parse(source.read_text()).body
             if (isinstance(node, ast.ClassDef) and node.name in names)
             or (isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in names for target in node.targets))]
    namespace = {
        "__name__": __name__, "Annotated": Annotated, "Literal": Literal,
        "BaseModel": BaseModel, "ConfigDict": ConfigDict, "Field": Field,
        "field_validator": field_validator, "math": math, "engine": engine,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec",
                 dont_inherit=True), namespace)
    for entry in catalogue["entries"]:
        validated = namespace["HomeInput"].model_validate(entry["home"])
        assert validated.engine_home() == entry["home"]


def test_loader_is_defensive_and_never_recalculates_on_requests(monkeypatch):
    module = catalogue_module()
    first = module.load_catalogue()

    def forbidden(*args, **kwargs):
        pytest.fail("Serving catalogue must not screen, assess, import or call models")

    monkeypatch.setattr(engine, "screen_home", forbidden)
    monkeypatch.setattr(engine, "assess", forbidden)
    first["entries"][0]["home"]["gas_kwh"] = -100
    first["entries"][0]["ranking"]["selected_retrofits"].append("bogus")
    first["entries"][0]["notes"].append("leaked")
    first["provenance"]["synthetic"] = False
    second = module.load_catalogue()
    assert second["entries"][0]["home"]["gas_kwh"] != -100
    assert "bogus" not in second["entries"][0]["ranking"]["selected_retrofits"]
    assert "leaked" not in second["entries"][0]["notes"]
    assert second["provenance"]["synthetic"] is True
    assert module.browse_catalogue(page=1)["total"] == 200


@pytest.mark.parametrize("damage", [
    "hash", "provenance", "duplicate_id", "oversized", "rank", "unknown_field", "stale_engine",
])
def test_loader_rejects_bad_integrity_and_schema(tmp_path, damage):
    module = catalogue_module()
    data_path = tmp_path / "demo_catalogue.json"
    manifest_path = tmp_path / "demo_catalogue_manifest.json"
    payload = json.loads((ROOT / "data/demo_catalogue.json").read_text())
    manifest = json.loads((ROOT / "data/demo_catalogue_manifest.json").read_text())
    if damage == "provenance":
        manifest["training_use"] = True
    elif damage == "stale_engine":
        manifest["calculation_source_sha256"]["engine.py"] = "0" * 64
    elif damage == "duplicate_id":
        payload["entries"][1]["home"]["property_id"] = payload["entries"][0]["home"]["property_id"]
    elif damage == "rank":
        payload["entries"][0]["ranking"]["rank"] = 900
    elif damage == "unknown_field":
        payload["entries"][0]["home"]["customer_id"] = "not-allowed"
    raw = canonical(payload)
    if damage == "oversized":
        raw += b" " * (2 * 1024 * 1024)
    manifest["sha256"] = "0" * 64 if damage == "hash" else hashlib.sha256(raw).hexdigest()
    data_path.write_bytes(raw)
    manifest_path.write_bytes(canonical(manifest))
    with pytest.raises(module.CatalogueIntegrityError):
        module.load_catalogue(data_path, manifest_path)


def test_api_exact_contract_default_last_and_empty_page(client):
    response = client.get("/api/demo-catalogue")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"version", "total", "filtered_total", "page", "page_size",
                         "page_count", "entries", "summary", "provenance", "policy"}
    assert (data["total"], data["filtered_total"], data["page"], data["page_size"],
            data["page_count"], len(data["entries"])) == (200, 200, 1, 12, 17, 12)
    assert set(data["summary"]) == {"assessed", "evidence_needed", "flagged"}
    assert data["summary"]["assessed"] + data["summary"]["evidence_needed"] == 200
    assert set(data["provenance"]) == {
        "label", "synthetic", "training_use", "generator_version", "sha256",
    }
    assert data["provenance"]["synthetic"] is True
    assert data["provenance"]["training_use"] is False
    assert len(client.get("/api/demo-catalogue?page=17").json()["entries"]) == 8
    assert client.get("/api/demo-catalogue?page=18").json()["entries"] == []
    empty = client.get("/api/demo-catalogue", params={"q": "definitely no fictional home"}).json()
    assert (empty["filtered_total"], empty["page_count"], empty["entries"]) == (0, 0, [])
    assert empty["summary"] == {"assessed": 0, "evidence_needed": 0, "flagged": 0}


def test_api_filters_counts_and_ranks_remain_global(client, catalogue):
    result = client.get("/api/demo-catalogue", params={
        "property_type": "Flat", "status": "available", "page_size": 24,
    }).json()
    expected = [entry for entry in catalogue["entries"]
                if entry["home"]["property_type"] == "Flat"
                and entry["ranking"]["status"] == "available"]
    assert result["filtered_total"] == len(expected) > 0
    assert result["entries"] == expected[:24]
    assert result["summary"] == {
        "assessed": len(expected), "evidence_needed": 0,
        "flagged": sum(entry["ranking"]["flagged"] for entry in expected),
    }
    query = client.get("/api/demo-catalogue", params={"q": "  demo-200  "}).json()
    assert query["filtered_total"] == 1
    assert query["entries"][0]["home"]["property_id"] == "DEMO-200"
    assert query["entries"][0]["ranking"] == next(
        entry["ranking"] for entry in catalogue["entries"]
        if entry["home"]["property_id"] == "DEMO-200"
    )
    all_pages = []
    for page in range(1, 10):
        all_pages.extend(client.get("/api/demo-catalogue",
                                    params={"page": page, "page_size": 24}).json()["entries"])
    assert all_pages == catalogue["entries"]
    for status in STATUSES:
        subset = client.get("/api/demo-catalogue", params={"status": status}).json()
        assert subset["filtered_total"] > 0
        assert all(entry["ranking"]["status"] == status for entry in subset["entries"])
        if status in {"insufficient_evidence", "unsupported"}:
            assert subset["summary"]["evidence_needed"] == subset["filtered_total"]


@pytest.mark.parametrize("label,region", [
    ("North East", "E12000001"),
    ("North West", "E12000002"),
    ("Yorkshire and the Humber", "E12000003"),
    ("East Midlands", "E12000004"),
    ("West Midlands", "E12000005"),
    ("East of England", "E12000006"),
    ("  loNDoN  ", "E12000007"),
    ("South East", "E12000008"),
    ("South West", "E12000009"),
    ("  WALES  ", "W92000004"),
])
def test_api_region_name_search_preserves_counts_pages_and_global_ranks(client, catalogue, label, region):
    expected = [entry for entry in catalogue["entries"] if entry["home"]["region"] == region]
    assert len(expected) == 20
    expected_summary = {
        "assessed": sum(entry["ranking"]["rank"] is not None for entry in expected),
        "evidence_needed": sum(entry["ranking"]["rank"] is None for entry in expected),
        "flagged": sum(entry["ranking"]["flagged"] is True for entry in expected),
    }
    for page, expected_entries in ((1, expected[:12]), (2, expected[12:]), (3, [])):
        response = client.get("/api/demo-catalogue", params={"q": label, "page": page})
        assert response.status_code == 200
        data = response.json()
        assert (data["total"], data["filtered_total"], data["page_count"]) == (200, 20, 2)
        assert data["entries"] == expected_entries
        assert data["summary"] == expected_summary
        assert data["provenance"] == catalogue["provenance"]
        assert data == client.get("/api/demo-catalogue", params={"q": region, "page": page}).json()


@pytest.mark.parametrize("params", [
    {"q": "x" * 101}, {"property_type": "Castle"}, {"status": "unknown"},
    {"page": 0}, {"page": -1}, {"page": "1.5"}, {"page_size": 0},
    {"page_size": 25}, {"page_size": "no"}, {"property_type": ""}, {"status": ""},
])
def test_api_rejects_unbounded_or_unknown_query_values(client, params):
    assert client.get("/api/demo-catalogue", params=params).status_code == 422


def test_api_accepts_max_query_and_page_size_one(client):
    result = client.get("/api/demo-catalogue", params={"q": "x" * 100, "page_size": 1})
    assert result.status_code == 200
    assert client.get("/api/demo-catalogue?page_size=1").json()["page_count"] == 200


def test_api_integrity_failure_is_closed_and_does_not_leak_paths(client, monkeypatch, tmp_path):
    module = catalogue_module()
    module._default_catalogue.cache_clear()
    monkeypatch.setattr(module, "CATALOGUE_PATH", tmp_path / "missing-private-path.json")
    try:
        response = client.get("/api/demo-catalogue")
        assert response.status_code == 503
        assert response.json() == {"detail": {
            "code": "demo_catalogue_unavailable",
            "message": "The fictional catalogue is temporarily unavailable.",
        }}
    finally:
        module._default_catalogue.cache_clear()


def test_catalogue_serving_and_generation_import_no_api_models_or_training_data(tmp_path):
    catalogue_module()
    generator_module()
    # Guard imports and file reads in a clean process; no dotenv/application init.
    code = r'''
import pathlib, sys
root = pathlib.Path.cwd()
allowed_data = {root / "data/demo_catalogue.json", root / "data/demo_catalogue_manifest.json"}
def audit(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes)):
        return
    path = pathlib.Path(args[0]).resolve()
    if root / "models" in path.parents:
        raise AssertionError("model access forbidden")
    if root / "data" in path.parents and path not in allowed_data:
        raise AssertionError("training/reference data access forbidden")
    if path.name == ".env":
        raise AssertionError("credential access forbidden")
sys.addaudithook(audit)
from greenhome.demo_catalogue_api import create_demo_catalogue_router
from greenhome.demo_catalogue import browse_catalogue
from scripts.generate_demo_catalogue import write_catalogue
assert browse_catalogue()["total"] == 200
assert create_demo_catalogue_router()
write_catalogue(pathlib.Path(sys.argv[1]))
assert not ({"greenhome.api", "greenhome.ml", "greenhome.decision",
             "greenhome.explain", "joblib", "sklearn", "pandas"} & set(sys.modules))
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_catalogue_does_not_expand_saved_workspace_seeds(tmp_path):
    catalogue_module().load_catalogue()
    from greenhome.workspace_store import WorkspaceStore, new_token
    seeds = [{
        "home": home,
        "preferences": {"budget_gbp": home["budget_gbp"], "deferred_retrofits": [],
                        "priority": "energy", "disruption": "flexible"},
        "selected_retrofits": [], "review_status": "new",
        "baseline_status": "current", "events": [],
    } for home in engine.demo_homes()]
    store = WorkspaceStore(f"sqlite:///{tmp_path / 'workspace.sqlite3'}")
    try:
        token = new_token()
        workspace = store.create(token, seeds)
        assert len(workspace["customers"]) == 4
        assert all(len(customer["properties"]) == 1 for customer in workspace["customers"])
        assert [customer["properties"][0]["home"] for customer in workspace["customers"]] == engine.demo_homes()
        assert store.get(token) == workspace
    finally:
        store.close()
