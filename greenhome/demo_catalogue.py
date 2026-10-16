"""Bounded, read-only fictional catalogue. No API, persistence or ML imports."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Literal, get_args

from greenhome import engine
from greenhome.ranking import POLICY, assign_global_ranks

PropertyType = Literal[
    "Detached", "Semi detached", "Mid terrace", "End terrace", "Bungalow", "Flat"
]
RankingStatus = Literal[
    "available", "no_affordable_option", "no_modelled_benefit",
    "insufficient_evidence", "unsupported",
]
PROPERTY_TYPES = get_args(PropertyType)
RANKING_STATUSES = get_args(RankingStatus)
REGIONS = tuple(f"E1200000{i}" for i in range(1, 10)) + ("W92000004",)
# Authored search labels only; stored HomeInput region codes remain unchanged.
REGION_LABELS = {
    "E12000001": "North East",
    "E12000002": "North West",
    "E12000003": "Yorkshire and the Humber",
    "E12000004": "East Midlands",
    "E12000005": "West Midlands",
    "E12000006": "East of England",
    "E12000007": "London",
    "E12000008": "South East",
    "E12000009": "South West",
    "W92000004": "Wales",
}
VERSION = "1"
GENERATOR_VERSION = "greenhome-fictional-catalogue-v1"
SEED = 225_20261016
COUNT = 200
ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_PATH = ROOT / "data/demo_catalogue.json"
MANIFEST_PATH = ROOT / "data/demo_catalogue_manifest.json"
MAX_CATALOGUE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
UNRANKED = {"insufficient_evidence", "unsupported"}
RANK_FIELDS = {
    "property_id", "rank", "status", "reason", "score", "classification", "flagged",
    "improvement_percent", "baseline_kwh", "selected_retrofits",
    "electricity_saving_kwh", "gas_saving_kwh", "carbon_reduction_kgco2e",
    "cost_gbp", "budget_gbp",
}
HOME_FIELDS = set(engine.demo_homes()[0]) | {"excluded_retrofits"}


class CatalogueIntegrityError(ValueError):
    """The fixed public artifact is unavailable or fails its integrity contract."""


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def record_sha256(home: dict) -> str:
    return hashlib.sha256(canonical_json(home)).hexdigest()


def summary_for(entries: list[dict]) -> dict:
    assessed = sum(entry["ranking"]["rank"] is not None for entry in entries)
    return {
        "assessed": assessed, "evidence_needed": len(entries) - assessed,
        "flagged": sum(entry["ranking"]["flagged"] is True for entry in entries),
    }


def distribution_for(entries: list[dict]) -> dict:
    return {
        "property_type": dict(sorted(Counter(e["home"]["property_type"] for e in entries).items())),
        "region": dict(sorted(Counter(e["home"]["region"] for e in entries).items())),
        "kind": dict(sorted(Counter(e["kind"] for e in entries).items())),
        "status": dict(sorted(Counter(e["ranking"]["status"] for e in entries).items())),
    }


def _require(condition: bool) -> None:
    if not condition:
        raise CatalogueIntegrityError("Fictional catalogue integrity validation failed.")


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    _require(len(raw) <= limit)
    return raw


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _decode(raw: bytes):
    def invalid_constant(_value):
        raise CatalogueIntegrityError("Non-finite catalogue JSON is not allowed.")
    return json.loads(raw, object_pairs_hook=_object, parse_constant=invalid_constant)


def _number(value, *, nullable=True):
    return (value is None and nullable) or (
        type(value) in (int, float) and math.isfinite(value)
    )


def _validate_home(home: dict) -> None:
    _require(isinstance(home, dict) and set(home) <= HOME_FIELDS)
    _require(set(engine.demo_homes()[0]) <= set(home))
    _require(not engine.validate_home(home))
    _require(home["property_type"] in PROPERTY_TYPES)
    _require(home["region"] in REGIONS)
    _require(home["age_band"] is None or
             (type(home["age_band"]) is int and 1 <= home["age_band"] <= 5))
    _require(home["floor_area_m2"] is None or home["floor_area_m2"] >= 0.01)
    _require(home["data_kind"] == "synthetic_demo")


def _validate_ranking(row: dict, home: dict) -> None:
    _require(isinstance(row, dict) and set(row) == RANK_FIELDS)
    _require(row["property_id"] == home["property_id"])
    _require(row["status"] in RANKING_STATUSES)
    _require(isinstance(row["reason"], str) and 0 < len(row["reason"]) <= 8000)
    _require(isinstance(row["classification"], str))
    _require(type(row["flagged"]) is bool)
    _require(row["score"] is None or
             (type(row["score"]) is int and 0 <= row["score"] <= 100))
    for key in ("improvement_percent", "baseline_kwh", "electricity_saving_kwh",
                "gas_saving_kwh", "carbon_reduction_kgco2e", "budget_gbp"):
        _require(_number(row[key]))
    _require(row["budget_gbp"] == home["budget_gbp"])
    _require(row["baseline_kwh"] == engine._total(home["electricity_kwh"], home["gas_kwh"]))
    selected = row["selected_retrofits"]
    _require(isinstance(selected, list) and len(selected) <= 5)
    _require(all(isinstance(rid, str) and rid in engine.RETROFITS for rid in selected))
    _require(len(set(selected)) == len(selected))
    if row["status"] in UNRANKED:
        _require(all(row[key] is None for key in (
            "rank", "improvement_percent", "electricity_saving_kwh",
            "gas_saving_kwh", "carbon_reduction_kgco2e", "cost_gbp",
        )))
        _require(selected == [])
    else:
        _require(type(row["rank"]) is int and 1 <= row["rank"] <= COUNT)
        _require(_number(row["improvement_percent"], nullable=False)
                 and 0 <= row["improvement_percent"] <= 100)
        _require(all(_number(row[key], nullable=False) for key in (
            "electricity_saving_kwh", "gas_saving_kwh", "carbon_reduction_kgco2e",
        )))
        costs = row["cost_gbp"]
        _require(isinstance(costs, list) and len(costs) == 2)
        _require(all(_number(cost, nullable=False) for cost in costs))
        _require(0 <= costs[0] <= costs[1])


def _load(catalogue_path: Path, manifest_path: Path) -> dict:
    try:
        raw = _read_bounded(catalogue_path, MAX_CATALOGUE_BYTES)
        manifest = _decode(_read_bounded(manifest_path, MAX_MANIFEST_BYTES))
        sha = hashlib.sha256(raw).hexdigest()
        _require(manifest["sha256"] == sha)
        _require(manifest["synthetic"] is True and manifest["training_use"] is False)
        _require(manifest["version"] == VERSION and manifest["schema_version"] == 1)
        _require(manifest["generator_version"] == GENERATOR_VERSION and manifest["seed"] == SEED)
        _require(manifest["purpose"] == "demo_only" and manifest["count"] == COUNT)
        _require(isinstance(manifest["label"], str) and bool(manifest["label"]))
        _require(bool(manifest["assumptions"]))
        # Detect an accidentally stale numerical snapshot after engine changes.
        for name in ("engine.py", "ranking.py"):
            expected = manifest["calculation_source_sha256"][name]
            _require(expected == hashlib.sha256((ROOT / "greenhome" / name).read_bytes()).hexdigest())
        payload = _decode(raw)
        _require(set(payload) == {"version", "entries", "policy"})
        _require(payload["version"] == VERSION and payload["policy"] == POLICY)
        entries = payload["entries"]
        _require(isinstance(entries, list) and len(entries) == COUNT)
        ids, physical, complete = set(), set(), set()
        legacy = {home["property_id"]: home for home in engine.demo_homes()}
        for entry in entries:
            _require(isinstance(entry, dict) and set(entry) == {
                "home", "label", "kind", "notes", "ranking",
            })
            home = entry["home"]
            _validate_home(home)
            identity = home["property_id"]
            _require(isinstance(identity, str) and re.fullmatch(r"DEMO-\d{2,3}", identity) is not None)
            _require(identity not in ids)
            ids.add(identity)
            _require(entry["kind"] in {"legacy", "generated", "edge_case"})
            _require(isinstance(entry["label"], str) and 0 < len(entry["label"]) <= 200)
            _require(isinstance(entry["notes"], list) and 1 <= len(entry["notes"]) <= 12)
            _require(all(isinstance(note, str) and 0 < len(note) <= 2000 for note in entry["notes"]))
            _require(manifest["record_sha256"][identity] == record_sha256(home))
            if identity in legacy:
                _require(home == legacy[identity] and entry["kind"] == "legacy")
            else:
                _require(entry["kind"] != "legacy")
            complete.add(canonical_json({k: v for k, v in home.items() if k != "property_id"}))
            physical.add(canonical_json({k: v for k, v in home.items() if k not in {
                "property_id", "budget_gbp", "current_value_gbp", "data_kind", "excluded_retrofits",
            }}))
            _validate_ranking(entry["ranking"], home)
        _require(ids == {f"DEMO-{i:02d}" for i in range(1, COUNT + 1)})
        _require(set(manifest["record_sha256"]) == ids)
        _require(len(complete) == len(physical) == COUNT)
        rows = [entry["ranking"] for entry in entries]
        _require(rows == assign_global_ranks(deepcopy(rows)))
        _require(manifest["summary"] == summary_for(entries))
        _require(manifest["distribution"] == distribution_for(entries))
        return {
            **payload, "total": COUNT, "summary": summary_for(entries),
            "provenance": {key: manifest[key] for key in (
                "label", "synthetic", "training_use", "generator_version", "sha256",
            )},
        }
    except CatalogueIntegrityError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise CatalogueIntegrityError("Fictional catalogue is unavailable or invalid.") from exc


@lru_cache(maxsize=1)
def _default_catalogue() -> dict:
    # Fixed release artifact only: no request-controlled paths or unbounded cache.
    return _load(CATALOGUE_PATH, MANIFEST_PATH)


def load_catalogue(catalogue_path: Path | None = None, manifest_path: Path | None = None) -> dict:
    """Return defensive copies. Explicit paths are uncached offline validation only."""
    if catalogue_path is None and manifest_path is None:
        return deepcopy(_default_catalogue())
    if catalogue_path is None or manifest_path is None:
        raise CatalogueIntegrityError("Both catalogue and manifest paths are required.")
    return _load(Path(catalogue_path), Path(manifest_path))


def browse_catalogue(*, q: str = "", property_type: PropertyType | None = None,
                     status: RankingStatus | None = None, page: int = 1,
                     page_size: int = 12) -> dict:
    """Filter fixed global rows, then paginate; never renumber a filtered result."""
    if (not isinstance(q, str) or len(q) > 100
            or (property_type is not None and property_type not in PROPERTY_TYPES)
            or (status is not None and status not in RANKING_STATUSES)
            or type(page) is not int or page < 1
            or type(page_size) is not int or not 1 <= page_size <= 24):
        raise ValueError("Invalid catalogue query.")
    data = _default_catalogue()
    search = q.strip().casefold()
    entries = [
        entry for entry in data["entries"]
        if (property_type is None or entry["home"]["property_type"] == property_type)
        and (status is None or entry["ranking"]["status"] == status)
        and (not search or search in " ".join((
            entry["home"]["property_id"], entry["label"], entry["home"]["property_type"],
            entry["home"]["region"], REGION_LABELS[entry["home"]["region"]], *entry["notes"],
        )).casefold())
    ]
    count = len(entries)
    offset = (page - 1) * page_size
    return {
        "version": data["version"], "total": COUNT, "filtered_total": count,
        "page": page, "page_size": page_size, "page_count": (count + page_size - 1) // page_size,
        "entries": deepcopy(entries[offset:offset + page_size]),
        "summary": summary_for(entries), "provenance": deepcopy(data["provenance"]),
        "policy": data["policy"],
    }
