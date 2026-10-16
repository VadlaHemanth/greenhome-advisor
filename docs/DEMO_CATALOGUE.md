# Fictional home catalogue — version 1

**200 fictional England/Wales examples, not observed homes, representative
housing-stock statistics, new training data, or evidence of model accuracy.**
Money is GBP; energy is annual kWh; solar capacity is kWp; area is m².
The four original `engine.demo_homes()` records are unchanged. Public browsing
does not create customers, saved properties, completed work or workspace totals.

## Integration contract

Parent integration imports
`greenhome.demo_catalogue_api.create_demo_catalogue_router()` and registers the
returned `APIRouter` on the existing application. The factory takes no arguments.
It defines **`GET /api/demo-catalogue`**; it does not initialize the main API,
read `.env`, call a provider or access a persistence database.

| Query | Constraint/default |
|---|---|
| `q` | Optional string, at most 100 characters; default `""` |
| `property_type` | Optional exact value: `Detached`, `Semi detached`, `Mid terrace`, `End terrace`, `Bungalow`, `Flat` |
| `status` | Optional exact value: `available`, `no_affordable_option`, `no_modelled_benefit`, `insufficient_evidence`, `unsupported` |
| `page` | Integer ≥1, default 1 |
| `page_size` | Integer 1–24, default 12 |

Invalid query values return HTTP 422. Filters combine with AND. Search is a
trimmed, Unicode-casefolded literal substring over ID, label, property type,
region code and notes, not a regex or a numerical query. Blank search means
no search filter. Omit inactive type/status filters; empty strings are invalid.

Successful response keys are exactly:

```text
{
  version: string,
  total: 200,
  filtered_total: integer,
  page: integer,
  page_size: integer,
  page_count: integer,
  entries: [{ home, label: string, kind, notes: string[], ranking }],
  summary: { assessed: integer, evidence_needed: integer, flagged: integer },
  provenance: {
    label: string,
    synthetic: true,
    training_use: false,
    generator_version: string,
    sha256: string
  },
  policy: string
}
```

- `version` is `"1"`.
- `home` satisfies the existing strict `HomeInput` contract. Unknown supported
  facts remain null/`unknown`; no descriptions or provenance are inserted into
  home facts. All homes have `data_kind: "synthetic_demo"`.
- `kind` is `legacy`, `generated`, or `edge_case`. This is independent of
  `home.data_kind` and does not claim observed/evaluated status.
- `ranking` has exactly the existing `RankedHome` fields. Its `property_id`
  matches the home. `rank` is 1–200 or null for `insufficient_evidence` and
  `unsupported`; those rows also retain null opportunity/savings/cost values.
- `summary` counts **all filtered rows before pagination**. `assessed` means a
  known ranking opportunity, including a known 0% result, **not** a complete
  score or survey. `evidence_needed` combines insufficient and unsupported
  opportunity. The two sum to `filtered_total`. `flagged` counts the engine's
  poor/very-poor score flag and may overlap either group.
- `page_count = ceil(filtered_total / page_size)`, zero for no matches.
  Out-of-range pages are not clamped and return an empty list. Every successful
  page length is `max(0, min(page_size, filtered_total-(page-1)*page_size))`.
- `sha256` is the 64-character lowercase hexadecimal hash of the raw, checked-in
  `data/demo_catalogue.json` bytes. It does not hash a filtered response.
- Default order is descending globally ranked opportunity, then unranked
  evidence-needed rows; property ID breaks ties using the ranking module's
  existing case-sensitive lexical ordering, not numeric ID ordering.
- Filtering and paging **never recompute or renumber ranks**. Public examples
  belong on the parent's separate `#examples` route, not in saved totals.

Snapshot errors return HTTP 503:

```json
{"detail":{"code":"demo_catalogue_unavailable","message":"The fictional catalogue is temporarily unavailable."}}
```

No filesystem path, parser diagnostic or secret is included in that response.

## Data authorship, separation and reproducibility

