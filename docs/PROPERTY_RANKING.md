# Property improvement-potential ranking

Implemented 10 October 2026 for the England/Wales GreenHome pilot, Team 225.
Energy is annual purchased electricity imports plus gross-CV gas; money is GBP.
This is a deterministic screening calculation, not measured savings, an EPC
reassessment, financial return, property valuation or a guarantee.

## Integration contract

`greenhome.ranking.rank_homes(homes: list[dict]) -> dict` returns exactly
`policy`, `rows` and `warnings`. It never imports `greenhome.api`,
`greenhome.decision`, a provider, or the ML/value modules.

The policy string is exactly:

> Maximum nominal purchased-energy reduction under each stated budget; upper indicative costs

Each row has:

| Field | Meaning |
| --- | --- |
| `property_id` | Supplied ID, or null; no invented identity |
| `rank` | Competition rank (1, 1, 3), or null when unranked |
| `status`, `reason` | Availability/constraints and plain-language explanation |
| `score`, `classification`, `flagged` | Current fixed-weight score, not a post-retrofit or ML score |
| `improvement_percent` | Nominal purchased-energy reduction quantized to 1e-9 percentage points for publication/ranking, or null |
| `baseline_kwh` | Known electricity + gas; null if either fuel is missing; confirmed zero remains zero |
| `selected_retrofits` | Nominal maximizing package in catalogue order; empty for a known no-action result or an unassessable package |
| `electricity_saving_kwh`, `gas_saving_kwh` | Separate signed nominal savings, or null |
| `carbon_reduction_kgco2e` | Signed per-fuel operational carbon calculation, or null |
| `cost_gbp` | Lower/upper indicative package costs, `[0,0]` for known no-action, null for unknown potential |
| `budget_gbp` | Supplied upper-cost budget, or null for unconstrained comparison |

The lead-owned HTTP route is `POST /api/rank-homes` with
`{"homes":[HomeInput,...]}`. This module also enforces at most **100** homes for
direct callers; an empty list is valid. Invalid batch shapes, non-string
non-null IDs, invalid home values or exclusions raise `ValueError`.
IDs are not generated or silently deduplicated. Duplicate or missing IDs retain
stable input order when both potential and ID tie; callers needing persistent
row identity must supply unique IDs.

## Maximum nominal potential, not the selected scenario

Use `engine.screen_home` once per home. It enumerates at most **32** subsets
including no-op, applies physical/evidence gates and exclusions, and calculates
nominal signed fuel effects once per permitted subset. Affordable packages use
the **sum of upper indicative costs**, not lower quotes or per-item checks only.
No budget means no affordability cap and is disclosed in the warnings.

Relevant measures must add positive nominal marginal energy saving in at least
one affordable joint package. Nonempty candidate packages must themselves have
positive nominal saving. A zero standalone is not a universal no-benefit test:
zero-import PV can reduce new heat-pump load in a joint package. A zero
self-consumption fraction cannot. Excluding the partner or having insufficient
joint budget removes that route.

Choose the candidate with maximum nominal **net kWh** saving for that home
(equivalent to maximum percentage for its fixed positive baseline).
Package ties use lower upper cost, then the lexicographic tuple of
catalogue-ordered retrofit IDs. Unlike the separate minimax-regret chooser,
ranking does not merge differences within a tolerance.

Compute each home's nominal percentage:

`100 × (electricity_saving_kwh + gas_saving_kwh) / baseline_kwh`

Then apply the shared **1e-9 percentage-point quantization**, nearest with
half-up rounding, to that percentage. Publish this quantized
`improvement_percent` and use **the same value** for descending home order
and equality when assigning competition ranks. This replaces the original
raw-float equality rule; binary roundoff must not create false distinctions
between mathematically proportional homes.

`greenhome.ranking.quantize_improvement_percent` implements this policy using
exact `Fraction` arithmetic on the float's decimal string, then returns the
quantized number as a JSON-compatible float. `RANK_PERCENT_QUANTUM` is exactly
`Fraction(1, 1_000_000_000)`. Half-quanta round away from zero; for example
12.1234567885 becomes 12.123456789, not the half-even result. This does not
depend on the process's Decimal precision/rounding context.

