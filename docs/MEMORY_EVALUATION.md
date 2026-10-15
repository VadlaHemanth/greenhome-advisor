# Chronological fictional customer-memory experiment, v1

**Authorised 10 October 2026 after the original reference protocol was frozen.**
This separate protocol supersedes the earlier *not performed* memory statement only for
the experiment described here. It does not alter the original required-output
cases, numerical targets, training protocol or earlier evidence.

### Freeze and evidence level

Eight new, explicitly fictional customers have one property/episode each,
four development and four test. Customer, episode and logical property IDs are
distinct before event expansion. Each private workspace contains four customers.
The application's four immutable `DEMO-01`–`DEMO-04` aliases recur in the other
private workspace: these aliases alone are **not** global property IDs.
Report grouping uses workspace/customer-scoped logical keys. There is no
training partition because nothing is fitted. Repeated designed archetypes do
not establish unseen-archetype or population generalisation.

The complete authored homes, events, recording times and eight query phases
per episode are embedded in `scripts/evaluate_memory.py`. Their canonical JSON
SHA-256 is pinned before the first candidate run and verified on every run.
The report includes that immutable specification plus source hashes before/after.
Targets are constraints from the written timeline, not outcomes fabricated by
calling a candidate. Eight episodes produce **64 paired queries** and a third
control arm (192 controller outputs if execution completes). These are eight
designed fictional customers, **not 64 independent participants**.

This evaluates retention and safe use of authored state through actual local
HTTP/store operations. It is not a user study, customer satisfaction or adoption
effect, empirical recommendation-quality study, financial benefit, measured
energy saving, property-value validation or learned memory model.

### Real operations and strict chronology

Use the existing `WorkspaceStore` and `create_workspace_router` in a standalone
FastAPI app, with two genuinely separate `TestClient` cookie jars and one
temporary file-SQLite database. Inject a strict fictional-home model rather than
importing the main API or loading its environment. The real router and real
engine validate writes/selections. The real `rank_homes` plus `screen_home`
form the same pure controller in every arm. Persistence must not invoke the
injected ranker. ML functions are explicitly stubbed; outbound socket connection
attempts raise and are counted. No secret/provider/network configuration, live
provider, artifact, production database or frontend is used.

For each episode, apply the fixed timeline:

1. Write the fictional intake and query **cold start**.
2. Update only review metadata and query **metadata only** (negative control).
3. Save a deferral, read it back, and query with a generic review request.
4. Save a changed budget, read it back, and query.
5. Save a feasible selected measure. Attempt a future-dated completion:
   expect HTTP 422 and exactly unchanged state; query **future rejected**.
6. Record the legitimate completion, then query **completed**. Its occurrence
   date is 9 October but it is first recorded on 10 October: it must not leak
   into earlier queries just because the occurrence date is earlier.
7. Attempt replacement fuel inputs without explicit post-completion
   confirmation: expect 422, unchanged state and continued abstention; query.
8. Explicitly confirm the authored replacement fuel inputs, then query
   **baseline refreshed**. These inputs are fictional numbers, not observed
   readings or model-generated savings targets.

The store clock advances monotonically through the fixed 10 October 2026
timeline. Every write precedes its query strictly. An independent reducer can
use only this episode's events whose **recording time is before the query**.
Rejected attempts have no effect. Compare actual persisted home, baseline
status and completion-event content/timestamps with that prefix; inspect actual
GETs before and after future-event rejection. Later committed events must not
alter already captured query inputs. No historical-as-of store API is implied.

The eight episodes cover loft, controls, glazing, PV and heat-pump completions;
gas, resistance and existing heat-pump heating; varied property types and
England/Wales regions; and confirmed listed-building consent. All completions
must remove the saved selected measure, update only its justified feature, and
invalidate both fuel totals until replacement is explicitly confirmed.

### Arms, fair comparisons and negative controls

All query wording means “Review my current plan”, without repeating prior facts.
The candidate controller is identical across arms:

- **With memory:** actual GET of the correct persisted customer's projected home.
- **Without memory:** the original fictional intake only. Past saved preferences,
  completions and replacement inputs are intentionally unavailable. This is a
  forgetful/intake-only baseline, not the strongest possible stateless service.