`scripts/generate_demo_catalogue.py` constructs 196 new records from authored
rules and adds the four existing engine demos verbatim. It reads **no**
NEED/training/reference/evaluation rows, competitor materials or model artifacts.
It produces only the catalogue and its separate manifest. No model is trained
or used to invent annual meter totals, scores, EPC labels or baseline values.

Generation identity:

- Generator: `greenhome-fictional-catalogue-v1`; fixed integer seed
  `22520261016`.
- Each new ID has its own `random.Random` seeded by the string
  `generator_version:seed:property_id`; no clock or process hash seed is used.
- IDs are reserved `DEMO-01` … `DEMO-200`. First four are legacy; 5–180 are
  varied generated examples; 181–200 are explicit edge cases.
- Fixed quota allocation is round-robin after reserving legacy/edge slots.
  Record streams are per-ID, but changing quotas/rules is a new catalogue
  version, **not** permission to silently change an existing record.
- Raw bytes are deterministic for the existing Python environment: sorted-key,
  indented UTF-8 JSON with a trailing newline. There is no generation timestamp.
- Manifest includes raw-content SHA-256, per-home canonical JSON hashes,
  source-code hashes for engine/ranking, schema, distributions, assumptions,
  generation traces, purpose, reuse notice and `training_use: false`.
- Canonical home hashing uses sorted keys, compact separators, UTF-8 encoding,
  standard JSON ASCII escaping and finite numbers; it includes the ID.
  Uniqueness checks separately remove IDs and then remove financial/planning
  fields as well. Coarse rounded structural/energy fingerprints also have
  200 distinct values.

The data reuse notice requires attribution to GreenHome Advisor and preservation
of the synthetic/demo-only/no-training/non-calibration disclosures. It does
not assert any third-party row rights or turn a software licence into evidence
of rights over someone else's data.

### Authored coverage quotas, not prevalence

| Property type | Count | New ordinary area range | Heat-exposure multiplier |
|---|---:|---:|---:|
| Detached | 30 | 90–280 | 1.20 |
| Semi detached | 40 | 65–220 | 1.05 |
| Mid terrace | 36 | 55–180 | 0.85 |
| End terrace | 24 | 55–180 | 1.00 |
| Bungalow | 30 | 55–180 | 1.15 |
| Flat | 40 | 30–120 | 0.75 |

Each of the nine England region codes `E12000001`–`E12000009` and Wales
`W92000004` has 20 records, including the four London legacy records. Equal
regional counts are coverage targets, not a claim about population frequency.
The deliberate 340m² out-of-envelope edge is outside the ordinary area range.

## Correlated generation assumptions

All coefficients/probabilities below are authored, non-empirical design
choices. The generator records latent demand/load traces, **not extra measured
facts**, and never passes those traces to the app to fill missing inputs.

### Structure, fabric, equipment and permissions

1. Area is a whole-square-metre uniform draw inside the overlapping type range.
   Ordinary age bands 1–4 use probabilities `[.20,.32,.28,.20]`; age 5 is
   reserved for a deliberate inference-abstention edge.
2. Poor/partial/good insulation probabilities by age are:
   band 1 `[.45,.40,.15]`, band 2 `[.30,.45,.25]`,
   band 3 `[.15,.45,.40]`, band 4 `[.05,.25,.70]`.
   Thus older improved and newer imperfect homes remain possible.
3. Single/double/triple glazing probabilities are `[.05,.70,.25]` for good
   insulation; otherwise `[.55,.43,.02]` for age ≤2 or `[.20,.70,.10]`.
4. Gas/heat-pump/resistance heating probabilities are `[.55,.35,.10]` with good
   insulation, otherwise `[.82,.08,.10]`. Controls probability is .85 for a
   heat pump and .45 otherwise. These are correlated assumptions, not fitted
   equipment-adoption rates.
