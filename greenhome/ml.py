"""Local trained inference: observed energy associations and synthetic value ranges.

Only load the trusted, locally trained artifacts in models/. Value predictions are
not valuations, sales evidence, or causal estimates. No API/network calls are made.
"""
from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
SEED = 42
PROPERTY_TYPES = ("Detached", "Semi detached", "Mid terrace", "End terrace", "Bungalow", "Flat")
REGIONS = tuple(f"E1200000{i}" for i in range(1, 10)) + ("W92000004",)
RETROFIT_IDS = ("loft_insulation", "double_glazing", "smart_controls", "heat_pump", "solar_pv")
# MAIN_HEAT_FUEL is deliberately NOT a feature: metadata says it uses Gcons2024.
ENERGY_FEATURES = ("PROP_TYPE", "PROP_AGE_BAND", "FLOOR_AREA_BAND", "REGION", "EPC")
VALUE_CATEGORICAL = ("property_type", "region", "heating", "insulation", "glazing")
VALUE_NUMERIC = (
    "floor_area_m2", "age_band", "epc_deficit", "log_current_value",
    "solar_kwp", "has_controls", *RETROFIT_IDS,
)
EPC_DEFICIT = {"A": 0, "B": 1, "A/B": .5, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6}
SYNTHETIC_NOTE = (
    "Synthetic hypothetical paired-home model, NOT market-calibrated. "
    "Range is learned from invented references, not historical sales, a causal "
    "retrofit premium, a valuation or a guarantee; negative impacts are possible."
)


