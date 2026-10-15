# Independent required-output protocol — frozen v1

Team 225 · England and Wales · GBP · specified 10 October 2026.

## Evidence boundary

**The new reference cases are fictional, independently implemented arithmetic
and screening references, NOT real empirical savings, observed retrofit effects,
surveyor judgements, customer-study results, value targets or market evidence.**
There are no real people, addresses, ownership links, meter histories or sales
in these cases. NEED observations are used only in the separate consumption
benchmark. Never combine the two into an observed end-to-end dataset.

The written prototype assumptions are shared with the candidate. Independence
means a separately coded exact-rational end-use ledger and constraint/search
reference, with literal hand-calculated regression fixtures; it does **not** mean
an independently validated physical model or independently chosen effect sizes.
The reference code never imports candidate helpers or constants to generate
targets. Candidate imports and numerical comparisons happen only after reading
hash-verified frozen targets. No LLM, provider, retraining or new value model is
involved. Existing energy/value inference is stubbed in the required-output run.

## New case design and freeze

`scripts/evaluate_reference_cases.py --freeze` creates an immutable v1 JSON and
manifest and refuses to overwrite either. `--verify` checks hashes, counts,
customer/property separation and exact deterministic regeneration. The manifest
binds the seed, UTC freeze time, generator-at-freeze hash, reference/protocol
hashes and source-register-at-freeze hash. Every evaluation binds before/after
source hashes. Source changes during a run mean **rerun required**.

The generator first hashes 48 fictional customer IDs with the fixed seed
`225-independent-reference-20261010-v1`, assigns 24/12/12 customers to
train/dev/test, then assigns two properties per customer. This gives 48/24/24
properties, 96 total. All requests, targets and reference ranks inherit their
customer's split. No customer or property is in multiple partitions. IDs are
grouping keys, not model predictors. Train is reserved for future development;
**nothing is fitted to these synthetic cases in this task**.

Twenty-four deliberately designed archetypes occur within each split, with
deterministic, target-independent consumption scaling, six property types,
England/Wales regions, four age bands, varied area and EPC. This is a stratified
boundary/conformance suite, **not a population sample or unseen-archetype
generalisation experiment**. The train partition repeats the archetype cycle.
Related archetypes across partitions are disclosed; customer ID separation
does not make the shared assumptions statistically independent.

Each property has all 32 subsets of the five-measure catalogue plus one unknown
ID request: 33 requests/property, 3,168 total. This includes accepted no-op,
standalone, interacting packages, physically inapplicable/already-installed,
unknown, budget-rejected and non-beneficial requests. Feasibility is separately
labelled for each of five measures: 480 property/measure labels, not 480 people.
Dev+test evaluations contain 48 properties / 24 customers / 1,584 requests.
Actual accepted/rejected counts are computed into the manifest, never invented.

Cases explicitly include:

- Gas, resistance and existing heat-pump heating; poor/partial insulation.
- Flats without roof access; listed buildings with/without confirmed consent.
- Unknown heating/efficiency/permissions/PV and a missing fuel baseline.
- Zero purchased energy; zero space-heat fraction and zero PV self-consumption.
- Existing PV with gas-only measures (supported) and no remaining supported
  measures (unsupported), not automatically zero opportunity.
- £0, £350, £1,600, £1,950 and £1,949.99 budgets: exact individual/package
  boundaries and a one-penny-below boundary.
- PV capped by post-retrofit imports; fuel switching that increases electricity.
- Low SPF=1 / boiler efficiency=1 / no baseline electricity: individually
  zero-benefit switching/PV can be useful jointly.
- Deferred measures and a deliberate identical-potential property pair.

## Independent reference method

Use `fractions.Fraction(str(input))`, not candidate floating-point functions.
Store targets as exact rational strings; convert only at comparison/reporting.

Let E/G be annual grid imports/gross-CV gas, f the space-heating share,
η gross-CV boiler efficiency and S heat-pump SPF. Multiply retained space-heat
fractions: loft **0.85** when poor or **0.93** when partial, glazing **0.90**,
controls **0.93**. Their effects are not added.

