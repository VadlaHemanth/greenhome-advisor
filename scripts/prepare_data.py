#!/usr/bin/env python3
"""Fetch metadata first, prepare observed targets, and generate paired synthetic references."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from greenhome.ml import (ENERGY_FEATURES, EPC_DEFICIT, PROPERTY_TYPES, REGIONS,
                          RETROFIT_IDS, SEED, effective_retrofits, value_features)

DATA = ROOT / "data"
METADATA_URL = "https://assets.publishing.service.gov.uk/media/6a282d2be371d9d2c0052b39/NEED-2026-anonymised-dataset-metadata.ods"
DATA_URL = "https://assets.publishing.service.gov.uk/media/6a282ad83b15d05a7ce31fb1/anon2026_50k.csv"
REGION_MULTIPLIERS = dict(zip(REGIONS, (1.10, 1.05, 1.05, 1.00, 1.00, .95, .75, .90, 1.00, 1.05)))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url: str, path: Path) -> dict:
    cached = path.exists()
    if not cached:
        request = urllib.request.Request(url, headers={"User-Agent": "GreenHomeHackathon/1.0"})
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = response.read()
        if not payload:
            raise ValueError("Empty official download")
        path.write_bytes(payload)
    return {"url": url, "file": str(path.relative_to(ROOT)), "sha256": sha256(path),
            "bytes": path.stat().st_size, "used_cached_download": cached,
            "checked_utc": datetime.now(timezone.utc).isoformat()}


def parse_metadata(path: Path) -> dict:
    ns = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
          "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    sheets = {}
    for table in root.findall(".//table:table", ns):
        rows = []
        for row in table.findall("table:table-row", ns):
            values = []
            for cell in row:
                text = " ".join("".join(p.itertext()) for p in cell.findall(".//text:p", ns))
                repeat = min(int(cell.get(f"{{{ns['table']}}}number-columns-repeated", "1")), 30)
                values.extend([text] * repeat)
            while values and not values[-1]:
                values.pop()
            if values:
                rows.append(values)
        sheets[table.get(f"{{{ns['table']}}}name")] = rows
    metadata = "\n".join(" ".join(row) for row in sheets.get("Metadata", []))
    for required in ("V = valid", "E = estimated", "1930-1972", "2000 or later", "2022-2024", "50 or less"):
        if required not in metadata:
            raise ValueError(f"Metadata schema changed; missing {required!r}. Review before using data.")
    return sheets


def assign_splits(frame: pd.DataFrame, seed: int, sample_size: int | None = None) -> pd.DataFrame:
    if not frame["property_id"].is_unique:
        raise ValueError("Property IDs must be unique BEFORE any scenario expansion.")
    result = frame.copy()
    order = np.random.default_rng(seed).permutation(len(frame))
    n_train, n_validation = int(len(frame) * .6), int(len(frame) * .2)
    labels = np.full(len(frame), "test", dtype=object)
    labels[order[:n_train]] = "train"
    labels[order[n_train:n_train + n_validation]] = "validation"
    result["split"] = labels
    result["model_sample"] = False
    size = min(len(frame), sample_size or len(frame))
    counts = {"train": int(size * .6), "validation": int(size * .2)}
    counts["test"] = size - sum(counts.values())
    for split, count in counts.items():
        candidates = order[labels[order] == split]
        result.loc[result.index[candidates[:count]], "model_sample"] = True
    return result


def observed_energy(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    required = {*ENERGY_FEATURES, "MAIN_HEAT_FUEL", "Econs2024", "Gcons2024",
                "ElecValFlag2024", "GasValFlag2024"}
    if not required <= set(raw):
        raise ValueError(f"Missing NEED columns: {sorted(required - set(raw))}")
    result = raw[list(ENERGY_FEATURES)].fillna("Unknown").astype(str).copy()
    result.insert(0, "property_id", [f"NEED2026-{i + 1:06d}" for i in range(len(raw))])
    result["source_row_number"] = np.arange(1, len(raw) + 1)
    result["source_main_heat_fuel_not_a_feature"] = raw["MAIN_HEAT_FUEL"]
    audit = {}
    for target, flag, lower, upper in (("Econs2024", "ElecValFlag2024", 500, 25000),
                                      ("Gcons2024", "GasValFlag2024", 1000, 50000)):
        numeric = pd.to_numeric(raw[target], errors="coerce")
        flags = raw[flag].fillna("").astype(str)
        # Estimate flag E is excluded: targets are observations, not supplier estimates.
        valid = flags.eq("V") & numeric.notna() & np.isfinite(numeric)
        if not numeric[valid].between(lower, upper).all():
            raise ValueError(f"Metadata/observed bounds disagree for {target}; refusing silent trimming.")
        result[target] = numeric.where(valid)
        result[flag] = flags
        audit[target] = {"flag_counts": flags.replace("", "<blank>").value_counts().to_dict(),
                         "accepted": int(valid.sum()), "excluded": int((~valid).sum()),
                         "valid_flag_missing_numeric": int((flags.eq("V") & numeric.isna()).sum()),
                         "policy": "V only, finite values; E/L/G/O/blank excluded; missing remains missing"}
    return result, audit


def fallback_energy(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "property_id": [f"SYNTH-ENERGY-{i:06d}" for i in range(n)],
        "PROP_TYPE": rng.choice(PROPERTY_TYPES, n), "PROP_AGE_BAND": rng.integers(1, 5, n).astype(str),
        "FLOOR_AREA_BAND": rng.integers(1, 6, n).astype(str), "REGION": rng.choice(REGIONS, n),
        "EPC": rng.choice(["A/B", "C", "D", "E", "F/G", "No EPC"], n),
    })
    area = frame.FLOOR_AREA_BAND.astype(int).map({1: 40, 2: 75, 3: 125, 4: 175, 5: 240}).to_numpy()
    deficit = frame.EPC.map({"A/B": .6, "C": .8, "D": 1, "E": 1.2, "F/G": 1.4, "No EPC": 1}).to_numpy()
    frame["Econs2024"] = np.maximum(500, (1000 + 19 * area) * rng.lognormal(0, .35, n))
    frame["Gcons2024"] = np.maximum(1000, 95 * area * deficit * rng.lognormal(0, .35, n))
    return frame


def synthetic_reference(home: dict, active: tuple[str, ...], market_shock: float, scenario_shock: float) -> float:
    """Hypothetical percentage change: the numerical rule is NOT evidence."""
    if not active:
        return 0.0
    coefficients = {"loft_insulation": .65 if home["insulation"] == "poor" else .30,
                    "double_glazing": .60, "smart_controls": .15, "heat_pump": .35, "solar_pv": .75}
    count = len(active)
    epc_factor = .55 + .12 * EPC_DEFICIT[home["epc_rating"]]
    size_factor = float(np.clip((home["floor_area_m2"] / 100) ** .15, .8, 1.15))
    price_factor = float(np.clip((300000 / home["current_value_gbp"]) ** .2, .65, 1.2))
    type_factor = .80 if home["property_type"] == "Flat" else 1.05 if home["property_type"] == "Bungalow" else 1.0
    mean = (sum(coefficients[r] for r in active) * (1 - .06 * (count - 1))
            * epc_factor * size_factor * price_factor * type_factor * REGION_MULTIPLIERS[home["region"]])
    return float(mean + np.sqrt(count) * (.55 * market_shock + .20 * scenario_shock))


def generate_value_data(n_properties: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    homes = []
    for i in range(n_properties):
        kind = str(rng.choice(PROPERTY_TYPES))
        area = float(rng.uniform(30, 300))
        region = str(rng.choice(REGIONS))
        value = float(np.clip(area * rng.uniform(1900, 4100) * (1.35 if region == "E12000007" else 1), 75000, 1500000))
        home = {"property_id": f"SYNTH-VALUE-{i:06d}", "data_kind": "synthetic_demo",
                "property_type": kind, "region": region, "floor_area_m2": area,
                "age_band": int(rng.integers(1, 6)), "epc_rating": str(rng.choice(list("ABCDEFG"))),
                "current_value_gbp": value, "heating": str(rng.choice(["gas_boiler", "heat_pump", "electric_resistance"], p=[.8, .1, .1])),
                "insulation": str(rng.choice(["poor", "partial", "good"])),
                "glazing": str(rng.choice(["single", "double", "triple"], p=[.55, .35, .1])),
                "solar_kwp": float(rng.choice([0, 0, 0, 3, 4])), "smart_controls": bool(rng.random() < .35),
                "roof_access": kind != "Flat", "listed_building": False, "consent_confirmed": False,
                "heat_pump_ready": True, "synthetic_market_shock": float(rng.normal())}
        homes.append(home)
    properties = assign_splits(pd.DataFrame(homes), seed + 1)
    rows = []
    for home in properties.to_dict("records"):
        feasible = []
        for retrofit in RETROFIT_IDS:
            try:
                if effective_retrofits(home, [retrofit]):
                    feasible.append(retrofit)
            except ValueError:
                pass
        # Split precedes expansion. Every home receives one no-op, each feasible
        # single measure, and unique interacting subsets (including full package).
        selections = {(), tuple(feasible)}
        selections.update((r,) for r in feasible)
        for _ in range(4):
            selections.add(tuple(r for r in feasible if rng.random() < .55))
        for scenario_index, selected in enumerate(sorted(selections)):
            x, active = value_features(home, list(selected))
            target = synthetic_reference(home, active, home["synthetic_market_shock"], float(rng.normal()))
            row = x.iloc[0].to_dict()
            row.update(property_id=home["property_id"], scenario_id=f'{home["property_id"]}-{scenario_index:02d}',
                       split=home["split"], data_kind="synthetic_hypothetical",
                       selected_retrofits="|".join(active), current_value_gbp=home["current_value_gbp"],
                       reference_before_gbp=home["current_value_gbp"],
                       reference_after_gbp=home["current_value_gbp"] * (1 + target / 100),
                       impact_percent=target, impact_gbp=home["current_value_gbp"] * target / 100)
            rows.append(row)
    return properties, pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=20000)
    parser.add_argument("--synthetic-properties", type=int, default=1800)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.sample_size < 100 or args.synthetic_properties < 100:
        parser.error("At least 100 properties are needed for each dataset.")
    (DATA / "raw").mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "requested_energy_sample": args.sample_size, "source_files": [],
                "energy_features": list(ENERGY_FEATURES), "fallback_reason": None}
    # Download failures may fall back; parse/schema/quality errors MUST fail, not
    # conceal a broken real-data pipeline by claiming a successful fallback.
    try:
        metadata_path = DATA / "raw" / "NEED-2026-anonymised-dataset-metadata.ods"
        manifest["source_files"].append(download(METADATA_URL, metadata_path))
    except (OSError, TimeoutError) as exc:
        manifest["fallback_reason"] = f"Official metadata download failed: {type(exc).__name__}: {exc}"
    if manifest["fallback_reason"] is None:
        metadata = parse_metadata(metadata_path)
        (DATA / "metadata_parsed.json").write_text(json.dumps(metadata, indent=2) + "\n")
        try:
            csv_path = DATA / "raw" / "anon2026_50k.csv"
            manifest["source_files"].append(download(DATA_URL, csv_path))
        except (OSError, TimeoutError) as exc:
            manifest["fallback_reason"] = f"Official CSV download failed: {type(exc).__name__}: {exc}"
    if manifest["fallback_reason"]:
        manifest["data_kind"] = "synthetic_fallback"
        energy = fallback_energy(args.sample_size, args.seed)
        manifest["quality"] = {"warning": "No observed-energy evaluation. All energy references synthetic."}
        print("WARNING:", manifest["fallback_reason"], flush=True)
    else:
        manifest["data_kind"] = "observed_NEED2026"
        energy, manifest["quality"] = observed_energy(pd.read_csv(csv_path, dtype=str))
    energy = assign_splits(energy, args.seed, args.sample_size)
    energy.to_csv(DATA / "energy_properties.csv", index=False)
    energy[["property_id", "split", "model_sample"]].to_csv(DATA / "energy_splits.csv", index=False)
    properties, scenarios = generate_value_data(args.synthetic_properties, args.seed + 100)
    properties.to_csv(DATA / "synthetic_value_properties.csv", index=False)
    scenarios.to_csv(DATA / "synthetic_value_scenarios.csv", index=False)
    manifest.update(energy_rows=len(energy), energy_sample_rows=int(energy.model_sample.sum()),
                    energy_split_counts=energy.split.value_counts().to_dict(),
                    energy_sample_split_counts=energy.loc[energy.model_sample, "split"].value_counts().to_dict(),
                    synthetic_value_properties=len(properties), synthetic_value_scenarios=len(scenarios),
                    synthetic_value_property_splits=properties.split.value_counts().to_dict(),
                    synthetic_value_scenario_splits=scenarios.split.value_counts().to_dict(),
                    target_year=2024, acceptable_quality_flags=["V"],
                    property_id_policy="Stable 1-based source row ID within the hash-pinned official snapshot; each row represents a property. No source identifiers supplied.",
                    split_policy="Seeded property-ID permutation; 60/20/20 before scenario expansion; sampling independent of target/flags.",
                    leakage_exclusions=["All consumption/quality columns as features", "MAIN_HEAT_FUEL (uses 2022-2024 gas)",
                                        "Installation flags/dates (can post-date target)", "2025 deprivation/tax bands", "IDs and synthetic references"],
                    temporal_caveat="Most recent EPC has no lodgement date; October 2025 property snapshot. Retrospective cohort benchmark only, not a time-safe 2024 forecast.",
                    files={p.name: sha256(p) for p in DATA.glob("*.csv")})
    (DATA / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("data_kind", "energy_rows", "energy_sample_rows",
                                               "energy_sample_split_counts", "synthetic_value_properties", "synthetic_value_scenarios")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
