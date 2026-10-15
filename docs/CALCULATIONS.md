# Calculation method

This is a screening prototype for England and Wales, not an EPC certificate, survey, quote or financial valuation. Exact floor area and annual fuel inputs come from explicit user/demo inputs. NEED's area bands are used only by the separate benchmark model, never silently substituted for exact measured area.

## Score mappings

Fixed weights: recorded energy rating 25%, annual purchased-energy intensity 20%, insulation 15%, heating 15%, windows 10%, renewable energy 10%, controls 5%.

- EPC A=100, B=85, C=70, D=55, E=40, F=25, G=10. The anonymised dataset's A/B band maps to 92.5 as an explicit midpoint assumption, not an invented A or B certificate.
- Intensity = (annual grid imports + annual gas input) / floor area. Score is 100 at 50 kWh/m²/year or below, linearly falling to zero at 400 or above. These are prototype anchors, not statutory EPC thresholds.
- Insulation: poor 20, partial 60, good 100.
- Heating: resistance 30, gas boiler 60, heat pump 90.
- Windows: single 20, double 75, triple 100.
- PV: installed kWp / 4 × 100, capped at 100. This is a simple capacity proxy, not a household-specific generation assessment.
- Smart controls: absent 0, present 100.

Unknown components remain unknown and prevent a complete total. Weights are not redistributed. Contributions sum before final nearest-integer rounding (ties upward). Bands: 0–29 Very poor, 30–49 Poor, 50–64 Moderate, 65–79 Good, 80–100 Highly efficient. The two lowest bands are flagged.

The total uses **unrounded** weighted components. Returned contributions are
rounded to four decimal places for display; summing those displayed values can
cross a rounding boundary and must not redefine the total or classification.

EPC measures assessed building performance; consumption intensity measures reported annual use. EPC reflects envelope/systems too, so residual overlap with insulation/heating/glazing is inherent in the prescribed components; we retain the fixed weights and disclose that overlap rather than claiming statistical independence. PV affects both imports and renewable provision; this overlap is also explicit.

## Fuel accounting and interaction

Default assumptions: 80% of heating-fuel input is allocated to space heating, gas-boiler seasonal efficiency 0.85 on a gross-CV basis, heat-pump SPF 3.0. These are editable scenario assumptions, not measured properties.

For a gas home, split gas into space heating and other uses. Useful space heat is space-heating gas × boiler efficiency. Loft insulation reduces remaining space-heating demand by 15% (poor insulation) or 7% (partial). Single-to-double glazing reduces the remainder by 10%; controls reduce the remainder by 7%. Reductions are sequential, not added. This simplified multiplicative assumption is not a full building-energy simulation.

If heating remains gas, divide remaining heat by the same efficiency. If a heat pump replaces space heating, add remaining useful heat / SPF to electricity, while retaining gas for non-space-heating use. This prototype does not model simultaneous hot-water conversion. Increased electricity is intentionally a negative saving.

Solar uses an assumed new 3 kWp installation, 900 kWh/kWp/year yield and 45% self-consumption, capped by the post-retrofit electrical load. Exports are not counted as household demand reduction or income. This annual approximation does not resolve hourly coincidence; scenario assumptions and warnings remain visible.

For existing solar, **gas-only loft/glazing/controls changes are supported for
gas-boiler homes** with the ordinary evidence and permission gates. They leave
electricity imports unchanged and reduce only gas space-heating input. The
unchanged-gas-heating equation cancels the same boiler efficiency algebraically:
`G_after = G × (1 - f) + G × f × remaining`. This is the same signed physics,
without multiplication/division underflow for very small positive efficiencies.

Existing-PV changes to electrical demand, gas-to-heat-pump switching, and PV
expansion still need behind-the-meter/load or site evidence outside this model.
They are withheld, not assigned zero opportunity. Unknown solar capacity is not
silently treated as absence of PV.

Each standalone intervention compares to the original baseline. A package reruns the complete sequence. No-op is zero. Percentage improvement is unavailable for missing or zero purchased-energy baseline.

## Carbon

DESNZ 2026 full set: electricity 0.13096 kgCO₂e/kWh (UK electricity E25); mains natural gas gross CV 0.18231 kgCO₂e/kWh (Fuels D42). Operational boundary excludes upstream energy, distribution/transmission, refrigerants and embodied emissions. Use the same factors for baseline and scenario.

Carbon reduction = electricity saving × electricity factor + gas saving × gas factor. Both fuels must be known for the complete output.

Source: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026

## Feasibility and costs

Roof permission, building consent, existing insulation/glazing/controls, known energy inputs and heat-pump readiness are explicit gates. They are not a replacement for an installer/surveyor's assessment.

