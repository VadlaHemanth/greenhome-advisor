# Independent ownership evaluation

Team 225. New evidence only, 11 October 2026. GBP; explicitly fictional
England/Wales homes. The previous property-only model, reference and memory
reports remain historical evidence, not customer-grouped validation.

## Frozen protocol and reference

The evaluator first creates 15 fictional customer IDs, orders the SHA-256 of
`225-ownership-v1:` plus each ID, and assigns 9 train / 3 validation / 3 test.
Only then does it expand each split in repeating 1, 2, 4 property groups.
There are 21 / 7 / 7 properties respectively. Siblings inherit their parent's
split. Each customer then receives a chronological episode containing one
backdated completion and nine query phases for every property.

Train is **design-only**: no estimator is fitted and no training results are
claimed. Validation and test each contain all three property cardinalities,
63 authored property-query occasions and three completion events. These are
six executed customer episodes, not 126 independent people or real users.
Archetypes repeat across partitions; this is not unseen-archetype generalisation.
No NEED row is assigned an invented owner and no old output is relabelled.

The immutable JSON contains the protocol, prior customer assignments, raw
fictional inputs, timestamped steps and expected state at each query.
Reference construction does not import or invoke the engine, router, store,
ranker, old evaluator or a fitted model. Literal test assertions check the
reference's semantics independently of candidate outputs.

`--freeze` exclusively creates `data/ownership_cases.json` and its manifest
before candidate execution. It refuses to overwrite either. The manifest
hashes the complete reference and protocol, original supplied materials,
candidate sources at freeze and protected old evidence. `--run` verifies these
references and cannot rewrite them. Each run additionally hashes source files
before/after and treats concurrent changes as invalid evidence requiring rerun.

## Actual boundary and chronological replay

The harness mounts the production workspace router with the production
`HomeInput`, while blocking `.env` loading before importing the main module.
Each episode creates two private TestClient cookie jars and disposable
file-SQLite storage. State mutations use real HTTP methods and SQL store
transactions, not test-side mutation callbacks. ML benchmark/value functions
are explicitly unavailable stubs. Socket connections, provider SDK imports
and joblib loads are guarded and counted. No provider, paid call, production
database, real customer record or credential is used.

The store clock advances through actual POST/GET operations. Before the
backdated completion is recorded, captured GET inputs must retain poor
insulation, known meter totals and no completion event. After the event is
recorded, a subsequent GET must show good insulation, unknown fuels and the
new event's actual recording timestamp. Other properties must remain
byte-equivalent, including versions. This is an actual prefix replay; it does
not claim the application has an as-of history-query endpoint.

Coverage includes:

- One, two and four properties; independent creation, opaque resource IDs,
  immutable distinct home IDs, parent binding and separate property state.
- Wrong parent inside an authorized workspace and cross-workspace GET/save/
  completion, plus cross-workspace settings/add attempts. Require 404 and
  unchanged state in both workspaces.
- Property-only solar exclusion versus customer-wide controls exclusion;
  raw property preferences remain separate. Selected excluded plans fail.
- Property budget changes, shared-cap reduction rejection, conflicting global
  exclusions, stale customer/property versions, and legacy writes requiring
  explicit property selection when a customer has multiple properties.
- A loft plan reserves £1,600 of a £1,950 cap. Completing it transfers the
  £1,600 upper planning estimate from active plan to completed reserve without
  implying actual spending. Duplicate/future completion and unconfirmed
  replacement bills fail. Explicit replacement restores calculability.
- Two separately constructed stores concurrently submit sibling controls
  plans costing £350 at the same customer version. Exactly one can consume
  the remaining allocation. This is a real SQLite race, not a fake model test.
- Full workspace export, separately constructed store read-back, workspace
  deletion, old-cookie rejection, SQL customer/workspace absence and foreign
  workspace invariance. Logical deletion is not forensic disk erasure.

