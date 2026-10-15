# Finite-grid decision check

**10 October 2026 implementation update:** shared model-free screening now
enforces nominal relevance and excluded measures, preserves supplied zero
fractions, and supports gas-only work with existing PV. The frozen-run metrics
below are **historical**, not validation of these changed sources. Their
engine/decision hashes no longer match; the evaluation **needs a separate
rerun**. No old report or hash was replaced during this change.

## Scope and contract

`greenhome.decision.decision_check(home: dict) -> dict` follows the top-level
response in `docs/REACT_HANDOFF.md`. The lead owns the API endpoint; this module
does not import FastAPI, a UI, Gemini, or a new model.

The objective is **annual purchased-energy savings**, electricity imports plus
gas. Costs and operational carbon remain separate. Neither the cohort benchmark
nor synthetic property values rank packages.

One initial `engine.screen_home` obtains known-feasible and energy-relevant
interventions, disclosed defaults, the current greedy package and all candidate
nominal scenarios. There is **no ML inference at all**, including no initial
`assess`, value model or benchmark load. Subsequent grid evaluations use only
`engine.calculate_scenario`.

The shared search considers at most 32 subsets of the five-item catalogue,
including no-op. It rejects candidates outside hard gates, exclusions and the
sum of upper indicative costs. It retains nonempty packages only with positive
nominal savings and measures having positive nominal marginal benefit in at
least one affordable package. This preserves jointly useful zero-standalone PV,
without admitting a solar-only zero action. The same constraints apply to all
strategies. An absent budget means no affordability constraint, explicitly warned.

## Three choices, not three estimates of certainty

- `greedy_package`: existing catalogue-order, upper-cost-budget selection.
- `nominal_package`: greatest energy saving at the supplied assumptions.
- `recommended_package`: smallest worst-case **regret** over the finite grid.

For package P and scenario s, let E(P,s) be its calculator-estimated energy saving.
Regret is `max_s(max_Q E(Q,s) - E(P,s))`, where Q ranges over the same feasible
packages. This is minimax regret, not maximin savings. Ties within `1e-8` kWh/year
use lower upper cost and then lexicographic catalogue-ordered retrofit IDs.

For nonzero supplied fractions the grid is the Cartesian product:

| Hypothetical parameter | Values |
| --- | --- |
| Space-heating fuel fraction | 0.6, 0.8, 1.0 |
| Heat-pump seasonal performance factor | 2, 3, 4 |
| New PV self-consumption fraction | 0.25, 0.45, 0.65 |

These are **analyst stress choices**, not published empirical uncertainty bounds,
probabilities, forecasts, confidence intervals or sampling weights. Supplied
values define the nominal point and are never clamped. **A supplied zero
space-heating fraction or zero solar self-consumption remains fixed at zero**:
replace that axis with the singleton `{0}`, rather than inventing positive
actionable demand or self-use. There are consequently 27, 9 or 3 grid points.
If the exact nominal point is not already present, append it once; the resulting
counts can also be 28, 10 or 4. An appended point is labelled `nominal`,
including when the fixed-zero grid is smaller than 27.
Every other input stays fixed, including recorded EPC, meter totals, property
features, permissions, exclusions, boiler efficiency, yield and budget.

For nonzero supplied parameters, alternatives remain counterfactual stresses,
not changes to a recorded fact. There is no new general measured/uncertain
provenance flag; the zero safeguard is deliberately conservative. Outputs must
not imply that sensitivity testing validates assumptions. Current demand
reductions, costs, fuel boundaries and annual solar approximation still apply.

`packages` includes all handoff fields and two additive signed details:
`nominal_electricity_saving_kwh` and `nominal_gas_saving_kwh`. Carbon is
`nominal_carbon_kgco2e`; `cost_gbp` is a separate lower/upper cost range.
Grid minima/maxima are not quantile intervals. The chosen package need not be
the cheapest or the carbon-maximising package; no weighted composite is invented.

## Stability and next evidence

`stable=true` means the recommended package has effectively zero regret on every
tested point, among currently feasible choices. It does not mean guaranteed,
unique, validated in practice, or independent of unknown permissions.

For an unstable decision, consider exactly resolving one stress parameter:
partition scenarios by that parameter, compute a new minimax regret in each
branch, and take the worst branch. Rank possible evidence checks by reduction
from current minimax regret; then by the number of matched comparisons where
varying only that parameter changes the winner; then by fixed parameter order.
No branch probabilities are assumed. If only a switch is identified, say that
resolving it alone does not improve worst-case regret. If a stable choice exists,
do not invent a measurement priority.

Questions concern a space-heating/end-use estimate, installer SPF estimate, or
daytime-load plus roof/yield evidence for self-consumption. Exact resolution is an
information-analysis assumption; a real measurement may be noisy, costly or unable
to resolve the choice. There is no claimed financial value of information.

## Missing facts, hard gates and no-op

Invalid values raise ValueError, including inputs outside the engine's aligned
finite bounds. Missing annual electricity/gas or a zero combined baseline
returns `status=unavailable`; numerical fields, selected packages, stability,
packages and scenarios remain null. Out-of-range finite values that could
previously overflow now fail validation rather than reaching the calculation.

Unknown permission never receives a probability or is treated as approval.
The current engine withholds interventions and supplies reasons. Relevant unknown
facts remain outside the hypothetical stress grid.

If only no-op can be evaluated **because evidence is missing or the opportunity
is unsupported**, return `status=unavailable`, null packages/rank-related values
and a next-evidence explanation. Unknown solar and unsupported electrical work
with existing PV are not stable zero opportunities.

