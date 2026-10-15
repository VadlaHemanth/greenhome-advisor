# Data and trained models

## Run status and scope

**Training actually completed on 10 October 2026**, using Python 3.12.14,
scikit-learn 1.9.1, pandas 2.3.3, NumPy 2.5.3 and joblib 1.6.0
(the machine-readable version record is authoritative).

Run from the repository root:

```bash
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/train_models.py
.venv/bin/python -m pytest -q tests/test_ml.py
```

These commands prepare data, fit models and compute actual holdout predictions.
They do not call an LLM. Models are not energy-savings calculators. Value models
are not market valuations. All currency amounts are GBP.

## Official energy source: metadata first

- Publisher: Department for Energy Security and Net Zero (DESNZ).
- Dataset: NEED anonymised domestic property-level 50,000-property sample, 2026.
- Official publication:
  https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026
- CSV:
  https://assets.publishing.service.gov.uk/media/6a282ad83b15d05a7ce31fb1/anon2026_50k.csv
- Metadata workbook:
  https://assets.publishing.service.gov.uk/media/6a282d2be371d9d2c0052b39/NEED-2026-anonymised-dataset-metadata.ods
- Workbook publication date: 11 June 2026.

The script obtains and parses the ODS metadata **before** reading targets. It uses
standard-library ZIP/XML parsing, so an ODS engine is not required. The original
workbook, original CSV, parsed metadata, source URLs, byte counts and SHA-256
digests are preserved in `data/`. `data/data_manifest.json` is the provenance
record. Cached downloads are explicitly identified.

The workbook describes one row per anonymised property, in England and Wales.
It is not an address-level EPC or sales join. The source snapshot represents
current domestic properties in the October 2025 council-tax database. Rare
combinations and records with missing key structural characteristics were removed
by the publisher before sampling. The training subset therefore does not represent
every UK household, Scotland, Northern Ireland, or excluded rare properties.

No names, addresses, customer IDs, UPRNs or personal customer data are used.
Generated IDs are `NEED2026-000001` etc., the stable 1-based row in this hash-pinned
snapshot. The publisher supplies no persistent property identifier: stability
across reordered or future releases is **not** claimed. Identical coarse feature
combinations do not imply duplicate properties and are not deduplicated.

Attribute reuse to DESNZ/NEED 2026 and retain publisher provenance. GOV.UK's
standard Open Government Licence framework applies where not otherwise stated;
review the source publication's notices before redistributing elsewhere. No
attempt is made to re-identify properties or join anonymised rows to addresses.

### Verified mappings and quality policy

| Field | Meaning used |
|---|---|
| `PROP_AGE_BAND` | 1 before 1930; 2 1930–1972; 3 1973–1999; 4 2000 or later |
| `FLOOR_AREA_BAND` | 1 <=50; 2 >50–100; 3 >100–150; 4 >150–200; 5 >200 m² |
| `PROP_TYPE` | Detached, Semi detached, Mid terrace, End terrace, Bungalow, Flat |
| `EPC` | A/B, C, D, E, F/G, No EPC |
| `REGION` | E12000001–E12000009 and W92000004 |
| `MAIN_HEAT_FUEL` | 1 gas main fuel; 2 not gas main fuel; **excluded from predictors**, see below |

API floor areas are continuous: boundaries map using `<=50`, `<=100`, `<=150`,
`<=200`, then the open-ended band. No band midpoint is invented for observed
training. API A/B and F/G are collapsed to the source categories. A missing EPC
maps explicitly to the source's `No EPC` cohort, not to an efficient rating.
Missing region/type/area or invalid age abstains. The engine's synthetic age
band 5 has no verified NEED mapping; the energy API abstains rather than guessing.
Synthetic value training separately supports synthetic ordinal age bands 1–5.

For **each fuel separately**, keep finite numeric annual targets only when its
2024 quality flag is `V`. `E` denotes estimated consumption, so it is excluded
from this *observed* benchmark. `L`, `G`, `O`, and blank flags are excluded.
Supplier estimates are not relabelled as observed; missing consumption is
**never zero-filled**. A valid electricity row is retained even when its gas
target is missing, and vice versa.