Indicative installed-cost ranges are prototype assumptions: loft £800–£1,600, glazing £4,000–£10,000, controls £150–£350, space-heating heat pump £9,000–£15,000, PV £4,500–£7,000. No grant or subsidy is assumed. Budget checks conservatively use the upper range and also check the package total.

### Energy relevance, zero inputs and excluded measures

`screen_home(home)` is the shared **model-free** screening path used by
assessment, nominal home ranking, and the finite-grid decision check. It inspects
at most **32 subsets** of the five catalogue measures and calculates each
hard-gate-permitted nominal subset once, including no-op. Unconstrained costs
are retained internally only to distinguish no affordable option from no
modelled benefit; they never authorise an over-budget recommendation.

A measure is recommended only if it has a **strictly positive marginal
purchased-energy benefit in at least one affordable nominal package**.
Subtract the saving for the same package without that measure; do not sum
standalone effects. This is energy relevance, not verified installability.

- A supplied zero heat share or zero consumption of the stated heating fuel
  does not become heating demand. Irrelevant heating measures have
  `feasible=false`, Low suitability and a reason. A zero heating-fuel total
  prompts confirmation rather than imputation.
- Zero PV self-consumption yields no purchased-energy benefit; exports and
  export revenue are outside this model.
- **Zero-import PV can be jointly useful.** If an eligible, affordable heat
  pump creates electrical load, retain PV with `joint_only=true`; its
  standalone zero is displayed honestly. The converse can also occur for a
  heat pump with efficiency/SPF both one, if PV makes the joint package useful.
  Excluding the load-creating measure, missing readiness, or an insufficient
  joint budget removes this route.
- The existing catalogue-order automatic package still uses upper costs, but
  nominally redundant members are removed. It remains a heuristic, **not**
  maximum potential; `rank_homes` uses exhaustive nominal optimization.
- An explicit no-op remains valid. Explicit infeasible/irrelevant measures
  and nonempty zero-benefit selections raise `ValueError` in `assess`.
  The low-level `calculate_scenario` arithmetic kernel still accepts valid
  zero assumptions and computes zero effects; it is not an eligibility API.
  It validates numeric inputs and IDs, not permissions, exclusions or budgets.
- With missing gas, supported PV can still show a known electricity reduction;
  the aggregate saving, carbon and percentage remain null.

`excluded_retrofits` is an optional home field, default **`[]`**. It must be a
list of at most five unique known catalogue IDs; null, non-list values, unknown
IDs and duplicates fail validation. Excluded/deferred work is withheld before
package search, not merely annotated afterward. It changes recommendations,
greedy and optimal packages, all decision strategies, and property rankings.
It does **not** change current home features, baseline usage, or the fixed score.
Explicitly selecting an excluded measure raises `ValueError`.

Recommendation rows retain their existing fields and add `status` and
`joint_only`. Statuses distinguish `available`, `excluded`,
`already_installed`, `not_applicable`, `no_modelled_benefit`,
`no_affordable_option`, `insufficient_evidence` and `unsupported`.
Reasons remain user-readable. Budget feasibility is package-level, so a
joint-only measure can be unaffordable even if its standalone price fits.

### Potential is separate from the selected scenario

`assess` additionally returns `potential: {"status": ..., "reason": ...}`.
This describes availability of a maximum-potential assessment, **not** the
chosen scenario's percentage. Statuses match property ranking:

- `available`: at least one positive, supported affordable nominal package.
- `no_affordable_option`: a positive option is supported without the budget,
  but none fits the stated upper-cost budget.
- `no_modelled_benefit`: no positive benefit under the known facts, exclusions
  and constraints; not proof that every real-world improvement is useless.
- `insufficient_evidence`: missing/zero combined fuel baseline, or unresolved
  eligibility evidence relevant to the permitted search.
- `unsupported`: no positive supported option and the remaining opportunity
  needs an outside-model assessment (for example electrical changes with PV).

No-op with known positive baseline still returns **zero** savings and **0%**
selected improvement, even if maximum potential is unavailable. The added
potential status and warnings prevent misusing that identity as an opportunity
estimate. Missing/zero baselines do not get a percentage. Supported gas-only
PV work can have available potential, explicitly excluding the unsupported
electrical changes from its scope.

Cross-home ranking publishes and compares percentage reductions at a fixed
**1e-9 percentage-point precision**, nearest with half-up rounding. The same
quantized value drives order and competition ties; binary roundoff must not
split proportional-home ties. This does not round raw fuel/carbon effects or
change nominal package selection. It is a deterministic precision rule, not
a relative tolerance, uncertainty bound or coarser UI display rounding.
See `PROPERTY_RANKING.md` for exact half-bin and boundary semantics.

## Missing data