- Retained gas heating: gas saving = G × f × (1 − retained).
- Space-heating gas-to-HP: gas saving = G × f; electricity saving =
  −G × f × η × retained / S. Non-space-heating gas remains.
- Existing electric heating: electricity saving = E × f × (1 − retained).
- New PV adds min(post-measure imports, 3 × yield × self-consumption share)
  to electricity saving. No export credit, battery, hourly coincidence or
  hot-water conversion is modelled.
- Net saving = signed electricity + gas savings. Percent = 100 × net/(E+G)
  only when both fuels and a positive baseline are known. Known zero is
  preserved; unknown is null, never imputed to zero.
- Carbon = signed electricity saving × **0.13096** + signed gas saving ×
  **0.18231** kgCO₂e. Use the same factors before/after.

Demand fractions, SPF, yield and installation-cost ranges are **prototype
assumptions**, not NEED-derived empirical effects or installer quotations.
Sources verify consumption definitions and carbon accounting factors, not the
15%/7%/10%/7% savings assumptions. Conditional arithmetic is exact, but physical
uncertainty is **unquantified**, not a zero-width empirical confidence interval.

### Feasibility, relevance and ranking policy

Feasibility means an explicitly permitted, supported measure with strictly
positive marginal purchased-energy benefit in at least one affordable
positive-benefit package. Determine this by independent rational comparisons
between packages with/without each measure. A zero standalone may be joint-only;
an explicit zero-benefit request is rejected. Budgets use sums of upper
indicative costs, without grants. Empty requests remain accepted identities.

Unknown evidence is distinct from a confirmed constraint or an excluded measure.
Missing consent for a listed building requires evidence, not a claim of
permanent physical impossibility. Already-installed measures are not new actions.
Gas-only fabric/controls with existing PV hold imports fixed. Changes to electric
load/fuel switching with existing PV lack behind-the-meter evidence.

Reference potential maximises nominal purchased-energy reduction over supported,
relevant packages under each property's own budget and exclusions, not the
candidate's currently selected package, EPC, value estimate or score. Missing
baseline or zero total is `insufficient_evidence`. Unknown relevant facts for an
individually affordable option also withhold a complete potential. Supported
positive options give `available` even when unsupported options also exist;
this is a maximum over the **supported catalogue only**, not every real upgrade.
With no positive affordable option, distinguish `no_affordable_option`,
`unsupported` and `no_modelled_benefit`.

Within each split, rank by exact percentage descending, with property-ID order
for ties and competition ranks (1, 2, 2, 4). Unavailable rows have null rank and
numeric potential, not rank zero. Preserve all optimal package ties; the ranking
contract's optional package tie-break is not used to fabricate a unique optimum.
The adapter checks the new `greenhome.ranking.rank_homes` rows, selected package,
per-fuel savings, carbon, costs, statuses, tie order and rank.

This v1 is frozen before its first candidate run, but the candidate's written
contract and implementation have been inspected. After first evaluation it is a
**regression/conformance test**, not a pristine unseen statistical holdout.
Do not modify its labels to remove candidate failures. Changes of scope or
assumptions require a separately versioned future protocol.

## Predeclared required-output metrics and baselines

Evaluate dev and test separately, without fitting; do not evaluate train as
held-out performance. Report:

1. Accepted/rejected request counts and all acceptance mismatches.
2. Feasibility false positives/negatives; reference unknown/excluded/budget/
   no-benefit/unsupported counts and correct withholdings. The candidate exposes
   a Boolean `feasible`; reason-text wording is not treated as truth.
3. Per-fuel post-retrofit levels and **signed savings**, net, percentage and
   carbon MAE/bias/max error, prediction coverage, null failures and sign counts
   for negative/zero/positive cases. Absolute numeric tolerance is 1e-8,
   relative tolerance zero. No-op/standalone/package denominators are separate.
   Missing/rejected predictions count as failed checks, not omitted successes.
4. Property- and customer-macro fuel MAE (mean within group then across groups)
   alongside scenario-weighted descriptions. No independent-scenario CI.