| Source count | Electricity | Gas |
|---|---:|---:|
| V, accepted observed targets | 45,214 | 37,186 |
| E, estimated | 1,020 | 2,316 |
| L, below threshold | 2,101 | 1,015 |
| G, above threshold | 155 | 214 |
| O, missing | 740 | 609 |
| Blank/unmatched meter | 770 | 8,660 |

All accepted values in the independently selected model sample are used; there
is no discretionary outlier trimming. Valid observed electricity is within
500–25,000 kWh and gas within 1,000–50,000 kWh. A disagreement between metadata
and valid-value bounds raises an error rather than silently removing records.
Targets are rounded to 100 kWh by the publisher.

Electricity `Econs2024` covers February 2024–January 2025 and is not weather
corrected. Gas `Gcons2024` is weather corrected; the workbook describes the
post-2020 gas reporting convention as consistent with the preceding mid-May
reporting windows. These are not synchronized calendar-year measures. They
are separate cohort benchmarks, not a reconstructed total-meter baseline.

### Leakage and temporal limitations

Predictors are **only** property type, age band, floor-area band, region and EPC.

The workbook states that `MAIN_HEAT_FUEL` is inferred from a matched gas meter
with at least 1,000 kWh in any of **2022–2024**. Including this would leak
information about the 2024 gas target. It is preserved for audit but excluded
from both fits. No annual usage, usage flag, property ID, deprivation variable,
tax band, or installation date/flag enters the energy feature matrix.
Inference ignores the home's supplied electricity/gas amounts.

The latest EPC has no lodgement date in this file, can be stale, and may
post-date the target. Property attributes also come from a later snapshot.
Consequently this is a **retrospective structural association benchmark**,
not a genuinely prospective/time-safe 2024 forecast. No claim that all
temporal leakage is eliminated is made. A production forecast needs dated
pre-outcome attributes, temporal validation, and independently observed heating
type rather than NEED's target-derived main-fuel field.

### Sampling, preprocessing and model

Seed 42; split unique property rows first, 60%/20%/20%. The full 50,000 rows
have 30,000/10,000/10,000 assignments. Select a deterministic, target-independent
20,000-property CPU sample from these assignments: 12,000 train, 4,000 validation,
4,000 test. Quality exclusion is then fuel-specific. All three pairwise
property-ID overlaps are **zero**, in the full data and sampled data.

| Accepted model targets | Train | Validation | Test |
|---|---:|---:|---:|
| Electricity | 10,941 | 3,615 | 3,607 |
| Gas | 8,918 | 2,991 | 2,983 |

Fit a train-only `OneHotEncoder(handle_unknown="ignore", sparse_output=False)`
and separate ExtraTrees models on `log1p(kWh)`, reversing with `expm1`.
The log transform reduces tail dominance; it does not make the result a
calibrated conditional arithmetic mean or exact median.

Fixed settings: 128 trees, minimum leaf 15, maximum depth 18, maximum feature
fraction 0.85, random state 42, two jobs. Baseline: train-only
`DummyRegressor(strategy="median")` for each fuel. No hyperparameter search,
test-based selection, test calibration, or train+validation refit occurred.
Validation and test preprocessing use the frozen train encoder.

### Actual observed-energy results (kWh/year)

| Target / split | Model MAE | Model RMSE | Median MAE | Median RMSE |
|---|---:|---:|---:|---:|
| Electricity / validation | 1,570.59 | 2,551.86 | 1,639.59 | 2,682.21 |
| Electricity / test | 1,610.72 | 2,578.06 | 1,691.10 | 2,734.82 |
| Gas / validation | 4,120.81 | 5,823.37 | 4,932.50 | 6,934.63 |
| Gas / test | 4,065.57 | 5,727.31 | 4,860.95 | 6,789.49 |

Test MAE improvements: electricity 4.75%, gas 16.36%. Error remains substantial;
unobserved occupancy, behavior, metering, weather and equipment matter. The
benchmark must not replace metered baselines or estimate retrofit effects.
The gas model is conditional on having a valid gas observation. At inference it
returns **null**, not zero, for electric/unknown heating. Electricity may still
be returned with `partial_observed_benchmark`. No false zero-label gas accuracy
is reported.

