# Integration contract

UK / England and Wales pilot. All monetary quantities GBP. No app/test outcome may be fabricated.

## Public portfolio release metadata

`GET /api/release` returns `name`, `version`, `revision` (a validated lowercase
40-character Git SHA or null), and `environment` (`local` or `hosted`). It
never returns credentials or arbitrary environment values. A missing revision
is explicitly unknown. `/api/readiness` remains the separate asset/model
readiness check; a version identifier does not prove deployment success.

## Engine interface owned by lead

`greenhome.engine` exports:

- `demo_homes() -> list[dict]`
- `assess(home: dict, selected_retrofits: list[str] | None = None) -> dict`
- `RETROFITS: dict[str, dict]` catalogue keyed by `loft_insulation`, `double_glazing`, `smart_controls`, `heat_pump`, `solar_pv`.
- `validate_home(home: dict) -> list[str]` validation errors; `assess` raises ValueError for invalid inputs.

Home keys:

`property_id`, `property_type` (Detached, Semi detached, Mid terrace, End terrace, Bungalow, Flat),
`age_band` (int 1..5, synthetic mapping; real mapping per dataset metadata),
`region` (NEED region code, default E12000007),
`floor_area_m2` (positive float or None), `epc_rating` (A..G, A/B or None),
`electricity_kwh` (annual grid imports, nonnegative float or None),
`gas_kwh` (annual gas input on gross CV basis, nonnegative float or None),
`heating` (gas_boiler, heat_pump, electric_resistance, unknown),
`insulation` (poor, partial, good, unknown), `glazing` (single, double, triple, unknown),
`solar_kwp` (nonnegative float), `smart_controls` (bool),
`roof_access` (bool or None), `listed_building` (bool), `consent_confirmed` (bool),
`heat_pump_ready` (bool or None), `space_heat_fraction` (0..1), `boiler_efficiency` (0..1 gross CV),
`heat_pump_spf` (1..6), `solar_yield_kwh_per_kwp` (positive float), `solar_self_consumption_fraction` (0..1),
`current_value_gbp` (positive float or None), `budget_gbp` (nonnegative float or None),
`data_kind` (synthetic_demo, user_entered).

`assess` output:

```
{
  "home": {...},
  "score": {"total": int|None, "classification": str, "components": [{"name": str, "weight": float, "score": float|None, "contribution": float|None}], "issues": [str]},
  "baseline": {"electricity_kwh": float|None, "gas_kwh": float|None, "purchased_kwh": float|None},
  "recommendations": [{"id": str, "name": str, "feasible": bool, "suitability": str, "reason": str, "cost_gbp": [low,high], "standalone": scenario_dict|None}],
  "selected_retrofits": [str],
  "scenario": {
     "electricity_kwh": float|None, "gas_kwh": float|None,
     "electricity_saving_kwh": float|None, "gas_saving_kwh": float|None,
     "net_saving_kwh": float|None, "improvement_percent": float|None,
     "carbon_reduction_kgco2e": float|None, "cost_gbp": [low,high],
     "warnings": [str], "assumptions": [str]
  },
  "value_impact": {"status": str, "low_gbp": float|None, "high_gbp": float|None, "low_percent": float|None, "high_percent": float|None, "note": str},
  "energy_benchmark": dict|None,
  "warnings": [str],
  "sources": [{"label": str, "url": str}]
}
```

Engine must not import the UI or LLM. Trained model module imported lazily, failure exposed with a warning rather than concealed.

## ML interface owned by training agent

`greenhome.ml` exports:
- `predict_energy_benchmark(home: dict) -> dict|None` with `electricity_kwh`, `gas_kwh`, `note`, `status`.
- `predict_value_impact(home: dict, selected_retrofits: list[str]) -> dict` with the value-impact schema above. Model trained on disclosed synthetic references; never imply causal UK premium.

Training commands: `.venv/bin/python scripts/prepare_data.py` then `.venv/bin/python scripts/train_models.py`.

Write machine-readable actual results to `reports/training_metrics.json`, fixed test predictions to `reports/test_predictions.csv`, models to `models/`. Document provenance, quality flags, samples and splits.

## UI and Gemini owned by app agent

The final frontend is React. **UI development is now authorized using the supplied dashboard-board reference.**
The earlier Streamlit prototype is retained only as a superseded exploratory demo; do not extend or treat it as the chosen frontend.

`greenhome/api.py` exposes JSON endpoints for the implemented React frontend.
Own-home screening and conversations remain temporary. Explicitly opted-in
fictional workspaces persist scoped home facts, preferences, selected plans and
confirmed completion history; see `docs/WORKSPACE_MEMORY.md`. They are not real
customer records or bank identities. The provider-attempt counter is separate.
`greenhome/explain.py` exposes explicit live/fallback status. Recompute via the
engine BEFORE explanation; keys remain server-side. `docs/FINAL_BUILD_CONTRACT.md`
and `docs/PROPERTY_RANKING.md` cover additive fields and the ranking API.

The integrated release uses an explicit active provider (`gemini` or `xkiro`).
Health adds `llm_*` metadata; historical `gemini_configured` and `use_gemini`
remain backward-compatible API field names. Successful Xkiro explanations use
`live_llm`, never a misleading Gemini label. See `docs/ACTIVE_LLM.md`.
`POST /api/energy-inputs` returns an in-memory checked rolling-year preview from
monthly CSV; it neither modifies a home nor stores uploaded rows. Unknowns
remain null. Explicit user application of the preview is required.

No stale scenario outputs: if a home or selection changes, recompute. New home must not inherit previous home's incompatible controls.

## Customer/property ownership — schema 2

Canonical saved state is workspace → customers → properties. Each property owns
its home facts, bills, permissions, active-plan budget, local deferrals, selection,
baseline status and completion events. Customer-wide preferences and shared
planning cap are separate. New paths name both customer and property, and writes
require both versions. Legacy customer writes are allowed only for exactly one
property; multi-property requests must name a property explicitly.

The shared cap covers all active upper-cost allocations plus completed planning
reservations and an explicitly confirmed legacy reserve. It is not actual bank
spending, realised savings, a property budget or a portfolio optimiser.
See `docs/MULTI_PROPERTY_CONTRACT.md` and `docs/WORKSPACE_MEMORY.md` for the
complete schema, routes, transaction/migration and expiry rules.
No ownership link is inferred for anonymised NEED data. New customer-grouped
ownership evaluation is separate from earlier property-only model metrics.

## Submission constraints

New rules: `deliverables/M1.pdf` max 2 pages, `deliverables/M2.pdf` max 2, `deliverables/final_report.pdf` max 3. Team NUMBER **225** at top; no team/member/college names in PDF/video.

README is setup/run instructions ONLY. Technical explanation belongs in `docs/`, not README.
Only main evaluated. No remote is configured. Team number **225** is confirmed.
Lead handles Git operations and report creation. Incremental local commits authorized.