This is **fixed-grid rounding, not a pairwise tolerance**. Two values in the
same bin tie; values across a bin boundary remain distinct even if their
difference is less than 1e-9. Unlike pairwise `isclose` grouping, it is
transitive and independent of input order. Quantization changes a percentage
by at most 0.5e-9 percentage points (apart from the returned float's usual
representation precision). It is not an uncertainty interval or a claim that
the screening assumptions are accurate to nine decimal places.

Equal quantized percentages receive equal competition ranks. Property IDs
sort ties deterministically (case-sensitive string order; null before strings).
Unranked rows follow all known percentages and sort by ID. Coarser UI rounding
must not alter ranks. Absolute kWh, fixed scores, greedy packages, carbon,
synthetic value uplift and an arbitrary currently selected no-op are still
not the ranking metric.

Package selection, budget checks, raw signed fuel savings and carbon calculations
are **unchanged**. A positive nominal opportunity below half a quantum can
publish as 0% while retaining `status=available` and its positive fuel-saving
evidence; quantization must not relabel it as `no_modelled_benefit`.

Different stated budgets mean different constrained opportunity sets; the
result is not an equal-investment comparison. Carbon, cost and fuel changes are
kept separate. Household priority/disruption preferences do not silently change
the mandated energy-percentage ranking objective.

## Status and evidence policy

| Status | Ranked? | Meaning |
| --- | --- | --- |
| `available` | Yes | Positive nominal optimum in the supported, permitted, affordable catalogue; a subquantum percentage may round to zero |
| `no_affordable_option` | Yes, **0%** | Positive supported options exist without the budget, but none fits its upper-cost cap |
| `no_modelled_benefit` | Yes, **0%** | Known assumptions, exclusions and confirmed constraints yield no positive modeled benefit |
| `insufficient_evidence` | **No**, null percentage/rank/savings/cost | Missing/zero fuel denominator or unresolved relevant eligibility evidence; do not invent opportunity |
| `unsupported` | **No**, null percentage/rank/savings/cost | Remaining opportunity requires an outside-model assessment and there is no positive supported package |

Unknown energy is never zero-filled. Baseline zero is valid input but lacks a
percentage denominator. Unknown solar, heating/end-use facts, installation
readiness or permissions must not create an apparent assessed 0% opportunity.
Even if some safe packages can be calculated, missing evidence about an
**affordable, non-excluded** option makes a maximum-potential ranking incomplete,
so the home is left unranked. An unaffordable or explicitly excluded unknown
option need not withhold a known positive budget-constrained result.
If no option could be assessed at all, a small budget does not convert that
unknown opportunity into `no_modelled_benefit`.

Score-only missing inputs (for example EPC or exact floor area) leave the score
null without inventing those facts. They do not withhold an otherwise complete
fuel-based opportunity estimate because those quantities do not enter these
retrofit equations. Required **potential** evidence, rather than all optional
HomeInput metadata, determines whether a percentage can be ranked.

Existing PV permits safe **gas-only** fabric/controls work on gas-boiler homes;
imports stay fixed. Its available row explicitly excludes unsupported
electrical-demand changes, fuel switching and PV expansion from the comparison.
When only these unsupported opportunities remain, the row is unranked rather
than called zero opportunity.

`excluded_retrofits` defaults to `[]` and contains unique known IDs. Deferrals
are hard selection constraints in assessment, ranking and decisions, not
changes to the current home's installed features. If everything is excluded,
known energy permits `no_modelled_benefit` under those exclusions; this is not
a claim that unrestricted improvements are useless.

## Initial regression evidence (before the tie-precision correction)

On 10 October 2026:

- **251 tests passed in 3.89 seconds** across the focused engine, decision and
  ranking suites.
- **480 tests passed in 12.34 seconds** across the focused suites plus existing
  ML, explanation, API and decision-API regressions; one TestClient deprecation
  warning. The pytest process had socket connections blocked. Full file lists
  and development-run outcomes are recorded in `CALCULATIONS.md`.
- Ranking checks include **24 independent rational reference cases** (three
  gas inputs × two electricity inputs × four budgets), each deriving the
  nominal maximum from the five-measure, 32-subset calculation independently
  of engine scenario output.
- A batch regression executes **100 homes / exactly 3,200 nominal scenario
  calculations**, with no assessment, model or stress-grid inference. A fresh
  subprocess verifies that ranking does not import API, decision or ML modules.