## Synthetic paired-home value model

**Every value training label, value output and value evaluation is synthetic
and not market-calibrated. No historical sales are present.** This does not meet
the evidential standard of a real property-valuation or causal retrofit study.
It is a transparent executable demonstration allowed by the challenge's
synthetic-data option, not an empirical universal premium.

Generate 1,800 fictional properties with seed 142, then split properties with
seed 143 into **1,080/360/360** before expanding scenarios. Produce **11,340**
unique within-property scenarios: **6,783/2,280/2,277** rows. Every property has
a no-op, each feasible individual retrofit, and unique mixed packages including
its full feasible package. No customer's/property's scenario crosses splits.

Property generation: uniform supported type and region; area uniform 30–300 m²;
synthetic age uniform 1–5; EPC uniform A–G; heating gas/heat-pump/resistance
probabilities 0.8/0.1/0.1; insulation uniform poor/partial/good; glazing
single/double/triple probabilities 0.55/0.35/0.10; controls probability 0.35;
solar chosen from `[0,0,0,3,4]` kWp. Flats have no roof access; readiness is
confirmed in generated references; no listed properties are generated.

The fictional *current baseline value* is area times a uniform 1,900–4,100
GBP/m², with a 1.35 London multiplier, clipped to £75,000–£1,500,000.
This is **not a historical sale price**. Before and after share location,
size, type and the same baseline value. No post-retrofit value, latent shock,
scenario identifier or target is supplied as a predictor.

### Exact hypothetical label rule

Let `n` be the count of effective upgrades, `d` the EPC deficit A=0 through G=6
(A/B=0.5 at inference). Numeric coefficients are **invented percentage-point
assumptions**, not fitted market effects:

- Loft: 0.65 for poor insulation, 0.30 for partial insulation.
- Single-to-double glazing: 0.60.
- New smart controls: 0.15.
- Gas-to-heat-pump change: 0.35.
- New solar: 0.75.

If `n=0`, impact is identically zero, including the noise term. Otherwise:

```text
epc_factor   = 0.55 + 0.12*d
size_factor  = clip((area/100)^0.15, 0.8, 1.15)
price_factor = clip((300000/current_value)^0.2, 0.65, 1.2)
type_factor  = 0.80 for Flat; 1.05 for Bungalow; otherwise 1
interaction  = 1 - 0.06*(n-1)
mean_percent = sum(active coefficients) * interaction * epc_factor
               * size_factor * price_factor * type_factor * region_factor
impact_percent = mean_percent + sqrt(n)*(0.55*Z_property + 0.20*Z_scenario)
after_gbp = before_gbp * (1 + impact_percent/100)
```

Region factors in order E12000001–09 then Wales:
`[1.10,1.05,1.05,1.00,1.00,0.95,0.75,0.90,1.00,1.05]`.
`Z_property` and `Z_scenario` are independent standard-normal draws; the
property-level shock is shared across that property's packages. Their role is
to illustrate an unobserved fixed market context and scenario uncertainty;
**no current market conditions are measured**. Labels are nonlinear, interacting,
heteroskedastic and can be negative. They are not a copied published premium.

Eligibility ignores already-installed measures; roof measures need explicit roof
access; heat pumps need gas heating and readiness; relevant listed-building
consents must be confirmed. Engine-level budget/energy feasibility is checked by
the engine before calling the value API. No-op packages are identical paired
homes, not a learned market prediction.

### Training and actual synthetic evaluation

Three separate `GradientBoostingRegressor(loss="quantile")` models at
alpha 0.10, 0.50 and 0.90. Fixed settings: 170 estimators, learning rate 0.055,
depth 3, minimum leaf 20, random state 42. Train-only one-hot categorical
preprocessing plus numeric area, age, EPC deficit, log baseline value, existing
solar/controls and effective retrofit indicators. Independently fitted quantiles
are sorted to remove crossings. Every no-op prediction is set to exact zero.
This same postprocessing is used in evaluation and runtime.