Disposable SQLite/WAL files are runtime scratch and removed after execution.
They are not deliverables or changes to live state. The harness itself writes
only its new ownership report; pytest runs without bytecode or cache writes.

## Arms, denominators and interpretation

All three arms use the **same deterministic engine and ranker**:

1. Scoped memory: actual GET for the requested customer/property.
2. Owner-blind memory: a legacy customer-root snapshot remembers the latest
   property's facts but drops the property key; the requested ID is attached
   to that snapshot. This deliberately diagnosed baseline can apply a
   completion, budget or local exclusion to a sibling.
3. Explicit current facts: independently authored recorded-prefix facts
   supplied anew without retrieving memory.

The one-property baseline must tie throughout. Multi-property errors are
binding failures, not evidence that the recommendation algorithm improved.
The explicit-facts arm must equal scoped outputs, showing that persistence
only supplies the correct inputs. Availability checks penalize an always-
abstaining controller; no artificial algorithmic win is claimed.

For every actual query retain inputs, outputs and per-criterion outcomes.
Report exact property facts, exclusion compliance, independently summed chosen
upper costs versus the property's budget, no reoffering completed measures,
correct missing/known-baseline handling and their conjunction. Denominators
exclude inapplicable criteria; constraints overlap and must not be summed into
independent trials. Report split, property cardinality and customer summaries
and paired successes. HTTP/security/planning-accounting checks are separate
from recommendation semantics. Shared caps are planning accounting, not a
portfolio-optimisation target or an individual property's budget.

No claim of fitted accuracy, LLM groundedness, physical saving, customer
benefit, bank authorization, browser security, PostgreSQL behaviour, v1
migration or representative user study follows from this experiment.

## Commands and execution status