5. Ordinary flats have no private roof access. Other homes draw explicitly
   recorded roof access with probability .92. Roof-access homes draw existing
   PV with probability .18, then uniformly 2/3/4kWp. The flat exceptions are
   explicitly labelled with rights, never inferred from being a flat.
6. Listed status has probability .20 at age 1, otherwise false. When listed,
   relevant consent has probability .65; ordinary non-listed homes retain
   false consent. Installer readiness is a separately drawn Boolean with
   probability .80; type, budget and unlisted status do not grant readiness.
7. Budget is a uniform choice among unknown, £1,000, £2,000, £7,500,
   £16,000 and £24,000. Edge cases add zero and cost-boundary budgets.
   It is a hypothetical planning constraint, not affordability advice.

### Annual fuel bookkeeping

For each new record, latent occupants are a uniform integer from 1 through
`min(5,max(1,floor(area/25)))`. No real household size is inferred or exposed
as a new HomeInput field.

```text
useful space heat =
  area
  × fabric intensity (poor 150, partial 100, good 60 kWh/m²)
  × type exposure
  × glazing multiplier (single 1.12, double 1.00, triple 0.92)
  × age multiplier (1:1.08, 2:1.04, 3:1.00, 4:0.96)
  × uniform(0.8,1.2)

useful hot water = useful space heat × (1-0.8)/0.8
non-heating electricity = (900 + 550×occupants + 4×area) × uniform(0.85,1.15)
```

Gas boilers convert total useful heat with gross-CV efficiency 0.85 and add
non-heating electricity. Heat pumps use SPF 3.0 for the total useful-heat
input; resistance uses efficiency 1. Gas is **confirmed zero** for these
gas-free generated heating cases, not a missing-meter replacement.

Existing PV generation is capacity × 900kWh/kWp/year; self-used generation is
45% (unless explicitly overridden), capped by gross electrical load. Subtract
it **once** to obtain nonnegative grid imports; round both annual fuels to the
nearest 10kWh. No hourly matching, batteries, export income or monthly histories
are fabricated.

The engine's `space_heat_fraction` applies to a whole fuel meter:

- Gas uses 0.8, consistent with the above useful-heat split up to fuel rounding.
- New electrically heated homes use
  `(useful space heat / heating efficiency) / rounded gross electricity`,
  rounded to eight decimal places. This excludes appliance and hot-water
  energy from the modelled space-heating savings.
- With existing PV, that fraction describes gross pre-PV electrical load,
  **not grid imports**. The existing engine withholds electrical-demand
  changes and fuel switching without behind-the-meter evidence; this
  catalogue does not bypass that gate.
- The original four fractions and records remain byte-for-byte equivalent
  in canonical JSON; they are not retroactively regenerated.

Edge overrides to known structure/equipment are applied before calculating
fuel totals; deliberately unknown facts and explicit zero/missing-meter
boundaries are then applied. Withheld facts stay unknown at serving time.
No claim is made that an annual-zero edge is typical occupied consumption.

### Invented labels, values and uncertainty

EPC uses a noisy ordinal index: insulation poor/partial/good gives 0/1/3;
single/double/triple glazing gives 0/1/2; gas/heat-pump/resistance gives 1/2/0;
existing PV adds 1; jitter is sampled from `[-1,0,0,0,1]`. Clamp the sum to 0–6
and map to `G,F,E,D,C,B,A`. This is **not an EPC methodology, certificate,
survey or post-retrofit label**.

Fictional current GBP value is:

```text
round((65000 + 1850×area) × (0.85 + 0.03×region_index)
      × uniform(0.85,1.15), nearest £1,000)
```

Clamp ordinary values to £75,000–£1,500,000. Region index is the ordered
coverage-code index 0–9, **not a measured regional market relationship**.
No sales, causal retrofit premiums, tariffs, bill savings or market calibration
are generated. Missing current values remain null. Age-5 and area/value
out-of-envelope inputs are labelled for existing inference abstention; the
catalogue itself invokes no model and makes no value-impact prediction.

