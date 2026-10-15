# Deterministic money and package comparisons

England and Wales pilot; all output money is GBP. These are screening estimates
over the existing five-measure catalogue, not quotes, tariff advice, guaranteed
savings or a whole-home retrofit design. The existing score and property-ranking
API are unchanged. No value model, trained energy model or explanation provider
is called by this feature.

## Integration and ownership

`greenhome.money_api.make_money_router(HomeInput, *, run_calculation=None)`
returns a FastAPI router. The parent integrates it inside `create_app`, using
its existing model **and shared bounded calculation runner**:

```python
from greenhome.money_api import make_money_router

application.include_router(
    make_money_router(HomeInput, run_calculation=calculations.run)
)
```

The router does not import `greenhome.api`. Its request model injects the actual
`HomeInput` and rebuilds the existing `HomeInput.excluded_retrofits` package
annotation, preserving the `RetrofitId` literals, strict lists and five-item
limit. Duplicate selections are normalized exactly as by `engine.assess`.
Home omissions and explicit nulls are preserved by `HomeInput.engine_home()`.

The endpoint is async and awaits
`run_calculation(money_plan, home_dict, selected_retrofits, tariffs)`. The runner
contract is `CalculationService.run`: perform admission before calculation,
execute off the event loop, bound running plus queued jobs, and raise
`ServiceBusy` when capacity is unavailable or a deadline expires. The existing
service keeps running work admitted after timeout/cancellation until that work
finishes; a queued job can be cancelled before it starts. The router does not
reimplement that policy or close an injected parent-owned service.

For standalone use, omitting `run_calculation` creates a router-owned
`CalculationService(workers=1, capacity=8)`, with the service's default 25-second
deadline. The router lifespan closes that private pool. This fallback is bounded
but **does not share** the parent's admission budget; the public integration
must pass `calculations.run` as shown above. Standalone callers must run the
application lifespan (e.g. a `with TestClient(app)` context).

The parent still owns request-body limits, ingress/origin policy and the shared
service lifecycle. The router accesses no accounts, persistence, credentials or
network services. Responses, including safe busy/deadline 503s, carry
`Cache-Control: no-store`; calculation state is per request.

Domain entry points:

- `money_plan(home: dict, selected_retrofits: list[str], tariffs: TariffInput | dict) -> dict`
- `calculate_money(home: dict, scenario: dict, tariffs: TariffInput) -> dict`
  prices an already-validated engine scenario, not arbitrary user scenario data.
- `TariffInput` validates inputs. `MoneyPlanResponse` validates output and is
  also the router's response model.

## Request

`POST /api/money-plan` with JSON:

```json
{
  "home": {"property_id": "EXAMPLE", "electricity_kwh": 4800, "gas_kwh": 12000},
  "selected_retrofits": [],
  "tariffs": {
    "electricity_pence": null,
    "gas_pence": null,
    "source": "user_entered",
    "as_of": null
  }
}
```

All three top-level fields are required. An empty selection explicitly means
unchanged home; it never triggers automatic selection. `home` follows the
existing HomeInput contract, including budget, exclusions, permissions and
assumption bounds. Unknown fields are rejected.

### TariffInput

| Field | Type / supported range | Omitted value |
| --- | --- | --- |
| `electricity_pence` | finite JSON number, 0–200 pence/kWh, or null | null |
| `gas_pence` | finite JSON number, 0–200 pence/kWh, or null | null |
| `source` | `"user_entered"` or `"illustrative"` | `"user_entered"` |
| `as_of` | real `YYYY-MM-DD` calendar date or null | null |
| `electricity_standing_before_pence_per_day` | finite number, 0–1000 pence/day, or null | null |
| `electricity_standing_after_pence_per_day` | finite number, 0–1000 pence/day, or null | null |
| `gas_standing_before_pence_per_day` | finite number, 0–1000 pence/day, or null | null |
| `gas_standing_after_pence_per_day` | finite number, 0–1000 pence/day, or null | null |