| Synthetic metric | Validation | Test |
|---|---:|---:|
| p50 MAE, percentage points | 0.50975 | 0.47825 |
| p50 RMSE, percentage points | 0.71230 | 0.67650 |
| Median-baseline MAE, percentage points | 0.57888 | 0.54186 |
| p50 MAE, GBP | 2,710.57 | 2,528.09 |
| p10–p90 coverage, all scenarios | 77.59% | 80.41% |
| p10–p90 coverage, active retrofits only | 73.39% | 76.73% |
| Mean active interval width, percentage points | 1.73530 | 1.73909 |
| No-op rows, all exactly zero | 360 | 360 |

The nominal central interval is 80%, **not a guaranteed calibrated interval**.
Coverage is lower for active upgrades; no-op rows inflate aggregate coverage.
No intervals were widened or tuned against the test set. Simultaneous coverage
of every scenario for a held-out property is only 50.28% validation / 56.11% test,
also reported in JSON. Rows within a property are correlated; no naive
independent-row confidence interval or real-world coverage claim is made.

## API contract and abstention

`greenhome.ml.predict_energy_benchmark(home)` returns exactly:
`electricity_kwh`, `gas_kwh`, `note`, `status`.
Statuses: `observed_benchmark`, `partial_observed_benchmark`, `unavailable`;
`synthetic_fallback` only if official downloading failed and the documented
fallback was actually trained. A missing model is exposed, never replaced with
a hard-coded claimed ML prediction.

`greenhome.ml.predict_value_impact(home, selected_retrofits)` returns exactly:
`status`, `low_gbp`, `high_gbp`, `low_percent`, `high_percent`, `note`.
These are **changes** in value, not predicted post-retrofit sale prices.

- Empty package: `no_change` and four exact numeric zeros, even without a
  current valuation; this is an arithmetic identity.
- Already-installed upgrades: `no_change`, exact zeros for otherwise known homes.
- Valid synthetic demo: `synthetic_illustration`, p10/p90 change range.
- Non-demo homes: always `abstained`; no opt-in bypass is implemented.
- Unknown structural/efficiency inputs, unsupported region/type, area outside
  30–300 m², baseline value outside £75k–£1.5m, invalid synthetic age, missing
  readiness/consent, unknown retrofit, or missing model: `abstained` with nulls.

Artifacts load lazily through the engine; the module makes no network requests.
Only trusted locally trained joblib files should be loaded: pickle/joblib is not
safe for untrusted uploads. The LLM must not turn these synthetic ranges into
market claims.

### Single-worker service inference (10 October 2026 follow-up)

The cached loader sets each energy pipeline's **fitted**
`TransformedTargetRegressor.regressor_.n_jobs = 1` immediately after loading,
before returning or caching the bundle. Setting only the constructor's
`regressor.n_jobs` would not change the fitted clone used by `predict`.
The inference-only override avoids nested per-tree joblib workers for small
service requests and their thread-configuration propagation overhead. It does
not globally suppress warnings or change process-wide sklearn/joblib settings.
Fitted trees, preprocessing and target transformations are unchanged. The
constructor template and serialized artifacts retain the training setting of
two workers; no retraining, artifact writes, metric changes or CSV rewrites occur.
This constrains forest-level joblib workers, not all possible BLAS/OpenMP threads.

Regression tests compare all 6,590 energy test predictions against the original
two-worker artifact with **absolute tolerance 1e-8 and zero relative tolerance**,
then against the frozen CSV at its original `%.12g` serialization precision.
The pre-existing CSV rounding alone differs from unrounded gas predictions by
up to approximately **5e-8**, including before this override: a strict unrounded
1e-8 comparison to that CSV is not supportable. Value quantiles are untouched;
all 2,277 value test rows are also checked at absolute tolerance 1e-8.
Tests verify cache reuse, unchanged artifact bytes, concurrent prediction
consistency and absence of the reported sklearn parallel-configuration warning.
Oversized positive and negative integers already fail `finite_number` safely
via its `OverflowError` guard and result in abstention; regression tests cover both.