- Tests covered exact floating-point equality and competition ties, missing evidence,
  known-zero statuses, budget boundaries, exclusions, input detachment, signed
  fuel/carbon accounting, and jointly useful zero-import PV.

The audit's fictional same-£7,350-budget counterexample is now a regression:

| Home | Baseline | Nominal optimum | Saving | Percentage |
| --- | ---: | --- | ---: | ---: |
| A: poor insulation, gas 6,000, electricity 4,800 | 10,800 kWh | Controls + PV | 1,551 kWh | 14.3611…% |
| B: good insulation, gas 10,000, electricity 4,800 | 14,800 kWh | Controls + PV | 1,775 kWh | 11.9932…% |

A correctly ranks ahead of B despite its smaller absolute kWh saving; the
old greedy-default percentages reversed that order.

These tests verify code/contract and documented equations, not independently
measured retrofit effectiveness. No provider, market/physical validation,
model retraining, artifact modification, deployment, commit or push was
performed. Historical `decision_evaluation` reports retain their original
source hashes and **need a separate rerun**; they do not validate this patch.

## Tie-precision development correction (10 October 2026)

Inspection of `reports/reference_metrics.json` and
`reports/reference_predictions.json` found **seven failures: five incorrect
home ranks and two split-order mismatches**. Their numerical, package,
feasibility and status checks passed. Exact rational percentage ties were
split by roughly 1e-14 percentage points of binary roundoff in the candidate.
Generic proportional-home probes reproduced the defect without copying
reference records or their expected labels into tests.

**Exposure disclosure:** both the `dev` and previously labelled `test` split's
stored diagnostics and expected results were seen. This is a development
bugfix motivated by those diagnostics, with the 1e-9 precision policy explicitly
requested by the user; it is not untouched-holdout validation or independent
evidence of predictive improvement. No reference case, expected label or metric
was edited. Do not relabel an inspected old test set as a fresh holdout.

Before the code correction, the new proportional-home regressions produced
**11 failed, 2 passed, 62 deselected in 0.38 seconds**. After correction,
`tests/test_ranking.py` passed **88 tests in 0.68 seconds**. Added checks cover
12 proportional-home configurations with five scales each, deterministic ID
ordering across input permutations, competition-rank gaps, nearby materially
different percentages, decimal half-up boundaries, transitive bins, missing
and zero values, ambient Decimal-context independence, and preservation of raw
fuel/carbon values and nominal package selection.

The broader offline regression then passed **508 tests in 11.60 seconds**, with
one Starlette TestClient deprecation warning, covering the engine, engine audit,
engine relevance, decision, ranking, ML, explanation, API and decision-API files
listed in `CALCULATIONS.md`. Socket connections were disabled in the pytest
process; no provider validation was performed.

A separate **read-only development replay** loaded the 48 cases already
represented in the stored `dev`/`test` diagnostics and compared fresh
`rank_homes` results with their unchanged rational reference expectations:

| Stored split | Ranks matched | Statuses matched | Full order matched | Pairwise comparisons matched | Non-ranking field sets unchanged |
| --- | ---: | ---: | --- | ---: | ---: |
| dev | 24/24 | 24/24 | Yes | 153/153 | 24/24 |
| previously labelled test | 24/24 | 24/24 | Yes | 153/153 | 24/24 |

Thus the five reported rank failures and both ordering failures no longer
reproduced in this replay. Non-ranking fields checked were baseline, selected
package, signed per-fuel savings, carbon, costs, budget and score fields.
SHA-256 before/after checks confirmed that the reference cases, manifest,
case-source evidence, metrics and predictions files were byte-for-byte unchanged
during replay. Results were printed in memory, not written into the reports.
The original report still records its seven pre-fix failures and old source
hashes. This replay did **not** rerun the entire 1,584-request reference evaluation
or restore the inspected test split's independence.

### Parent integration handoff

- The JSON field set and `policy` string are unchanged. Only the published
  ranking percentage's precision and resulting cross-home ties/order change.
- Use the published `improvement_percent` for comparisons; do not reconstruct
  raw ratios or apply a different pairwise epsilon in downstream views.
- `FINAL_BUILD_CONTRACT.md` now describes the same precision rule. The
  reference expected labels and evaluator remain independent and unmodified.
- Existing reference report source hashes describe the pre-correction files.
  The parent owns report/source-snapshot updates and any formal evaluation
  rerun. A development replay must not be presented as a new held-out result.