Zero is valid and never replaced with a default. Strings, booleans, NaN,
infinities, negative numbers and values above the inclusive bounds are rejected.
Rates are not rounded to integer pence: fractional pence are supported.
`as_of` is supplied provenance, not evidence that a tariff is current or verified.

The main client form must start with **null rates**, not 25/7. An explicit
illustrative-preset action may send electricity `25`, gas `7`,
`source: "illustrative"`; the server has no automatic preset and makes no
current-tariff claim.

### Standing charges

Each fuel is handled independently. Both its before and after standing rates
must be supplied to include them, using **365 days** for this annual screening
comparison. An incomplete pair is excluded, with an explicit incomplete-input
note. When both are absent, charges are excluded from before/after amounts and
assumed unchanged for savings. Excluded does **not** mean free or zero.

A heat pump does not automatically remove the gas supply or its standing
charge; the engine normally retains gas hot-water/cooking use. A supplied zero
after-charge is an explicit caller assumption, never inferred from the retrofit.
The same entered before/after charge pairs apply to every compared package;
package-specific tariff eligibility or supply disconnection is not modelled.

## Response contract

Exactly five top-level fields: `money`, `packages`, `picks`, `tariffs`, `warnings`.
Money and rate values serialize as **JSON numbers**, not Decimal strings.

```text
money: {
  status: "available" | "partial" | "unavailable",
  electricity: {before_gbp: number|null, after_gbp: number|null, saving_gbp: number|null},
  gas:         {before_gbp: number|null, after_gbp: number|null, saving_gbp: number|null},
  total:       {before_gbp: number|null, after_gbp: number|null, saving_gbp: number|null},
  monthly_average_gbp: number|null,
  payback_years: {low: number, high: number} | null,
  cost_gbp: [number, number],
  standing_charge_note: string
}
packages: [{
  id: string,
  retrofits: RetrofitId[],
  cost_gbp: [number, number],
  net_saving_kwh: number|null,
  improvement_percent: number|null,
  carbon_reduction_kgco2e: number|null,
  money_saving_gbp: number|null,
  recommendation_reason: string
}]
picks: {energy: string|null, bills: string|null, lowest_cost: string|null}
tariffs: TariffInput with defaults expanded, numeric rates and ISO date|null
warnings: string[]
```

`money` prices the explicitly selected scenario. It is not replaced by any
named pick. `cost_gbp` is always the indicative installation `[low, high]`
range, retained even when bills are unavailable or savings are negative.

`monthly_average_gbp` means **signed annual bill saving / 12**, rounded to
pence. It is not a monthly total bill or a seasonal prediction.

Each package ID is its catalogue-ordered retrofit IDs joined with `+`, e.g.
`loft_insulation+heat_pump`. `retrofits` uses the engine's existing field name.
Only nonempty packages are listed; unchanged home is still supported as an
explicit selection. Carbon and energy are engine outputs, not monetized or
combined into a weighted score.

### Missing data and availability

- Each fuel needs its own rate and before/after energy to report complete costs.
- If both fuels have complete costs, status is `available`.
- If only some costs are known, status is `partial`; if none are known, it is
  `unavailable`. Known per-fuel amounts stay visible.
- If either unit rate or either required fuel reading is missing, **all three
  total fields, monthly average, payback, package bill savings and `picks.bills`
  are null**. No model or previous request fills gaps, even when the other rate
  is zero. A known zero fuel requires a known rate for aggregate availability.
- Missing optional standing pairs do not disable variable-cost totals; they
  trigger the explicit exclusion/unchanged label above.

### Currency and payback

All billing arithmetic uses `Decimal(str(engine_value))`, with explicit
`pence / 100` conversion. For each fuel:

```text
before = round_half_up(before_kWh * rate_pence / 100 + included_before_standing)
after  = round_half_up(after_kWh  * rate_pence / 100 + included_after_standing)
saving = before - after
```