Local follow-up validation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_engine.py tests/test_engine_audit.py tests/test_ml.py tests/test_explain.py \
  -k 'not apptest'
```

Result: **267 passed, 4 UI cases deselected, 8.95 seconds**, no warning summary.
These are local non-UI results, not a claim about the paused frontend or the
in-progress API. The earlier training-run counts below remain historical.

## Files, reproducibility and limitations

### Bounded serving cache, final build

Energy inference now caches up to 2,048 scalar predictions keyed by fitted
pipeline identity and its five coarse cohort features. IDs, user meter totals,
budgets, current values, conversations and workspace tokens are never cache keys
or stored values. Outputs are newly constructed for each request. Replacing a
model artifact creates new fitted pipeline identities and therefore separate
cache entries. Predictions still come from the frozen trained model and retain
the same rounding; no retraining or saved artifact/metric modification occurred.
Dedicated tests compare cached/uncached pipeline values and replacement-model
identity. This is an inference optimization, not a model-accuracy improvement.

- `data/energy_properties.csv`: one row/property, masked per-fuel targets,
  source flags, non-feature main-fuel audit field, split and sample membership.
- `data/energy_splits.csv`: complete frozen property assignment.
- `data/synthetic_value_properties.csv`: fictional property rows, pre-expansion
  split; latent property shock is reference-generation-only.
- `data/synthetic_value_scenarios.csv`: feature rows, IDs, paired before/after
  hypothetical references, target percentage and GBP impacts, inherited split.
- `models/energy_benchmark.joblib`: two trained energy pipelines and baselines.
- `models/synthetic_value.joblib`: three trained quantile pipelines.
- `reports/training_metrics.json`: exact actual metrics, counts, overlaps,
  timings, versions and artifact/prediction hashes.
- `reports/test_predictions.csv`: frozen held-out predictions (8,867 rows:
  3,607 electricity, 2,983 gas and 2,277 synthetic value).
- `reports/validation_predictions.csv`: corresponding validation predictions.
- `reports/data_preparation.log`, `reports/training.log`: executed command output.

Prediction CSV schema: `task`, `data_kind`, `property_id`, `scenario_id`, `split`,
`unit`, `actual`, `predicted`, `baseline_predicted`. Synthetic value rows also
include `p10`, `p50`, `p90`, current/before/after GBP, actual/predicted GBP and
`no_op`. Energy units are kWh/year; value target units are percentage points.
Blank value-only columns on energy rows mean not applicable, not zero.

Tests recompute recorded metrics and interval coverage from frozen predictions,
verify source flags, property separation, source/artifact integrity, metadata
mapping, absence of usage predictors, API schemas, deterministic no-op identities,
unknown/non-demo abstention and electric-heating gas withholding.
The final ML test command passed **66 tests**, including ten additional
unknown-consent/oversized-integer regression cases.
All four
parent-engine demo assessments also executed successfully: observed benchmarks
for supported inputs, synthetic ranges for eligible demos, exact-zero no-op for
the already-upgraded home, and abstention for the incomplete home. Model training
plus evaluation took **15.8323 seconds**, excluding downloading/preparation.
Saved model reload independently reproduced **all 8,867 frozen test predictions**.
The first full repository suite run was **151 passed / 7 failed**: four
unknown-listing/consent cases, two mutable engine-response cases, and one
oversized-integer engine-validation case. Those failures are in the parent-owned
engine, not the ML-owned files; they are recorded in `reports/full_test_suite.log`
and were not concealed or fixed by editing outside the assigned scope.

Only download/network failures trigger a conspicuous synthetic energy fallback.
Metadata/schema/quality failures raise errors instead of concealing a broken
pipeline. If fallback occurs, manifest and metrics say `synthetic_fallback`,
record the reason, and never claim observed-energy performance. **No fallback
was used in the completed run.**

No temporal forecast validation, causal effect identification, real sale-price
validation, fairness audit, geography-stratified error analysis or production
uncertainty calibration has been completed. No needlessly collected personal
data, API keys or secrets are written by these scripts.