- **Re-entered current facts:** no store retrieval; independently replay the
  legitimate recorded prefix and give those current facts explicitly to the
  same controller. Equal outputs here demonstrate that fresh input, not a
  superior recommendation algorithm, explains the memory advantage.

Cold-start and metadata-only queries must show no artificial memory advantage.
These controls prevent counting a mere successful test or identical unchanged
output as improved recommendation quality. Also require known-baseline
availability after refresh: an always-abstaining controller must not win by
avoiding all recommendations.

### Predeclared metrics and denominators

For every query retain each arm's actual input, selected package, feasible
recommendations, status, costs and fuel/percentage availability. Report separately
for dev/test and together:

- Deferred-measure violations among queries with a nonempty deferral:
  neither chosen nor feasible-offered measures may include one.
- Budget violations among queries with a known current budget: independently
  sum upper catalogue costs of the chosen package; do not sum all alternatives.
- Repeated-completion violations among queries after a recorded completion:
  neither chosen nor feasible-offered measures may repeat it.
- Required fuel abstention after completion/unconfirmed refresh rejection:
  `insufficient_evidence`, empty chosen package and null potential, cost and
  per-fuel savings, not a fabricated numeric zero opportunity.
- Evidence-status correctness for every query: after confirmed current inputs,
  known opportunity or known zero must remain assessable.
- Exact input agreement with the legitimate prefix and all-applicable-constraint
  satisfaction. Pair the with/without results as memory-only satisfied,
  without-memory-only satisfied, both satisfied or both violated.

Expected applicability from the authored complete schedule is 48 deferral,
40 budget, 24 completed-measure and 16 fuel-abstention query occasions, plus
64 evidence-status checks. Actual denominators are computed from executed
records, not assumed if execution fails. These outcomes overlap and correlate;
do not add them as independent trials or manufacture confidence intervals.
The independent unit is an episode/customer, with no empirical statistical claim.

Operational/security checks are reported **separately**, not called memory
quality or outcome uplift: actual status codes; version increments; sibling
customer state invariance; rejected writes with no side effects; and restoration
through a separately constructed store reading the committed SQLite file.

### Privacy, scope and no future leakage checks

The primary run uses the real public-mode HttpOnly, Secure, SameSite=Strict,
host-only `__Host-` cookie and HTTPS TestClient URLs. Check cookie attributes
without logging the bearer value; verify a foreign-host request has no session,
HTTP requests are denied, and the Secure cookie is not sent over HTTP.
Separate local-mode unit checks inspect the `/api/workspace` cookie path.
TestClient is in-process: this verifies emitted attributes and cookie-jar
host/transport/path handling, **not actual browser JavaScript HttpOnly or browser
SameSite enforcement, TLS, proxy, CORS, bank authentication or a security audit**.

In both directions, the other private client attempts each episode customer's
GET, update and completion. Require actual 404s, no returned customer state and
both workspace snapshots unchanged. Check IDs are disjoint and tokens are only
hashed in SQLite. Within one workspace, the schema intentionally returns all
four authorised customers; there is no claim of separate adviser/customer roles
or isolation between those four authorised rows.

All credentials are newly generated disposable TestClient cookies. Never copy
browser or production credentials. Temporary SQLite/WAL files and cookies are
discarded after execution; no real customer data is present. Source changes
during execution require a rerun. Main API/proxy/UI and PostgreSQL are outside
this experiment.

### Running, outputs and preserved original freeze

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_memory_evaluation.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/evaluate_memory.py
```

Only `reports/memory_evaluation.json` is written by the evaluation command.
It includes actual requests/statuses, query/arm outcomes, paired counts,
failures, runtime guards and full source/specification provenance. A failed or
incomplete run must not be labelled successful. The parent can rerun after
concurrent workspace/ranking changes.

**Original freeze preserved:** `docs/EVALUATION_PROTOCOL.md` is restored byte-for-byte
to its original frozen SHA-256, as verified against the unchanged
`data/reference_cases_manifest.json`. This memory protocol is a separate file
with its own run-specific hash. No existing reference label or manifest is
changed, and the existing reference verifier requires no compatibility change.
The earlier document's memory-not-performed statement describes its original
freeze; this later, separately versioned experiment is the new evidence.