5. Pairwise cross-property order including reference ties and missing candidate
   predictions; rank/status/order mismatches. Unavailable reference homes are
   excluded from numeric pairs but retained in status/abstention evaluation.
6. **Zero-savings** and **sum-of-standalone** per-fuel baselines on the identical
   accepted requests, by split/kind. The additive baseline deliberately ignores
   interactions and is a diagnostic, not an alternate physical truth.
7. **No action** and **best beneficial feasible standalone** ranking strategies:
   pairwise agreement and mean/worst attainable-potential regret, in percentage
   points, over reference-available homes under identical constraints.

Report failures and ties even if unflattering. No assertions of calibrated
uncertainty, superiority significance, comfort, affordability in money saved,
adoption, future energy prices or real-home value accuracy follow.

## Validation-only observed-consumption benchmark

`scripts/evaluate_benchmark_baselines.py` reads the existing manifest/prepared
data and hash-verified frozen **validation** predictions from the existing
energy artifact. It does not fit/load/rewrite the model, retrain, tune, calibrate,
open test predictions or compute new test metrics. The artifact hash links the
historical model and frozen predictions; original logs/results are preserved.

Use exactly the existing target-independent `model_sample=True` assignments.
Skip test rows before target conversion/consumption. For each fuel separately,
learn medians only from training rows with that fuel's finite `V` target:

1. property type × floor-area band if cell n ≥ **30**;
2. otherwise area-band median if n ≥ 30;
3. otherwise property-type median if n ≥ 30;
4. otherwise global training median.

Threshold and fallback order are predeclared, not selected against validation
error. Compare global median, type/area cohort baseline and existing model on
the **same** valid validation property/fuel rows. Require exact membership and
label agreement with the historical frozen predictions; do not zero-fill.
Report MAE, RMSE and signed bias = prediction − observation; all EPC, region,
type, area, other-fuel-availability and EPC-availability slices with their counts,
including small/worse slices. Slices overlap; no multiplicity-adjusted or causal
claim. Save train-cell medians/support and every validation prediction.

Expected existing split counts are 12,000 training and 4,000 validation sampled
properties; actual valid-fuel denominators are checked against frozen rows.
Anonymous NEED IDs do not establish customer independence. Latest EPC and
October 2025 stock can post-date 2024 targets; this is a **retrospective
structural annual-consumption association**, not a prospective forecast or
retrofit saving. Electricity and weather-corrected gas periods differ.

## Memory and value boundaries

Customer grouping prepares a leakage-safe key structure only. No history
replay, retrieval, memory/no-memory comparison or behavioural study is performed.
Any future memory evaluation must freeze customer-disjoint episodes and allow
only authorised same-customer, correct-property history strictly before each
query, separating cold-start from warm-prefix episodes. Do not infer ownership
or join these fictional customers to anonymous NEED properties.

Existing synthetic value artifacts and metrics are neither changed nor
re-evaluated here; their non-market, non-causal limitations remain.

## Commands and outputs

From the project root, using the existing `.venv`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_reference_cases.py --freeze
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_reference_cases.py --verify
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q tests/test_reference_cases.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_reference_cases.py --evaluate
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_benchmark_baselines.py
```

Freeze is a one-time command, not part of routine reruns. Report outputs:
`reports/reference_metrics.json`, `reports/reference_predictions.json`,
`reports/reference_summary.md`, `reports/benchmark_baselines.json`,
`reports/benchmark_baselines.md`, `reports/benchmark_baselines_cohorts.json`,
`reports/benchmark_baselines_validation.csv`. `--split dev` or `--split test`
can isolate a reference run; each invocation replaces only the new reference
reports, clearly recording which split ran. A missing ranker records pending,
never a fabricated passing result. Rerun after concurrent engine/ranking edits.

Source metadata, licence evidence and limitations are in
`data/source_register.json`, `data/reference_cases_source_evidence.json` and
`docs/DATA_LICENCES.md`. No existing model, training file, artifact or historical
metric is edited. Nothing is committed, pushed, deployed or submitted here.