## Explicit edge records

| ID | Purpose |
|---|---|
| DEMO-181 | Missing area/EPC; score null while fuel opportunity may rank |
| DEMO-182 | Missing electricity, not zero |
| DEMO-183 | Missing gas, not gas-free |
| DEMO-184 | `unknown` heating, insulation and glazing |
| DEMO-185 | Null equipment/permissions/value with zero budget; remains evidence-needed |
| DEMO-186 | Both fuels exactly zero; undefined percentage denominator |
| DEMO-187 | Known demand and confirmed £0 cap |
| DEMO-188 | £349: just below controls upper cost |
| DEMO-189 | £350: controls upper cost exactly admitted |
| DEMO-190 | Listed, relevant consent withheld |
| DEMO-191 | Listed, relevant consent explicitly confirmed |
| DEMO-192 | Unknown roof rights and installer readiness |
| DEMO-193 | Flat with explicit roof rights; heat-pump readiness false |
| DEMO-194 | Already-improved supported no-action case, no roof rights for new PV |
| DEMO-195 | Existing PV with electric heating; demand-change potential unsupported |
| DEMO-196 | Age 5, 340m², £1.6m: outside frozen inference envelope |
| DEMO-197 | All five supported improvements explicitly deferred |
| DEMO-198 | Installer readiness confirmed false |
| DEMO-199 | Unknown current value and unconstrained budget |
| DEMO-200 | Gas-free resistance heating, poor fabric, zero PV self-consumption |

## Ranking and bounded serving

The offline builder calls the existing model-free `rank_homes` for two
admitted ≤100-home batches. Every home is screened once by `engine.screen_home`;
the existing package choice, signed fuel/carbon arithmetic and 1e-9
percentage-point quantization remain unchanged. It then calls the extracted
`assign_global_ranks` **once across all 200 rows**, overwriting every batch rank.
Ties use competition numbering (1,1,3), and unknowns remain null.

`rank_homes` still rejects arbitrary batches over 100. No main API request
limit, frontend rank validator, workspace/customer/property cap, seed source,
model or calculation rule was changed.

The fixed loader:

- reads at most 1MiB of catalogue and 256KiB of manifest;
- rejects missing/bad hashes, wrong version/provenance, stale engine/ranking
  hashes, duplicate JSON keys, nonfinite JSON, invalid records, wrong IDs,
  duplicate physical records, mismatched summaries/distributions and invalid
  global ordering/ranks;
- caches one validated release snapshot per process and copies response data;
- performs no per-request screening, optimizer/stress grid, model load,
  provider call or database access;
- does not accept request-controlled file paths. Explicit loader paths are
  only an offline Python validation interface.

Hashes protect accidental integrity, **not adversarial authenticity** if both
files and code are replaced. Deploy catalogue and manifest together and restart
the process when replacing them. Rebuild after intentional engine/ranking
source changes; do not silently serve a mismatched numerical snapshot.

## Regeneration and targeted validation

Use the existing environment; no installation or training command is required:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/generate_demo_catalogue.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider \
  tests/test_demo_catalogue.py tests/test_ranking.py -q
```

`--output-dir PATH` writes the same two files to an explicit scratch destination.
The generator validates both files before reporting success. It does not
modify other data or calculate new model results.

Tests cover byte-for-byte regeneration, exact legacy snapshots, 200 complete
and physical/coarse fingerprints, real HomeInput declarations without main-app
initialization, all five ranking statuses, global ties across batches, signed
fuel savings, energy bookkeeping, bounded API filters/pages, source/hash
rejection, mutation isolation, no model/training/credential-file reads and
four-customer SQLite workspace creation. These are synthetic conformance
checks, not real participant research or measured retrofit outcomes.

Executed commands, results, checksums and implementation review are recorded in
`work/home-upgrade/catalogue-implementation.md`. Browser, deployed-app, frontend,
full-suite and real-model evaluation remain outside this worker's validation.