From the project root, using its existing `.venv`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_ownership.py --freeze
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_ownership_evaluation.py -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_ownership.py --run
```

Freeze once only. Missing V2 routes are reported as `blocked_interface`, never
as passed tests or a skipped feature.

## Actual results, 11 October 2026

Reference frozen at **01:21:03.805827 UTC**, before the first candidate run
at **01:21:26.766951 UTC**.

- Reference SHA-256:
  `365336d4cc0c62502c92c0246407781edceae2eb92e5706e60f735fa792cf612`
- Protocol SHA-256:
  `8181fd730fe9bc4570dac96c0066fd589bbbbc6a943e813d8a837f5089e97bbe`

The final standalone report completed at **01:31:51.729857 UTC** with
`status: passed`. Source hashes were stable during that run, the raw reference
still matched its original freeze, and all protected previous model, memory,
training and reference evidence matched its pre-execution hashes.

| Partition | Assigned customers | Assigned properties | Executed customers | Actual queries | Recorded completions | HTTP requests |
|---|---:|---:|---:|---:|---:|---:|
| Train, design only | 9 | 21 | 0 | 0 | 0 | 0 |
| Validation | 3 | 7 | 3 | 63 | 3 | 573 |
| Test | 3 | 7 | 3 | 63 | 3 | 573 |

All six pairwise customer/property split-overlap counts are zero. Each split's
1-, 2-, and 4-property customers respectively executed 9, 18 and 36 query
occasions, with 121, 185 and 267 HTTP requests. Each episode has 19 authored
timeline steps and one committed completion. The request totals include all
verification GETs, failed requests, exports/deletions and concurrent writes,
not only the 126 scored property queries.

The real bootstrap seeds four customers per workspace. Across the six
episodes, 12 private workspaces, 48 customer records and 56 property records
were actually created. **Only six customers and 14 properties are evaluation
subjects**; the other 42 customer and 42 property records are untouched
same-workspace/foreign-workspace controls, not extra participants. All test
workspaces were deleted; disposable databases were removed.

There were **1,146 actual HTTP requests**, **100 successful HTTP mutations**,
and **50 completion-endpoint attempts**, of which six created completion
events. The other attempts exercise authorization, duplicate/future-event
rejection and legacy-route safeguards. **3,036/3,036 recorded assertions
passed**, including four two-store sibling-allocation races. Assertion counts
overlap and are not statistical sample sizes.

### Per-query semantics, identical totals for validation and test

| Criterion | Applicable queries per split | Scoped satisfied | Explicit facts satisfied | Owner-blind satisfied |
|---|---:|---:|---:|---:|
| Exact property facts | 63 | 63 | 63 | 27 |
| Exclusions respected | 52 | 52 | 52 | 52 |
| Chosen package within property budget | 18 | 18 | 18 | 18 |
| Completed measure not reoffered | 9 | 9 | 9 | 9 |
| Correct known/missing-baseline availability | 63 | 63 | 63 | 55 |
| All applicable semantics | 63 | 63 | 63 | 27 |

Scoped memory and explicitly re-entered current facts produced identical
controller outputs on **126/126** occasions. The owner-blind baseline
satisfied **54/126**, but this is not a recommendation-quality uplift:

- One-property customers: both arms satisfied **18/18**.
- Two-property customers: both satisfied **18/36**; scoped alone **18/36**.
- Four-property customers: both satisfied **18/72**; scoped alone **54/72**.

No owner-blind-only success occurred. Importantly, exclusion, budget and
repeat-completion compliance **did not improve** versus this control. Its
actual failures were incorrectly bound property inputs (72 occasions) and
wrong baseline availability (16 of those occasions). False abstention on
unchanged siblings is counted as a failure, not rewarded as safe behaviour.
No learned or algorithmic superiority is inferred.

The report contains raw actual property state, event IDs/occurrence/recording
times, versions, independently authored expected state, all three arm inputs
and outputs, actual statuses, and a logical-to-runtime identity map. Customer
and property IDs in this evidence are disposable fiction; cookies are absent.
Persisted planning reservations are never called observed spending or savings.
Per-property budgets constrain active plans; completed reservations belong to
shared planning accounting. Re-entered replacement fuel values are authored
inputs, not inferred from old bills or calculated savings.

Offline guards recorded zero network attempts, zero provider attempts and zero
model loads. There were 56 benchmark-stub and 56 value-stub calls; these return
unavailable values, not fitted predictions. One `.env` loading call was blocked
before reading the file.

### Regression and investigation of the parent's earlier failures

`reports/ownership_regression.json` records this actual command and its output:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests \
  -k 'not apptest' -p no:cacheprovider -q
```

**1,120 passed in 58.63 seconds**, including all 14 ownership test functions.
This aggregate is not added to the ownership checks as independent evidence.
The ownership experiment itself uses model stubs; the broader existing suite
also includes its normal model regressions.

The preceding fresh full run passed 1,113 tests in 53.83 seconds and is retained
under `previous_runs` in that JSON. Additional parallel backend tests account
for the later collection size. A separate final focused run recorded
**14 passed in 13.01 seconds** in `reports/ownership_tests.json`.

The parent's earlier `work/ownership-release/backend-first.log` reported
1,060 passed and two ownership failures. Its fixture run began at
01:22:55.090189 UTC while evaluator/test instrumentation was being edited.
The report assertion displayed all six episode statuses as passed and
`failures: []`, but an overall failed report. The other traceback's displayed
source lines do not reliably identify the in-memory assertion after those
edits. That log did not preserve the full fixture's source/guard fields.

**Diagnosis:** no candidate semantic mismatch is demonstrated by that log,
and none reproduced in the fresh focused or full-suite runs. A concurrent
source-hash guard failure is plausible, but cannot be proved retrospectively
from the truncated fixture. The raw chronology expectations were not changed.
Current diagnostics explicitly report `failed_report_gates` and
`changed_sources_during_run`; chronology assertions include actual phase/event
counts. Final values are empty failure lists and stable source hashes.