def finite_number(value) -> bool:
    if not isinstance(value, (int, float, np.number)) or isinstance(value, (bool, np.bool_)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def floor_area_band(area: float) -> str:
    if not finite_number(area) or area <= 0:
        raise ValueError("A finite positive floor area is required.")
    return str(1 + sum(float(area) > boundary for boundary in (50, 100, 150, 200)))


def energy_features(home: dict) -> pd.DataFrame:
    if home.get("property_type") not in PROPERTY_TYPES or home.get("region") not in REGIONS:
        raise ValueError("Known England/Wales region and supported property type are required.")
    age = home.get("age_band")
    if not finite_number(age) or age not in (1, 2, 3, 4):
        raise ValueError("NEED age band 1..4 is required; synthetic age band 5 has no verified mapping.")
    epc = home.get("epc_rating")
    mapping = {None: "No EPC", "No EPC": "No EPC", "A": "A/B", "B": "A/B",
               "A/B": "A/B", "C": "C", "D": "D", "E": "E", "F": "F/G", "G": "F/G", "F/G": "F/G"}
    if epc not in mapping:
        raise ValueError("Unsupported EPC rating.")
    row = {"PROP_TYPE": home["property_type"], "PROP_AGE_BAND": str(int(age)),
           "FLOOR_AREA_BAND": floor_area_band(home.get("floor_area_m2")),
           "REGION": home["region"], "EPC": mapping[epc]}
    return pd.DataFrame([row], columns=ENERGY_FEATURES)


@lru_cache(maxsize=8)
def _read_artifact(path: str, modified_ns: int):
    # The mtime cache key permits a newly trained artifact to replace an old one.
    bundle = joblib.load(path)
    if Path(path).name == "energy_benchmark.joblib":
        for pipeline in bundle["models"].values():
            # TTR predicts with its fitted clone, not the constructor template.
            # Configure before caching/sharing: small service requests should not
            # spawn nested joblib workers (or propagate config into those workers).
            # This changes execution only; fitted trees and disk artifacts stay intact.
            pipeline.named_steps["model"].regressor_.n_jobs = 1
    return bundle


def load_artifact(name: str):
    path = MODEL_DIR / name
    return _read_artifact(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=2048)
def _cohort_prediction(pipeline, features: tuple) -> float:
    """Cache only five coarse public cohort features, never a customer or bill.

    Pipeline identity changes when the artifact loader detects a replacement.
    The frozen fitted model owns the value; no score or numerical rule changes.
    """
    frame = pd.DataFrame([features], columns=ENERGY_FEATURES)
    return float(pipeline.predict(frame)[0])


def predict_energy_benchmark(home: dict) -> dict | None:
    """A cohort benchmark only; never fills a missing metered baseline."""
    result = {"electricity_kwh": None, "gas_kwh": None, "note": "", "status": "unavailable"}
    try:
        x = energy_features(home)
        bundle = load_artifact("energy_benchmark.joblib")
        synthetic = bundle["data_kind"] != "observed_NEED2026"
        if synthetic and home.get("data_kind") != "synthetic_demo":
            result["note"] = "Only a synthetic fallback was trained; abstaining for non-demo homes."
            return result
        features = tuple(x.iloc[0][key] for key in ENERGY_FEATURES)
        result["electricity_kwh"] = round(_cohort_prediction(bundle["models"]["electricity"], features), 1)
        # No gas grid match is NOT a zero observed gas target. The gas fit is
        # conditional on a valid gas observation, so do not apply it to electric heat.
        if home.get("heating") == "gas_boiler":
            result["gas_kwh"] = round(_cohort_prediction(bundle["models"]["gas"], features), 1)
        result["status"] = "synthetic_fallback" if synthetic else (
            "observed_benchmark" if result["gas_kwh"] is not None else "partial_observed_benchmark"
        )
        result["note"] = (
            ("SYNTHETIC FALLBACK, not observed data. " if synthetic else "Trained on valid observed NEED 2024 consumption. ")
            + "Structural cohort association, not a personal forecast or retrofit savings model. "
            "Electricity and weather-corrected gas have different annual reporting periods. "
            "Latest EPC and property snapshot may post-date 2024; not a prospective forecast. "
            "MAIN_HEAT_FUEL excluded because it incorporates target-year gas usage. "
            "Age bands must follow NEED's 1..4 definitions."
        )
        if result["gas_kwh"] is None:
            result["note"] += " Gas benchmark withheld for electric/unknown heating; missing gas is not zero."
    except (ValueError, TypeError, KeyError, OSError, EOFError, ImportError) as exc:
        result["electricity_kwh"] = result["gas_kwh"] = None
        result["note"] = f"Energy benchmark unavailable: {type(exc).__name__}: {exc}"
    return result


def effective_retrofits(home: dict, selected: list[str]) -> tuple[str, ...]:
    if not isinstance(selected, (list, tuple)) or any(not isinstance(r, str) or r not in RETROFIT_IDS for r in selected):
        raise ValueError("Unknown retrofit; only the five contract identifiers are supported.")
    active = []
    for retrofit in RETROFIT_IDS:
        if retrofit not in selected:
            continue
        if retrofit == "loft_insulation" and home.get("insulation") == "good":
            continue
        if retrofit == "double_glazing" and home.get("glazing") in ("double", "triple"):
            continue
        if retrofit == "smart_controls" and home.get("smart_controls") is True:
            continue
        if retrofit == "heat_pump" and home.get("heating") == "heat_pump":
            continue
        if retrofit == "solar_pv" and finite_number(home.get("solar_kwp")) and home["solar_kwp"] > 0:
            continue
        if retrofit in ("loft_insulation", "solar_pv") and home.get("roof_access") is not True:
            raise ValueError("Roof access is absent or unknown.")
        if retrofit == "heat_pump" and (home.get("heating") != "gas_boiler" or home.get("heat_pump_ready") is not True):
            raise ValueError("Gas-to-heat-pump installation readiness is not confirmed.")
        if retrofit != "smart_controls" and home.get("listed_building") is not False and home.get("consent_confirmed") is not True:
            raise ValueError("Required building consent is not confirmed.")
        active.append(retrofit)
    return tuple(active)


def value_features(home: dict, selected: list[str]) -> tuple[pd.DataFrame, tuple[str, ...]]:
    if home.get("property_type") not in PROPERTY_TYPES or home.get("region") not in REGIONS:
        raise ValueError("Known supported property type and England/Wales region are required.")
    for field, low, high in (("floor_area_m2", 30, 300), ("current_value_gbp", 75000, 1500000),
                             ("solar_kwp", 0, 12), ("age_band", 1, 5)):
        value = home.get(field)
        if not finite_number(value) or not low <= value <= high:
            raise ValueError(f"{field} is missing or outside the synthetic training envelope [{low}, {high}].")
    if home["age_band"] != int(home["age_band"]):
        raise ValueError("Age band must be an integer.")
    if home.get("epc_rating") not in EPC_DEFICIT:
        raise ValueError("A known EPC rating is required.")
    if home.get("heating") not in ("gas_boiler", "heat_pump", "electric_resistance"):
        raise ValueError("Heating is unknown.")
    if home.get("insulation") not in ("poor", "partial", "good") or home.get("glazing") not in ("single", "double", "triple"):
        raise ValueError("Insulation/glazing is unknown.")
    if not isinstance(home.get("smart_controls"), bool):
        raise ValueError("Smart-controls status is unknown.")
    active = effective_retrofits(home, selected)
    row = {field: home[field] for field in VALUE_CATEGORICAL}
    row.update(floor_area_m2=float(home["floor_area_m2"]), age_band=int(home["age_band"]),
               epc_deficit=EPC_DEFICIT[home["epc_rating"]],
               log_current_value=math.log(float(home["current_value_gbp"])),
               solar_kwp=float(home["solar_kwp"]), has_controls=int(home["smart_controls"]))
    row.update({retrofit: int(retrofit in active) for retrofit in RETROFIT_IDS})
    return pd.DataFrame([row], columns=(*VALUE_CATEGORICAL, *VALUE_NUMERIC)), active


def value_quantile_predictions(bundle: dict, x: pd.DataFrame) -> np.ndarray:
    predictions = np.column_stack([bundle["models"][q].predict(x) for q in ("p10", "p50", "p90")])
    # Quantile fits can cross: monotonically rearrange, then enforce the paired
    # no-intervention identity exactly rather than learning a spurious intercept.
    predictions.sort(axis=1)
    predictions[x[list(RETROFIT_IDS)].sum(axis=1).to_numpy() == 0] = 0.0
    return predictions


def predict_value_impact(home: dict, selected_retrofits: list[str]) -> dict:
    """Return GBP change, not post-retrofit sale price; demos only."""
    result = {"status": "abstained", "low_gbp": None, "high_gbp": None,
              "low_percent": None, "high_percent": None, "note": SYNTHETIC_NOTE}
    # A no-intervention identity is arithmetic, not a market valuation.
    if isinstance(selected_retrofits, (list, tuple)) and not selected_retrofits:
        result.update(status="no_change", low_gbp=0.0, high_gbp=0.0, low_percent=0.0, high_percent=0.0,
                      note="No retrofit: paired baseline and after are identical; exact zero. " + SYNTHETIC_NOTE)
        return result
    if home.get("data_kind") != "synthetic_demo":
        result["note"] += " Abstained: only explicitly synthetic_demo homes are supported."
        return result
    try:
        x, active = value_features(home, selected_retrofits)
        if not active:
            result.update(status="no_change", low_gbp=0.0, high_gbp=0.0, low_percent=0.0, high_percent=0.0)
            result["note"] += " Already-installed measures leave the paired baseline unchanged: exact zero."
            return result
        bundle = load_artifact("synthetic_value.joblib")
        low, _, high = value_quantile_predictions(bundle, x)[0]
        current_value = float(home["current_value_gbp"])
        result.update(status="synthetic_illustration",
                      low_gbp=round(float(low) * current_value / 100, 2),
                      high_gbp=round(float(high) * current_value / 100, 2),
                      low_percent=round(float(low), 4), high_percent=round(float(high), 4))
        result["note"] += " Learned p10-p90 interval, validated only against synthetic references; fixed market scenario."
    except (ValueError, TypeError, KeyError, OSError, EOFError, ImportError) as exc:
        result["note"] += f" Abstained: {type(exc).__name__}: {exc}"
    return result
