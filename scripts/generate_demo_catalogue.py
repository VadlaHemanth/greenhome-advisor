"""Author a fixed demo-only catalogue independently; never read training data."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from greenhome import engine
from greenhome.demo_catalogue import (
    COUNT, GENERATOR_VERSION, REGIONS, SEED, VERSION,
    distribution_for, load_catalogue, record_sha256, summary_for,
)
from greenhome.ranking import POLICY, WARNINGS, assign_global_ranks, rank_homes

# Authored coverage targets, NOT measured housing-stock proportions.
TYPE_QUOTAS = {
    "Detached": 30, "Semi detached": 40, "Mid terrace": 36,
    "End terrace": 24, "Bungalow": 30, "Flat": 40,
}
AREA_RANGES = {
    "Detached": (90, 280), "Semi detached": (65, 220), "Mid terrace": (55, 180),
    "End terrace": (55, 180), "Bungalow": (55, 180), "Flat": (30, 120),
}
EXPOSURE = {
    "Detached": 1.20, "Semi detached": 1.05, "Mid terrace": 0.85,
    "End terrace": 1.00, "Bungalow": 1.15, "Flat": 0.75,
}
CONFIRMED_GAS = {
    "heating": "gas_boiler", "solar_kwp": 0.0, "listed_building": False,
    "consent_confirmed": False, "roof_access": True, "heat_pump_ready": True,
    "insulation": "poor", "glazing": "single", "smart_controls": False,
}
CONTROLS_ONLY = {
    **CONFIRMED_GAS, "insulation": "good", "glazing": "double",
    "roof_access": False, "heat_pump_ready": False,
}
# Twenty authored edge cases. Fields withheld AFTER generation remain null,
# rather than being inferred by the serving path from latent generation facts.
EDGES = {
    181: ("Semi detached", "Missing score evidence", {
        **CONFIRMED_GAS, "floor_area_m2": None, "epc_rating": None, "budget_gbp": None,
    }, "Area and EPC deliberately withheld: score is unknown; known fuel opportunity can still rank."),
    182: ("End terrace", "Missing electricity total", {
        **CONFIRMED_GAS, "electricity_kwh": None,
    }, "Annual grid imports deliberately missing, not zero; no total-energy ranking."),
    183: ("Bungalow", "Missing gas total", {
        **CONFIRMED_GAS, "gas_kwh": None,
    }, "Annual gas deliberately missing, not a confirmed gas-free home."),
    184: ("Detached", "Unknown heating and fabric", {
        "heating": "unknown", "insulation": "unknown", "glazing": "unknown",
        "solar_kwp": 0.0, "budget_gbp": None,
    }, "Heating and fabric are unconfirmed, not default gas or installed efficiency."),
    185: ("Flat", "Unrecorded equipment and permissions", {
        "heating": None, "insulation": None, "glazing": None, "solar_kwp": None,
        "smart_controls": None, "roof_access": None, "listed_building": None,
        "consent_confirmed": None, "heat_pump_ready": None, "current_value_gbp": None,
        "budget_gbp": 0.0,
    }, "Null equipment, value and permissions remain unknown, even with a zero budget."),
    186: ("Mid terrace", "Confirmed zero purchased energy", {
        **CONFIRMED_GAS, "electricity_kwh": 0.0, "gas_kwh": 0.0,
    }, "Authored zero-meter boundary, not typical occupied use: percentage denominator is unavailable."),
    187: ("Semi detached", "Zero planning budget", {
        **CONTROLS_ONLY, "budget_gbp": 0.0,
    }, "Known gas demand but no upper-cost installation fits the confirmed £0 planning cap."),
    188: ("Bungalow", "Just below controls upper cost", {
        **CONTROLS_ONLY, "budget_gbp": 349.0,
    }, "£349 is below the existing engine's £350 controls upper-cost boundary."),
    189: ("End terrace", "At controls upper cost", {
        **CONTROLS_ONLY, "budget_gbp": 350.0,
    }, "£350 exactly admits controls under the existing engine's upper-cost budget policy."),
    190: ("Detached", "Listed consent withheld", {
        **CONFIRMED_GAS, "age_band": 1, "listed_building": True,
        "consent_confirmed": False, "budget_gbp": None,
    }, "Listed-building installation consent is explicitly unconfirmed; money is not permission."),
    191: ("Mid terrace", "Listed consent confirmed", {
        **CONFIRMED_GAS, "age_band": 1, "listed_building": True,
        "consent_confirmed": True, "budget_gbp": None,
    }, "Relevant installation consent is explicitly confirmed for this fictional listed example."),
    192: ("Bungalow", "Roof rights and readiness unknown", {
        **CONFIRMED_GAS, "roof_access": None, "heat_pump_ready": None, "budget_gbp": None,
    }, "A bungalow does not establish roof rights or installer readiness automatically."),
    193: ("Flat", "Flat with confirmed roof rights", {
        **CONFIRMED_GAS, "heat_pump_ready": False, "budget_gbp": 9000.0,
    }, "Explicit fictional private roof permission; not inferred from the Flat property type."),
    194: ("Semi detached", "Already improved no-action home", {
        "heating": "heat_pump", "insulation": "good", "glazing": "triple",
        "smart_controls": True, "solar_kwp": 0.0, "roof_access": False,
        "listed_building": False, "heat_pump_ready": True, "budget_gbp": None,
    }, "No relevant supported measure remains; absent roof rights exclude new PV. Known no-op is zero."),
    195: ("Flat", "Electric heating with existing PV", {
        "heating": "electric_resistance", "solar_kwp": 2.5, "roof_access": True,
        "listed_building": False, "insulation": "partial", "glazing": "double",
        "smart_controls": False, "budget_gbp": None,
    }, "Existing PV already reduces grid imports; electrical-demand changes need unsupported behind-the-meter evidence."),
    196: ("Detached", "Outside frozen inference envelope", {
        **CONFIRMED_GAS, "floor_area_m2": 340.0, "current_value_gbp": 1600000.0,
        "age_band": 5, "budget_gbp": None,
    }, "Deliberate age-5 energy-benchmark and area/value-envelope abstention inputs; not a model-calibrated case."),
    197: ("Mid terrace", "All improvements deferred", {
        **CONFIRMED_GAS, "excluded_retrofits": list(engine.RETROFITS), "budget_gbp": None,
    }, "All five supported measures explicitly deferred; exclusions do not change installed features."),
    198: ("Bungalow", "Installer readiness absent", {
        **CONFIRMED_GAS, "heat_pump_ready": False, "budget_gbp": None,
    }, "Installer readiness is confirmed false, not unknown; only other permitted measures compete."),
    199: ("End terrace", "Unknown value and unconstrained budget", {
        **CONFIRMED_GAS, "current_value_gbp": None, "budget_gbp": None,
    }, "Missing value remains unknown; missing budget means no affordability constraint, not a £0 cap."),
    200: ("Flat", "Gas-free resistance heating", {
        "heating": "electric_resistance", "solar_kwp": 0.0, "roof_access": False,
        "listed_building": False, "insulation": "poor", "glazing": "single",
        "smart_controls": False, "heat_pump_ready": False, "budget_gbp": 2000.0,
        "solar_self_consumption_fraction": 0.0,
    }, "Confirmed gas-free electric heating: gas is exactly zero; no gas-to-heat-pump conversion is modelled."),
}

ASSUMPTIONS = {
    "authorship": "Original project-authored fictional rules; not fitted to observations or copied rows.",
    "coverage": "Four unchanged legacy + 176 varied + 20 deliberate edge cases; quotas are not prevalence.",
    "randomness": "Per-ID Python Random string seed: generator_version:seed:property_id. No clock input.",
    "area_ranges_m2": AREA_RANGES,
    "type_exposure": EXPOSURE,
    "age_probabilities_1_to_4": [0.20, 0.32, 0.28, 0.20],
    "insulation_poor_partial_good_by_age": {
        "1": [0.45, 0.40, 0.15], "2": [0.30, 0.45, 0.25],
        "3": [0.15, 0.45, 0.40], "4": [0.05, 0.25, 0.70],
    },
    "heat": "Space useful kWh = area * fabric intensity (poor150/partial100/good60) * exposure * glazing (single1.12/double1/triple0.92) * age (1:1.08/2:1.04/3:1/4:0.96) * uniform(0.8,1.2). Hot water = space*(1-space_fraction)/space_fraction; total useful heat is divided by boiler efficiency, SPF or resistance efficiency1.",
    "electricity": "Non-heating kWh=(900+550*occupants+4*area)*uniform(0.85,1.15). Occupants are latent fictional 1..min(5,max(1,floor(area/25))). Add electric heating demand where applicable.",
    "space_heat_fraction": "Gas uses0.8. For new electric homes, divide useful space heat by heating efficiency and rounded gross electricity (including appliances and hot water); round the fraction to8decimals. Existing PV uses the pre-PV denominator, not imports; electrical-demand retrofit effects remain unsupported. Legacy fractions unchanged.",
    "pv": "Grid imports=max(0,gross electricity - min(gross electricity,kWp*yield*self_consumption)); subtract once. Round annual fuels to nearest10kWh. Confirmed gas-free heating has gas0; missing meters are masked, never filled.",
    "epc": "Invented noisy ordinal label from fabric/glazing/heating/solar, not an EPC calculation or certificate. See docs/DEMO_CATALOGUE.md.",
    "value": "Fictional GBP=round((65000+1850*area)*(0.85+0.03*region_index)*uniform(0.85,1.15),-3), clipped75000..1500000. Index is a coverage ordering, not an estimated regional market gradient.",
    "permissions": "Ordinary flats have no private roof access; other homes draw explicit permission (92%). Listed chance20% for age1; consent draw65%. Gas readiness draw80%. These draws are authored facts, not installation inference.",
    "budget": "Independent choice None/1000/2000/7500/16000/24000GBP; constraints and boundary cases are intentionally overrepresented.",
    "masking": "Null/unknown edge facts withheld after constructing the fictional baseline; retained latent traces are generation assumptions, never inference inputs for filling unknowns.",
    "units": {"area": "m²", "energy": "annual kWh", "solar": "kWp", "money": "GBP"},
    "engine_assumptions": engine.DEFAULT_ASSUMPTIONS,
    "limitations": "No empirical calibration, representative sampling, new accuracy evidence, real addresses, monthly histories, tariff assumptions or market premiums.",
}


def _allocate(quotas: dict, reserved: list) -> list:
    remaining = Counter(quotas)
    remaining.subtract(reserved)
    result = []
    while any(value > 0 for value in remaining.values()):
        for key in quotas:
            if remaining[key] > 0:
                result.append(key)
                remaining[key] -= 1
    if any(value < 0 for value in remaining.values()):
        raise ValueError("Reserved examples exceed authored quotas.")
    return result


def _home(number: int, property_type: str, region: str, overrides: dict) -> tuple[dict, dict]:
    identity = f"DEMO-{number:02d}"
    rng = random.Random(f"{GENERATOR_VERSION}:{SEED}:{identity}")
    area = float(rng.randint(*AREA_RANGES[property_type]))
    age = rng.choices((1, 2, 3, 4), (0.20, 0.32, 0.28, 0.20))[0]
    insulation = rng.choices(
        ("poor", "partial", "good"),
        ASSUMPTIONS["insulation_poor_partial_good_by_age"][str(age)],
    )[0]
    glazing = rng.choices(
        ("single", "double", "triple"),
        (0.05, 0.70, 0.25) if insulation == "good" else
        ((0.55, 0.43, 0.02) if age <= 2 else (0.20, 0.70, 0.10)),
    )[0]
    heating = rng.choices(
        ("gas_boiler", "heat_pump", "electric_resistance"),
        (0.55, 0.35, 0.10) if insulation == "good" else (0.82, 0.08, 0.10),
    )[0]
    roof = property_type != "Flat" and rng.random() < 0.92
    listed = age == 1 and rng.random() < 0.20
    home = {
        "property_id": identity, "property_type": property_type, "region": region,
        "age_band": age, "floor_area_m2": area, "heating": heating,
        "insulation": insulation, "glazing": glazing,
        "solar_kwp": rng.choice((2.0, 3.0, 4.0)) if roof and rng.random() < 0.18 else 0.0,
        "smart_controls": rng.random() < (0.85 if heating == "heat_pump" else 0.45),
        "roof_access": roof, "listed_building": listed,
        "consent_confirmed": listed and rng.random() < 0.65,
        "heat_pump_ready": rng.random() < 0.80,
        "budget_gbp": rng.choice((None, 1000.0, 2000.0, 7500.0, 16000.0, 24000.0)),
        "data_kind": "synthetic_demo", "excluded_retrofits": [],
        **engine.DEFAULT_ASSUMPTIONS,
    }
    # Derive demand from known edge-specific equipment/structure, then withhold
    # deliberately unknown fields. Explicit meter boundary overrides come last.
    home.update({key: value for key, value in overrides.items()
                 if value is not None and value != "unknown"
                 and key not in {"electricity_kwh", "gas_kwh"}})
    area = home["floor_area_m2"]
    occupants = rng.randint(1, min(5, max(1, int(area // 25))))
    space = (
        area * {"poor": 150, "partial": 100, "good": 60}[home["insulation"]]
        * EXPOSURE[property_type] * {"single": 1.12, "double": 1, "triple": 0.92}[home["glazing"]]
        * {1: 1.08, 2: 1.04, 3: 1.00, 4: 0.96}[min(home["age_band"], 4)]
        * rng.uniform(0.8, 1.2)
    )
    water = space * (1 - home["space_heat_fraction"]) / home["space_heat_fraction"]
    useful_heat = space + water
    base_electricity = (900 + 550 * occupants + 4 * area) * rng.uniform(0.85, 1.15)
    gas = useful_heat / home["boiler_efficiency"] if home["heating"] == "gas_boiler" else 0.0
    electric_heat = (
        useful_heat / home["heat_pump_spf"] if home["heating"] == "heat_pump" else
        useful_heat if home["heating"] == "electric_resistance" else 0.0
    )
    gross_electricity = base_electricity + electric_heat
    self_used = min(gross_electricity, home["solar_kwp"] * home["solar_yield_kwh_per_kwp"]
                    * home["solar_self_consumption_fraction"])
    home["electricity_kwh"] = float(round(max(0, gross_electricity - self_used), -1))
    home["gas_kwh"] = float(round(gas, -1))
    if home["heating"] in ("heat_pump", "electric_resistance"):
        efficiency = home["heat_pump_spf"] if home["heating"] == "heat_pump" else 1.0
        home["space_heat_fraction"] = round(
            (space / efficiency) / round(gross_electricity, -1), 8
        )
    epc_points = (
        {"poor": 0, "partial": 1, "good": 3}[home["insulation"]]
        + {"single": 0, "double": 1, "triple": 2}[home["glazing"]]
        + {"gas_boiler": 1, "heat_pump": 2, "electric_resistance": 0}[home["heating"]]
        + int(home["solar_kwp"] > 0) + rng.choice((-1, 0, 0, 0, 1))
    )
    home["epc_rating"] = "GFEDCBA"[max(0, min(6, epc_points))]
    home["current_value_gbp"] = float(max(75000, min(1500000, round(
        (65000 + area * 1850) * (0.85 + 0.03 * REGIONS.index(region)) * rng.uniform(0.85, 1.15), -3
    ))))
    home.update(overrides)
    trace = {
        "latent_occupants": occupants, "useful_space_heat_kwh": round(space, 3),
        "useful_hot_water_kwh": round(water, 3), "non_heating_electricity_kwh": round(base_electricity, 3),
        "gross_electricity_kwh": round(gross_electricity, 3), "self_used_pv_kwh": round(self_used, 3),
        "gross_gas_kwh": round(gas, 3), "explicit_overrides": overrides,
    }
    return home, trace


def build_catalogue() -> tuple[dict, dict]:
    legacy = engine.demo_homes()
    types = _allocate(TYPE_QUOTAS, [h["property_type"] for h in legacy]
                      + [case[0] for case in EDGES.values()])
    edge_regions = {number: REGIONS[(number - 5) % len(REGIONS)] for number in EDGES}
    regions = _allocate({region: 20 for region in REGIONS},
                        [h["region"] for h in legacy] + list(edge_regions.values()))
    entries = [{
        "home": home, "label": f"{home['property_id']} · Familiar {home['property_type'].lower()}",
        "kind": "legacy",
        "notes": ["Unchanged original fictional demonstration; not an observed home or training row."],
    } for home in legacy]
    traces = {}
    for number in range(5, COUNT + 1):
        if number in EDGES:
            property_type, label, overrides, note = EDGES[number]
            region, kind = edge_regions[number], "edge_case"
        else:
            property_type, region = types[number - 5], regions[number - 5]
            label, overrides, kind = f"Fictional {property_type.lower()}", {}, "generated"
            note = "Independent authored example; annual fuels, EPC and baseline value are synthetic, not measured."
        home, trace = _home(number, property_type, region, overrides)
        traces[home["property_id"]] = trace
        entries.append({
            "home": home, "label": f"{home['property_id']} · {label}",
            "kind": kind, "notes": [note],
        })
    rows = []
    for start in range(0, COUNT, 100):
        rows.extend(rank_homes([entry["home"] for entry in entries[start:start + 100]])["rows"])
    # Local batch numbering is explicitly overwritten for all 200 together.
    by_id = {entry["home"]["property_id"]: entry for entry in entries}
    entries = [{**by_id[row["property_id"]], "ranking": row} for row in assign_global_ranks(rows)]
    payload = {"version": VERSION, "entries": entries, "policy": POLICY}
    manifest = {
        "schema_version": 1, "version": VERSION, "generator_version": GENERATOR_VERSION,
        "seed": SEED, "count": COUNT, "purpose": "demo_only",
        "label": "200 fictional England/Wales examples; not observed homes or training data.",
        "synthetic": True, "training_use": False,
        "schema": {"home": "Existing HomeInput, synthetic_demo only; original four unchanged.",
                   "entry": ["home", "label", "kind", "notes", "ranking"],
                   "ranking": "Existing RankedHome with globally assigned competition ranks."},
        "record_sha256": {entry["home"]["property_id"]: record_sha256(entry["home"]) for entry in entries},
        "calculation_source_sha256": {
            name: hashlib.sha256((ROOT / "greenhome" / name).read_bytes()).hexdigest()
            for name in ("engine.py", "ranking.py")
        },
        "distribution": distribution_for(entries), "summary": summary_for(entries),
        "assumptions": ASSUMPTIONS, "generation_trace": traces, "ranking_warnings": list(WARNINGS),
        "data_reuse_notice": "Project-authored fictional demonstration inputs. Reuse with attribution to GreenHome Advisor and retain synthetic/demo-only/no-training and non-calibration disclosures. No third-party row rights are asserted.",
    }
    return payload, manifest


def _pretty(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_catalogue(output_dir: Path = ROOT / "data") -> dict:
    """Write only the two catalogue files, reproducibly, with no timestamp."""
    payload, manifest = build_catalogue()
    raw = _pretty(payload)
    manifest["sha256"] = hashlib.sha256(raw).hexdigest()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path, manifest_path = output_dir / "demo_catalogue.json", output_dir / "demo_catalogue_manifest.json"
    data_path.write_bytes(raw)
    manifest_path.write_bytes(_pretty(manifest))
    # Fail the build rather than serving invalid schema/ranks/provenance.
    load_catalogue(data_path, manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    result = write_catalogue(args.output_dir)
    print(json.dumps({"count": result["count"], "sha256": result["sha256"],
                      "summary": result["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