When confirmed budget/exclusions or known no-benefit assumptions leave only
no-op, retain an available no-action comparison with explicit limitations:
`stable=null`. `regret_kwh=0` is then a trivial identity, not a stable-choice
success or proof of no real improvement potential. The no-action check uses
**nominal** savings, not the greatest saving anywhere on a hypothetical grid.

Gas-only fabric/controls packages with existing PV are now evaluated, keeping
electricity imports fixed. Existing-PV fuel switching and electrical changes
remain withheld. With partial eligibility evidence, supported positive packages
can still be compared; `stable` only concerns those known-permitted packages.
Unknown affordable options can therefore keep **home-level maximum potential
unranked** even while a limited within-home decision comparison is available.

## Frozen evaluation protocol (specified before the first full run)

Six fictional DEMO-01 variants: gas `{3000,6000,12000}` kWh crossed with electricity
`{2400,4800}` kWh. Keep all other demo attributes fixed, including nominal fraction
0.8, SPF 3 and self-consumption 0.45. Cross those profiles with upper-cost budgets
`{3000,7350,17000,25000}` GBP: **24 designed cases**, not independent households.

Select greedy, nominal and robust packages on the nominal/development inputs.
The 27-point development grid remains as above. Separately verify all three
frozen packages at **eight off-grid combinations**:

- heating fraction `{0.7,0.9}`;
- SPF `{2.5,3.5}`;
- PV self-consumption `{0.35,0.55}`.

For each case, compute each strategy's largest off-grid energy regret against
the best same-budget feasible package at that off-grid point. Report every case,
better/tied/worse outcomes, and any nominal-energy savings sacrificed by robust
selection. No post-verification tuning. No observed or synthetic ML split files,
market observations, new labels, retraining or external calls are used.

Optimisation guarantees on the development grid are mathematical identities.
Off-grid performance is still only a calculator sensitivity check, not physical,
customer, causal, market or novelty validation. Do not call it real-world savings.

## Reproduce

From the repository root:

```bash
.venv/bin/python -m pytest tests/test_decision.py -q
.venv/bin/python scripts/evaluate_decision.py
```

The script writes only:

- `reports/decision_metrics.json`: protocol/source hashes, aggregate actual
  results, all worse-case IDs, no-action counts, measured runtimes and caveats.
- `reports/decision_cases.json`: every case and strategy, including separate
  nominal fuel savings, carbon, costs and next evidence.
- `reports/decision_development_grid.csv`: every development scenario comparison.
- `reports/decision_off_grid.csv`: every verification scenario comparison.

Illustrative regression fixtures, not independently sampled evidence:
gas 6000 and budget 7350 gives greedy 1005.6 kWh versus nominal solar/controls
1551 kWh. At gas 12000, nominal fraction 0.8 and budget 7350, loft/controls gives
2011.2 kWh and solar/controls crosses it at self-consumption 0.496. The solar
assumption is therefore a meaningful next-evidence candidate in that fixture.

## Historical frozen-run results (10 October 2026, pre-fix sources)

**Not a current-source result.** The implementation has since changed; source
hash drift is intentional and must not be concealed by editing the reports.
The evaluation command above has **not** been rerun as part of this patch.
The following figures and timings are retained only as the historical record.

The first full evaluation completed all **24 cases**, **648 development rows**
and **192 off-grid rows** with **zero feasibility or budget violations**.
All 24 were active decisions; none was an unavailable/no-action case.

| Strategy | Mean of case-level off-grid maximum regrets, kWh/year | Largest case-level off-grid regret, kWh/year |
| --- | ---: | ---: |
| Current greedy | 1836.6975 | 5610.2914 |
| Nominal exhaustive | 58.54725 | 389.3670 |
| Minimax regret | 58.54725 | 389.3670 |

Minimax selection beat greedy in **16** cases and tied in **8**, with **0 worse**
cases. It tied nominal exhaustive selection in **all 24** cases. There were no
nominal-energy sacrifices on this designed set. All cases, including ties, are
retained in the reports.

**This experiment does not demonstrate incremental performance improvement from
minimax over nominal enumeration.** Its demonstrated addition is disclosure of
assumption sensitivity and a model-based next-evidence check; no user benefit
study was performed. The grid and selection policy were not altered to seek a
better post-verification result. These are calculator comparisons, not real savings.

The evaluation's median decision call was **0.0496 seconds**. A separate
full-catalogue check confirmed 32 packages and 27 scenarios; ten warm calls took
**0.046–0.062 seconds**, all below two seconds. The first fresh-process call in
that check took **2.080 seconds**; earlier cold calls took approximately
2.13–2.66 seconds, including the mandatory initial assessment's model imports
and loading. A strict two-second cold-start requirement is **not established**.
The lead can warm the existing assessment/model path before serving interactive
requests; no API/startup code was changed here.

`reports/decision_performance.json` records the individual timing observations,
not just their summary. Timing is machine/load-dependent and not a guarantee.

The old cold timings included an initial ML assessment that the current
decision path no longer performs. Do not present them as current timings or
infer a new latency guarantee without a new measurement.

## Current-source regression checks (10 October 2026)

The combined engine/decision/ranking focused run passed **251 tests in
3.89 seconds**. The broader engine/ML/explanation/API/decision integration run
passed **480 tests in 12.34 seconds**, with one pre-existing TestClient
deprecation warning and network connections disabled in the pytest process.
Exact file lists and limitations are in `CALCULATIONS.md`.

Regressions cover the audit's zero-share/£3,000 case (no recommended work,
`stable=null`, all tested savings zero), zero self-consumption, reduced-grid
nominal labels, exclusions in every strategy, supported existing-PV gas-only
packages, genuinely unavailable no-op cases and retained joint-only PV.
These are calculator regression checks, **not** a rerun of the frozen
24-case/eight-point off-grid evaluation or measured physical/customer outcomes.