`reports/ownership_initial_run.json` preserves the first successful semantic
run. **Do not use its request totals**: the first harness omitted verification
GETs from that tally. Later changes corrected instrumentation, included raw
state/ID evidence, added immutable-ID checks and improved failure diagnostics.
The final trace logs event counts directly from actual HTTP-returned events,
with expected event counts in a separate field; raw history equality was
already checked in the earlier runs.
The reference/protocol JSON and the expected outcomes remained byte-equivalent.
Use `reports/ownership_evaluation.json` for the final complete denominators.
The parent's v1 database-copy migration rehearsal is separate evidence and is
not represented as an independently performed part of this evaluation.

## Independent brief/rules review: three concrete parent handoffs

Scope: the participant-supplied original `LLOYDS-ps2.pdf`, condensed PPTX,
general guidelines and submission-deliverables PDF; current local code,
recorded reports, final-report text, ignore rules and tracked-file inventory.
All four original documents are hash-pinned in the manifest. They are primary
normative sources, not empirical studies. Findings below are direct local
observations, not external product research, actual-user findings or an account/
submission audit. No known synthetic-value caveat is duplicated here.

1. **Active-provider regression is not an untouched held-out explanation
   evaluation.** PS sections 9/11 and PPT slide 13 call for leakage-aware
   evaluation, relevant baselines, and held-out explanation/what-if scenarios.
   `scripts/evaluate_active_provider.py` has one 12-case list based on one
   demo home, with no split assignment; it hashes that list while producing
   its results. `reports/integrated_provider_evaluation.json` correctly reports
   12 fixed regression checks and eight live completions, but no independent
   test partition. Its displayed grounding check compares rendered lines to
   the same allowed claim map; it is not independent raw-response factual
   adjudication. **Parent action:** retain the honest regression label; if
   stronger held-out claims are needed, separately freeze new prompt/context
   groups, intended actions and completeness criteria before running the
   final provider, and distinguish upstream raw-response validity, fallback
   rates and displayed-claim safety. No live evaluation or paid call was
   performed for this handoff.

2. **Some final-report evidence citations are not portable with the
   submission.** PS section 13G/I, PPT slide 15 and PS section 11 require
   inspectable/reproducible validation evidence. The inspected
   `deliverables/final_report.pdf` cites
   `work/integrated-release/{backend-tests,frontend-tests,api-contract}.log`,
   `backend-tests.xml` and `frontend/work/intake-*-final.log`. `git ls-files`
   returned no tracked files for those cited scratch locations; `.gitignore`
   excludes `work/` and `*.log`. The aggregate
   `reports/integrated_release_verification.json` exists, but is not the cited
   raw/JUnit evidence. **Parent action:** preserve a source-hashed portable
   validation record in included `reports/` content and update final citations
   to the actual included files. Keep chronological results separate rather
   than replacing old runs or changing their labels.

3. **The code-only packager will omit untracked ownership implementation
   files if run before staging/commit integration.** Submission-deliverables
   section 4 requires full solution code plus a code ZIP; PS 13B/I requires
   runnable preparation code and reference/schema documentation.
   `scripts/package_submission.py` enumerates only `git ls-files`, and at this
   inspection the new evaluator, frozen ownership fixtures and
   `greenhome/workspace_migration.py` were untracked. The packager also excludes
   all `data/`, so this evaluation's frozen cases cannot be reproduced from
   that code-only ZIP alone. This is a **current packaging hazard**, not proof
   of a failed submitted archive. **Parent action:** include all intended new
   code in the submitted revision before packaging, inspect the resulting ZIP
   contents, and ensure the judged repository separately includes the original
   frozen fixtures and manifest. Do not regenerate them to make the ZIP pass,
   do not invent an upload, and preserve the rules' dataset/weight exclusions.

No unresolved runtime contract conflict was found in the tested V2 SQLite
boundary. The three handoffs above concern evidence or submission integration
outside this worker's allowed edits; they are not claims that this local work
has been published, pushed, accepted by judges, or tested in a browser.