Round before/after amounts to two decimals, then subtract and sum those
displayed amounts. This makes totals and per-fuel savings reconcile exactly to
pence; it can differ by a penny from rounding a combined unrounded bill.
Negative electricity or total savings remain negative. Negative zero is
normalized to zero. JSON need not display trailing zeroes.

Simple payback is `[low cost / annual saving, high cost / annual saving]`,
serialized as `{low, high}`, rounded HALF_UP to two decimal years. It is null
unless the **displayed** annual saving is positive, so sub-penny savings
displaying as zero never produce an unexplained positive payback. It excludes
grants, financing, maintenance, replacements, discounting, future price changes
and export revenue. Very long arithmetic payback ranges are not lifespan or
investment-return forecasts.

## Named package objectives

`money_plan` calls `engine.screen_home` once and reuses its feasible,
upper-cost-affordable packages. It does not call `assess` or reimplement the
engine's physical gates. Explicit selection must match a returned screening
package, or it is rejected.

Screening relevance means that a measure helps in **some** supported package,
not every combination. Before constructing alternatives and picks, the money
layer compares each package with each one-measure removal. A measure is
redundant when removing it leaves **both modelled per-fuel consumption outputs
unchanged** (including preserved unknowns). Such a package is omitted from
`packages` and consequently cannot appear in `picks`. This uses engine outputs,
not rounded bill savings, zero tariffs, standalone usefulness, or a weighted
score. A missing subpackage is evaluated by the model-free
`engine.calculate_scenario` kernel and cached only within that request.

If the caller explicitly selected a redundant package, its `money`, complete
cost range and simple payback are still calculated for **all selected work**.
The response warns about each zero-marginal measure by ID/name and its extra
indicative installation cost, and explains why that package is omitted from
comparisons. No work is silently stripped from the selection.

Examples: with zero electricity imports, loft + PV without a heat pump has no
PV benefit, but heat pump + PV survives when PV offsets new electrical demand.
If PV already eliminates all modelled electric imports, adding fabric work
that leaves both fuels unchanged is also omitted as an alternative. These
comparisons do not imply that excluded work has no unmodelled comfort or other
benefit; they describe only this engine's supported energy calculation.

- `energy`: greatest known positive purchased-energy `improvement_percent`.
- `bills`: greatest positive rounded `money_saving_gbp`. Null if costs are
  incomplete or no package lowers estimated bills. Loss-making packages remain
  inspectable rather than being clamped to zero.
- `lowest_cost`: smallest **upper** installation estimate among nonempty
  packages. This avoids advertising doing nothing as the cheapest improvement.

Ties in the primary metric use lower upper cost and then lexicographic package
ID. Lowest-cost ties use the ID. Packages are ordered by upper cost then ID.
Every pick refers to an included package; no pick exceeds a supplied budget.
Absent budget means unconstrained comparison, with the engine warning retained.
Missing permissions/unsupported measures can limit the search; recommendations
and warnings label that limitation instead of claiming a whole-home optimum.

## Errors and verification

Malformed/invalid request: HTTP 422,
`{"detail":{"code":"invalid_money_input","message":"Missing, unsupported, out-of-range or invalid money input."}}`.

Infeasible or over-budget selection: HTTP 422,
`{"detail":{"code":"invalid_scenario","message":"The home or package is invalid or infeasible. Check missing fields, permissions and budget."}}`.

Admission rejection or calculation deadline: HTTP 503,
`{"detail":{"code":"service_busy","message":"Calculations are busy. Please try again shortly."}}`.

No error includes submitted home facts, unexpected field names, exception
representations or private values.

Tests: `tests/test_money.py` and `tests/test_money_api.py`. The reference DEMO-01
loft + heat-pump selection at explicit illustrative 25p/7p produces annual
£2,040 before, £1,946 after, £94 saved; electricity saves **−£578**, gas **£672**.
The original heat-pump-only example instead saves **−£8/year**, with no payback.
These are synthetic test cases, not measured household outcomes.