This first version takes annual fuel totals. Monthly ingestion/seasonal imputation is not implemented; it does not manufacture monthly data from annual NEED observations. Gas zero must mean confirmed no consumption, not missing data. Oil, district heating, detailed roof geometry, battery storage and EPC reassessment are outside the current calculator.

The integrated release adds an independent monthly-input preview helper; the
calculator still receives annual totals. It uses an explicitly selected complete
12-month window, validates duplicates/periods/values, and withholds incomplete
fuel totals rather than seasonally imputing. The user must apply the preview;
rows are not persisted or inferred from NEED. See `docs/ENERGY_INPUTS.md`.
This updates the earlier annual-only intake statement, not the frozen formulas.

## Direct-call numeric safety

`validate_home`, `assess`, `calculate_score`, `calculate_scenario` and the shared
search reject non-finite numbers, booleans masquerading as numbers, and
out-of-bound supported quantities. Direct-library bounds now match the maintained
HTTP numeric envelope: each fuel 0–10,000,000 kWh/year; floor area
0.01–100,000 m²; solar 0–10,000 kWp; budget 0–£1,000,000,000; current value
strictly positive and at most £1,000,000,000,000. Existing fraction/SPF/yield
constraints remain. Missing optional values remain missing, not zero.

These are computational safety bounds, **not validated residential operating
ranges**. They prevent finite input extremes from overflowing aggregate energy,
intensity or JSON output. The scenario also checks that derived fuel, savings,
percentage and carbon values are finite. No sign clamping or invented saving
has been introduced.

## Validation performed on 10 October 2026

Focused offline suite: **251 passed in 3.89 seconds**, covering
`tests/test_engine.py`, `tests/test_engine_audit.py`,
`tests/test_engine_relevance.py`, `tests/test_decision.py` and
`tests/test_ranking.py`. Earlier development runs were **120 passed / 15 failed**
(superseded behavior assertions), then **190 passed / 1 failed** (a test expected
the zero-benefit label instead of the valid not-applicable label); these are not
reported as passing runs.

Broader offline integration suite: **480 passed in 12.34 seconds**, one
Starlette TestClient deprecation warning; no failure or deselection was reported.
This included all five focused files plus `tests/test_ml.py`,
`tests/test_explain.py`, `tests/test_api.py` and `tests/test_decision_api.py`,
with `-k "not apptest" -q -p no:cacheprovider`. The existing `.venv` was used,
bytecode writes disabled, and socket connections disabled in the pytest process.
No live/provider validation was performed.

The zero arithmetic checks remain: the former zero-action `assess` fixtures
now check the numerical kernel **and** assert the new plan-rejection semantics.
New tests cover jointly useful zero-import PV, fixed-zero stress axes, signed
gas/PV accounting, exclusions, exact ranking ties, upper-cost boundaries,
missing versus zero opportunity, direct finite safety and no ranking ML/API
imports. Ranking includes **24 independent rational nominal-reference cases**,
each checking the upper-cost constrained optimum against a 32-subset search.

No model artifacts, old metrics, training data or decision-evaluation reports
were rewritten. The old decision reports' engine/decision source hashes are
now stale: **a separate evaluation rerun is required** before claiming those
results apply to this implementation. See `DECISION_CHECK.md` and
`PROPERTY_RANKING.md` for current contracts and limitations.

### Tie-precision development follow-up

The previously recorded 251/480-test runs predate the numerical tie correction.
The independent reference diagnostics were subsequently inspected, including
the previously labelled **test** split. They reported five wrong ranks and
two ordering failures from binary-roundoff-split rational ties, not failed
fuel calculations or package feasibility. This exposure is disclosed:
post-fix replay is development regression evidence, not a fresh untouched
holdout result. The 1e-9 percentage-point rule was explicitly requested for
this correction, not chosen by optimizing performance on reference labels.

Generic proportional-home regressions failed before correction (**11 failed,
2 passed, 62 deselected**) and the updated ranking suite then passed
**88 tests in 0.68 seconds**. Reference cases, expected labels and metrics were
not edited. The parent manages source-snapshot updates and formal evaluation
reruns; the old report hashes must not be silently presented as current.

The broader follow-up regression passed **508 tests in 11.60 seconds**, one
Starlette TestClient deprecation warning, with socket connections disabled and
the same nine-file scope as the initial broader run above. A read-only replay
of the 48 stored development/test ranking cases matched **48/48 ranks**,
**48/48 statuses**, both split orders, and **306/306 pairwise comparisons**;
all checked non-ranking fields were unchanged. Protected reference-file
SHA-256 checks matched before and after replay. This is explicitly **seen-set
development regression evidence**, not a replacement formal report or new
holdout evaluation. The detailed parent handoff is in `PROPERTY_RANKING.md`.
