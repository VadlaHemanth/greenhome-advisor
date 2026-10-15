# Fictional customer → property memory — Team 225

Schema 2 implementation and validation date: **11 October 2026**. England and Wales
demonstration; monetary inputs are GBP. This is not a bank account, an identity
provider, a real customer record system, or a shared multi-user adviser service.
“Adviser” and “customer” are views of the **same private browser workspace**.

## Integration boundary

The parent registers the router; these modules do not import or modify the main
API, frontend, explanation layer, model artefacts, or ranking implementation:

```python
from greenhome.workspace_api import create_workspace_router

app.include_router(create_workspace_router(HomeInput, rank_homes))
```

The prefix is already `/api/workspace`; do not add it a second time.
The final frontend probes `GET /api/workspace/session`, which returns a validated
workspace or JSON null with HTTP 200. This treats a normal anonymous visit as an
empty session, not an error. Invalid/expired cookies are cleared. Existing
private GET/export/write routes still require a valid scoped cookie and reject
unauthorised access; no workspace is implicitly created by the probe.
`home_model` is the parent's Pydantic HomeInput class. It is narrowed to require
`data_kind="synthetic_demo"` and an immutable home reference: original
`DEMO-01`–`DEMO-04` IDs are preserved; added homes use `PROP-` followed by
32 random lowercase hex characters. Each property also has a distinct opaque
resource ID and an immutable customer owner. The model includes `excluded_retrofits`, retaining strict
HomeInput validation. Unknown request fields, notes, addresses, prose, uploads,
and non-fictional homes are rejected. A fictional flag is an explicit demo
restriction, **not a way to verify that arbitrary numbers are actually fictional**.
Do not enter real household/customer data.

The factory accepts the injected callable `ranker` but deliberately does not
invoke it on persistence reads/writes. No ranking, savings, model inference
output, generated prose, or explanation is persisted. The parent-owned
`/api/rank-homes` remains the ranking endpoint. Saved homes already carry their
effective budget and exclusions, so their reuse in ranking/assessment is
consistent. `priority` and `disruption` never change the mandated energy-ranking
metric. Selection feasibility is validated through `engine.assess`; this can
perform local model inference, but never a provider call.

`router.workspace_store` exposes the store for startup, disposal and maintenance,
not through HTTP. **Call public `store.warm()` once in each worker's lifespan
before yielding readiness.** It initializes schema/WAL and verifies schema
version plus exact owned-table column names, types and nullability using
`_ensure_engine` only, with no workspace/customer rows or opt-in fabricated.
Schema 1 is migrated transactionally after full schema/row validation; schema 2
is validated on each new worker startup. **Stop every old-schema worker before
warming the replacement release.** Initialization errors are sanitized and fail
that worker's startup.
Example integration inside the parent's app factory:

```python
workspace_router = create_workspace_router(HomeInput, rank_homes)
workspace_store = workspace_router.workspace_store

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(workspace_store.warm)
    try:
        # Preserve the parent's other readiness/startup checks here.
        yield
    finally:
        await asyncio.to_thread(workspace_store.close)

app = FastAPI(lifespan=lifespan)
app.include_router(workspace_router)
```

Merge this into the existing lifespan; do not replace the parent's existing
calculation/provider service setup/teardown. Do not signal readiness before
warmup succeeds. `store.close()` disposes connections. `store.prune_expired()`
removes expired live rows and returns the deleted workspace count. The parent
may call these from its lifecycle/maintenance machinery; no background task,
automation, or external deployment is created here.

## Configuration and dependencies

Only `SQLAlchemy==2.0.54` is added to required project dependencies. It was
installed into the existing `.venv`; unrelated requirements are unchanged.

| Environment variable | Default | Accepted limits / meaning |
| --- | --- | --- |
| `GREENHOME_WORKSPACE_DATABASE_URL` | Absolute file SQLite URL for `state/workspaces.sqlite3` in the project | `sqlite:///...`, `sqlite+pysqlite:///...`, or `postgresql+psycopg://...` |
| `GREENHOME_WORKSPACE_MAX_WORKSPACES` | `1000` | Integer 1–1000 active workspaces per database |
| `GREENHOME_WORKSPACE_MAX_CREATIONS_PER_DAY` | `1000` | Integer 1–1000 new workspaces per UTC day, global to the database |
| `GREENHOME_PUBLIC_MODE` | `false` | Existing explicit project boolean setting; public mode requires HTTPS and Secure cookies |
| `GREENHOME_ALLOWED_ORIGINS` | Localhost / 127.0.0.1 ports 5173, 8000, 4173 locally; empty extra allowlist publicly | Exact trusted origins, never `*`; current request origin is also accepted |

Use the **same URL and quota settings in every worker**. SQLAlchemy engines
are lazy: constructing the router or rejecting a missing cookie does not
create a workspace or database file.

Example local configuration:

```sh
export GREENHOME_WORKSPACE_DATABASE_URL='sqlite:////absolute/service-owned/state/workspaces.sqlite3'
```

SQLite must be a regular persistent file; memory databases, SQLite URI query
options, database symlinks and hard-linked database files are rejected. A new
storage directory is created with mode `0700`; the database is mode `0600`.
Existing parent-directory permissions are not silently changed. Put it in a
dedicated service-owned directory, not an untrusted/shared filesystem.
SQLite has foreign keys, `secure_delete`, synchronous FULL and a five-second
lock timeout enabled on each connection. WAL is configured once during engine
initialization, not on every read/connection. Connections use `NullPool`.
Writes use `BEGIN IMMEDIATE`; GET/export/customer GET use read-only `BEGIN`
transactions with `PRAGMA query_only=ON` and one snapshot SELECT. They do not
take the writer lock or prune expired rows. WAL permits a reader to finish
while another connection has an uncommitted write; readers see committed state.
Keep the database and its SQLite `-wal` / `-shm` sidecars together on a suitable
single-host local filesystem.

A per-store/process write-admission lock limits native SQLite writer contenders;
it waits at most five seconds and returns safe 503 `workspace_busy` if full.
This is an efficiency control, **not cross-process authorization/locking**.
The database still owns atomic quota and version checks across processes.
Reads bypass this admission queue. There are no automatic write retries,
version rebases, or “last write wins” fallbacks. Local operation is bounded,
not an unlimited-throughput or sustained-availability claim.

### Optional PostgreSQL configuration — not runtime-tested

For an operator choosing PostgreSQL, install the optional Psycopg 3 driver
using the existing environment:

```sh
.venv/bin/python -m pip install 'psycopg[binary]>=3.2,<4'
# Supply the actual URL privately via the environment or ignored .env:
export GREENHOME_WORKSPACE_DATABASE_URL='postgresql+psycopg://localhost/greenhome'
```

The example contains no credential. Never put a credential-bearing URL in
source, a chat, a log, or an export. Use a dedicated least-privilege database
role and an operator-managed TLS/backup configuration. Public remote database
connections should require certificate/hostname verification, e.g. the
operator's `sslmode=verify-full` and trusted CA configuration. No PostgreSQL
service, role, account, or remote connection was created by this task.

The PostgreSQL path uses standard SQLAlchemy Core tables, parameterized SQL,
foreign-key cascades, workspace and customer row locks, and atomic versioned
customer/property UPDATEs. Sibling allocations share the same customer lock.
A transaction-scoped advisory lock serializes initial schema creation.
Connection/pool/lock waits are five seconds; statement timeout is ten seconds.
The pool is capped at five connections per process with no overflow.
The schema and versioned UPDATE were **compiled for the PostgreSQL dialect
only**. The Psycopg driver was not installed, and PostgreSQL connectivity,
transactions, migrations, TLS and concurrent runtime behaviour were **not
tested**. These remain deployment validation requirements, not proven results.

## Privacy, consent and lifetime

- `POST /api/workspace` requires the JSON boolean `consent: true`, even when
  returning an existing workspace. There is no implicit creation on GET.
- Four customers are created with one fictional property each. Customers have
  generated IDs and labels `Example household 1` through `4`. Each customer can
  add up to eight properties from the four engine templates, with fresh resource
  and home IDs, neutral property preferences except the template budget, and
  empty selection/history. Edited bills, events and preferences are never copied
  from another saved property.
- Tokens contain 32 random bytes encoded as 43 URL-safe characters. Only a
  SHA-256 digest is stored. The cookie token is never put in response JSON,
  database rows, exports, URLs, or application logs.
- Local cookie: `greenhome_workspace`, `Path=/api/workspace`.
  Public cookie: `__Host-greenhome_workspace`, `Path=/`, `Secure`.
  Both are host-only, `HttpOnly`, `SameSite=Strict`, `Max-Age=2592000`.
  The public `__Host-` prefix also forbids browser Domain/path overrides.
- The fixed server expiry is exactly 30 days from creation. Reads, repeated
  opt-in, edits and completions do **not** extend it. Server expiry is decisive
  even if a client replays an old cookie. Public mode accepts HTTPS directly or
  the exact boolean ASGI scope flag
  `scope["greenhome.authenticated_gateway"] is True` on a TLS-terminated hop.
  The parent owns middleware that sets this flag **only** after checking a
  loopback peer and the server gateway token injected by the authenticated
  gateway. This router never infers it from a request header.
  Plain HTTP without that verified flag remains 403; raw `Forwarded`,
  `X-Forwarded-Proto`, `X-Forwarded-For`, or similarly named flag headers cannot
  bypass the check. Public cookies remain Secure and `__Host-` prefixed on both
  permitted paths. The parent runs with `--no-proxy-headers` and owns actual
  gateway authentication, stripping/injection and origin configuration.
- Cookie possession is the only workspace credential. Knowing a workspace ID,
  customer ID, demo property ID or exported file is insufficient. There is no
  workspace-by-ID login, import, recovery link, role switching or shared access.
  Losing the cookie loses browser access. Anyone who steals the bearer cookie
  can access that fictional workspace until expiry/deletion.
- All reads, writes, export and deletion are scoped to the hash-authenticated
  workspace. Another workspace's customer ID receives the same 404 as an
  unknown ID. Missing/expired/malformed credentials receive 401 and cookie
  removal.
- Origin checks, rejection of `Sec-Fetch-Site: cross-site`, JSON-only writes,
  and SameSite cookies protect the browser boundary. Browser writes are
  non-simple JSON requests; the parent must retain its strict CORS/Host
  boundary, not grant arbitrary credentialed origins. No-origin CLI requests
  still require the private cookie. This is not general-purpose bank auth.
- The router applies `Cache-Control: no-store`, `nosniff`, and `no-referrer`
  to success and error responses. Request/database error text and validation
  inputs are not reflected or logged. Export is JSON attachment only.

Expiry is enforced on every authenticated operation: after fetching a read
snapshot or acquiring a write lock. Expired credentials always fail immediately
even when old rows await physical cleanup. GET/export/customer GET never run
cleanup. Creation prunes inside its existing write transaction at most once
per minute per store/process, **or unconditionally when the physical row count
reaches the configured capacity**. Thus a throttle hint cannot block reusable
capacity or bypass the row bound. Other writes do not opportunistically prune.
Explicit `prune_expired()` performs a maintenance sweep with cascades.
**An idle service does not run a background expiry sweeper**; schedule that
method in parent-controlled maintenance if prompt physical removal is required.
Deletion removes live
database rows and revokes the cookie; it is not a claim of forensic erasure
from SSDs, operating-system snapshots or operator-managed backups.

The global daily quota survives deletion, so repeatedly creating/deleting a
workspace cannot reset that quota. Its singleton counter has no customer data
or token. Quotas bound records, not admission fairness; a public anonymous
pilot can exhaust the global allowance. Parent gateway/rate limits and disk
monitoring remain necessary.

## Schema 2 HTTP contract

The authoritative release shape is `docs/MULTI_PROPERTY_CONTRACT.md`. All request
models remain strict, finite-number-only, extra-forbidden JSON; writes are capped
at 16 KiB with a ten-second body-read deadline. No route accepts query parameters.
No numerical assessment, ranking, model prose, identity or bank data is persisted.

Paths below are relative to `/api/workspace`. Successful reads/mutations return
the whole private workspace, except nullable `/session` and `{"deleted":true}`.

| Method/path | Input / behaviour |
| --- | --- |
| `GET /session` | Workspace or null; no implicit opt-in |
| `GET ""`, `GET /export` | Existing scoped workspace; export is a JSON attachment |
| `POST ""` | `{"consent":true}`; create/return the same fixed-expiry workspace |
| `POST /delete` | `{"confirm":true}`; revoke cookie and cascade all customers/properties |
| `GET /customers/{cid}` | Scoped customer lookup |
| `GET /customers/{cid}/properties/{pid}` | Both identities must match the private workspace; wrong owner → 404 |
| `POST /customers/{cid}/properties` | `{customer_version, template_id}`; template is exactly `DEMO-01`–`DEMO-04` |
| `POST /customers/{cid}/settings` | Customer settings below |
| `POST /customers/{cid}/properties/{pid}` | Complete versioned property save below |
| `POST /customers/{cid}/properties/{pid}/events` | Versioned completion below |
| Legacy `POST /customers/{cid}` and `/events` | Only exactly one property; otherwise 409 `property_required` |

### Canonical response and compatibility

```text
workspace = {id, schema_version:2, mode:"fictional_demo", expires_at, customers, note}
customer = {
  id, label, version, updated_at,
  customer_preferences:{deferred_retrofits:[], priority:"energy", disruption:"flexible"},
  portfolio_budget_gbp:null,
  legacy_completed_reserve_gbp:0|null,
  budget_summary:{planned_upper_gbp, completed_reserved_gbp, total_reserved_gbp,
                  remaining_gbp, status},
  properties:[{
    id, customer_id, label, version, updated_at,
    home, preferences, selected_retrofits, review_status, baseline_status, events
  }]
}
```

`status` is `unlimited`, `within_budget` or `needs_cost_evidence`. Customer settings
are canonical at the customer root; home facts, individual budgets/preferences,
selections, baseline and history are canonical **only on properties**. For exactly
one property the six former root fields remain deprecated read-only projections.
No root home/history projection exists for multiple properties. Legacy writes use
the customer version and increment both versions of the sole child/parent.

Property labels are server-generated `Example property N`. Resource IDs are
32-character lowercase hex strings; `home.property_id` is a separate immutable
reference unique within the workspace. The child has a real database relationship
to its owner, not just an owner label or nested JSON. Ownership cannot be submitted,
transferred or deleted through a property endpoint in this release.

### Property save

```text
{
  customer_version: integer 1..2147483647,
  version: integer 1..2147483647,
  home: HomeInput,
  preferences: {
    budget_gbp: finite number 0..1000000000 | null,
    deferred_retrofits: distinct RetrofitId[] (maximum 5),
    priority: "energy" | "carbon" | "low_cost",
    disruption: "flexible" | "minimal"
  },
  selected_retrofits: distinct RetrofitId[] (maximum 5),
  review_status: "new" | "reviewing" | "ready" | "deferred",
  baseline_confirmed_after_completion: boolean = false
}
```

All fields except the explicit baseline confirmation are required. Property
preferences own the home's individual budget and exclusions. Raw property
preferences stay separate; effective response/assessment homes union property and
customer exclusions. Customer settings do not rewrite sibling JSON or increment
sibling versions. Customer priority/disruption are discussion preferences, never
ranking weights. The shared cap is not projected into an individual home budget.
Engine feasibility and the individual upper-cost budget remain enforced on saves.

### Customer settings and shared allocation

```text
{
  version: integer 1..2147483647,
  customer_preferences:{deferred_retrofits, priority, disruption},
  portfolio_budget_gbp: finite number 0..1000000000 | null,
  legacy_completed_reserve_gbp: finite number 0..1000000000 | null,
  confirm_legacy_reserve: boolean = false
}
```

Both monetary fields and all customer-preference fields are required. Altering a
legacy reserve requires explicit confirmation, including an intentional zero.
A confirmed reserve cannot be reset to unknown. This records the operator's
planning declaration, not verified spending.

Allocation is the sum across **all properties of this customer** of:

1. Upper catalogue costs of active saved selections.
2. `planning_cost_upper_gbp` captured in new completion events.
3. The customer's explicitly recorded aggregate legacy reserve.

Unknown legacy cost evidence makes completed/total reserved amounts null and
status `needs_cost_evidence`, even with an unlimited cap. Known new reservations
are still retained. No finite shared cap is accepted until the old aggregate
reserve is explicitly confirmed. Unlimited caps still report known totals.
A cap below allocation returns 409 `portfolio_budget_exceeded`; unknown costs with
a finite cap return 409 `needs_cost_evidence`. New universal exclusions conflicting
with any saved plan return 409 `exclusion_conflict`. Nothing is silently dropped.

### Completion, dates and preventing double counting

```text
{
  customer_version: integer 1..2147483647,
  version: integer 1..2147483647,
  kind:"completed", retrofit_id:RetrofitId,
  completed_on:"YYYY-MM-DD", confirmed:true
}
```

Every field is required. Only a saved selected measure can be completed, never a
duplicate. `completed_on` must be a real date no later than **Europe/London today**;
during BST London can be one calendar day ahead of UTC. Server `created_at` is
UTC ISO-8601 with a `Z` suffix. Occurrence dates may be backdated but do not rewrite
recording time. Migration validates occurrence against its recording-time London
date and validates recording timestamps against the owning row's lifetime/history.

The same atomic transaction adds `{id,kind,retrofit_id,completed_on,created_at,
planning_cost_upper_gbp}`, removes the measure from selection, and sets only its
justified feature. The captured upper estimate is **not actual expenditure**.
Replacing a selected upper cost by an equal completed reservation leaves shared
allocation unchanged. No aggregate or realised energy saving is stored or added.

| Measure | Recorded installed feature; allowed later compatible state |
| --- | --- |
| Loft insulation | `insulation="good"` |
| Double glazing | `glazing="double"`; later triple is allowed |
| Smart controls | `smart_controls=true` |
| Solar PV | `solar_kwp=3.0` package assumption; later positive capacity is allowed |
| Heat pump | `heating="heat_pump"` |

Only the target's electricity/gas figures become null and its baseline becomes
`needs_update`. Sibling facts, selections, history and versions remain unchanged.
Remaining measures in the already saved package may be completed while fuels are
unknown: completion does **not** reassess the unfinished package or invent bills.
A later home save still follows normal engine selection validation. Returning both
known fuels (including explicit zero) requires explicit replacement-baseline
confirmation; partial fuels cannot be confirmed and remain `needs_update`.

A completed measure cannot be selected again, including after manual feature edits
or baseline replacement. Saves cannot regress/remove a recorded installed feature.
There is no correction/de-installation workflow in this release. These rules apply
to canonical and legacy saves. Migration rejects contradictory old histories,
rather than silently resetting them or calculating their savings again.

### Atomic storage, limits and errors

SQLite mutations retain finite-wait `BEGIN IMMEDIATE`. PostgreSQL uses the
workspace lock (also protecting deletion), a customer `FOR UPDATE` lock and
versioned customer/property UPDATE predicates. Every add, settings change, legacy
write, property save and completion checks allocation under this same transaction.
Canonical property mutations check **both versions**, increment both, and leave
sibling versions unchanged. Add/settings change only the parent version (new child
starts at 1). Failed validation, stale versions or budget checks roll back all
state, versions and events; no automatic retry/rebase occurs.

GET/export/scoped GET retain one joined snapshot SELECT across workspace, customer
and properties; no writer lock, cleanup or partial owner/child snapshots.

Errors keep the existing static `{detail:{code,message}}` shape. In addition to
existing 401/403/404/408/409/413/415/422/429/503 boundaries, 409 includes
`property_required`, `property_limit`, `exclusion_conflict`, `needs_cost_evidence`
and `portfolio_budget_exceeded`. No cookie/hash, SQL or validation input is echoed.

## Persistent schema 2 and migration

The original `workspaces` table is unchanged: opaque ID, unique token hash,
created/expiry UTC integer seconds and fixed 30-day expiry constraint.
`workspace_control` retains its singleton, UTC creation-day counter and quota;
its schema-version CHECK now requires 2.

`workspace_customers` retains original IDs, workspace FK/cascade, slots 1–4,
versions, update timestamps and bounded `state_json`. Its JSON now contains only
`customer_preferences`, `portfolio_budget_gbp`, `legacy_completed_reserve_gbp`.
A new unique index on `(id,workspace_id)` supports the composite child FK.

`workspace_properties` columns are all NOT NULL:

| Column | Type / constraint |
| --- | --- |
| `id` | VARCHAR(32), primary key |
| `customer_id` | VARCHAR(32), indexed |
| `workspace_id` | VARCHAR(32) |
| `slot` | INTEGER, 1–8, unique `(customer_id,slot)` |
| `home_id` | VARCHAR(64), unique `(workspace_id,home_id)` |
| `version` | INTEGER, 1–2147483647 |
| `state_json` | TEXT, at most 16384 bytes of ASCII-escaped JSON |
| `updated_at` | BIGINT, UTC epoch seconds |

The real composite FK `(customer_id,workspace_id)` references
`workspace_customers(id,workspace_id) ON DELETE CASCADE`; workspace deletion and
expiry pruning cascade through both levels. State JSON contains the original six
property fields. Events remain transactionally embedded in that property's row,
bounded at 20; the five distinct measures also prohibit duplicates. At maximum
configured capacity there are 1,000 workspaces, 4,000 customers, 32,000 properties.
Property JSON alone can total 524,288,000 bytes before customer JSON, SQL indexes,
WAL and file overhead. This is a record bound, not a whole-database disk quota.

### Upgrade procedure and safeguards

1. The operator/parent stops **all old-schema workers** before replacing the schema.
   Do not run schema-1 and schema-2 code against the same database concurrently.
2. The parent-owned `scripts/migrate_workspaces.py` requires explicit stopped-worker
   confirmation and saves an integrity-checked private backup in `state/backups`
   before calling `store.warm()`. This backend task never invokes it on live data.
3. Under SQLite's write lock or PostgreSQL's transaction-scoped advisory lock,
   inspect exact columns, PK/FK/unique/index/check constraints and **every row**.
   Unknown schemas, partial tables, malformed/duplicate-key JSON, invalid values,
   dangling owners, duplicate IDs, inconsistent history or missing customers abort.
4. Before any SQLite migration DDL/DML, the store independently snapshots committed
   WAL data to an exclusive mode-0600 sibling file named
   `<database>.schema1-<random>.sqlite3`, verifies integrity and fsyncs it. Failure
   prevents migration. Keep this private backup out of commits/exports/submissions.
5. Create one deterministic child ID per original customer (SHA-256 of
   `greenhome:property:v2:<customer_id>`, first 32 hex characters). Copy the exact
   old `state_json` string without normalizing original home facts/permissions,
   selections, preferences, baseline or event IDs/dates. Copy the original version
   and timestamp to the child, leaving the parent's originals unchanged.
6. Initialize neutral customer preferences and a null portfolio cap. Old property
   budgets/exclusions are **not promoted**. Any completion lacking a captured
   reservation makes the legacy aggregate null; do not price old work from today's
   catalogue. Customers without such history start with reserve 0.
7. Replace the singleton's schema-version CHECK while retaining its quota/day
   values. Validate the complete v2 schema and every migrated row before commit.
   DDL and all copied/updated rows roll back together on failure. The verified
   pre-upgrade backup remains. Cookies, workspace/customer IDs, expiry and raw
   historical facts survive; expired rows are validated/preserved, not pruned by
   migration. No lossy reset or import endpoint exists.

Concurrent warmers serialize at the database lock, so later workers see/validate
v2 rather than copying again. Repeated warmup and a separate v2 restart create no
additional children or migration backups. PostgreSQL uses compatible SQLAlchemy
Core DDL/transactions but has **no live PostgreSQL validation evidence** here.

## Schema 2 validation (11 October 2026)

All backend tests use temporary SQLite files and fictional inputs. API tests use
an offline ML stub and forbid provider calls. No production server was started or
stopped, no live workspace database migrated, and no identity/account/publication
operation performed by this backend worker. The parent owns live backup/migration,
UI integration and the separate ownership dataset/evaluation.

Focused command:

```sh
.venv/bin/python -m pytest tests/test_workspace_api.py tests/test_workspace_store.py tests/test_workspace_backup.py tests/test_multi_property*.py -q
```

Required backend command:

```sh
.venv/bin/python -m pytest tests/test_engine.py tests/test_engine_audit.py tests/test_ml.py tests/test_explain.py tests/test_api.py -k "not apptest" -q
```

Measured final runs: **192 focused tests passed in 22.79 seconds** and
**330 backend regression tests passed in 10.83 seconds**. Neither run reported
failures, skipped tests, xfails or xpasses. Python compilation of the three
workspace modules and five owned API/store/migration test files succeeded;
scoped `git diff --check` succeeded. These are local offline results, not a
live upgrade or PostgreSQL runtime claim.

The focused suite covers 1/2/4/8-property HTTP flows, fresh template identities,
wrong-owner lookups/writes, exact-one compatibility, both versions, exclusion
unions, independent budgets, shared-cap reductions/reservations, unknown legacy
cost evidence, simultaneous sibling HTTP/process writes, completion/settings/add
races, target-only fuel invalidation, unfinished-package completion, all installed
feature replay guards, London/UTC date boundaries, export/delete cascades and
real composite-FK enforcement. Frozen independent v1 DDL fixtures cover pristine,
pending, restored-baseline and fully completed histories, exact raw JSON/cookie/ID/
expiry preservation, corrupt-row rejection, post-DDL rollback, expired-row
preservation and three independent concurrent warmers. PostgreSQL checks are
SQL compilation plus a documented reflection-shape simulation, **not runtime**.

## Historical single-property validation (10 October 2026)

The following retained results concern the earlier single-property release, not
new customer-ownership validation or a rerun of the HTTP workload.

Tests use generated temporary SQLite files, fictional engine homes, an offline
ML stub for API tests, and a Gemini transport that fails the test if invoked.
They do not use real home records, a provider credential, a provider call,
browser UI automation, or an external deployment.

Commands:

```sh
.venv/bin/python -m pytest tests/test_workspace_api.py tests/test_workspace_store.py -q
.venv/bin/python -m pytest tests/test_engine.py tests/test_engine_audit.py tests/test_ml.py tests/test_explain.py tests/test_api.py -k "not apptest" -q
```

Coverage includes two private clients; cookie/hash/public HTTPS attributes;
exact verified-gateway flag acceptance and raw-forwarded-header rejection;
explicit consent and delete confirmation; cross-workspace customer GET/write/
event denial; exact export shape; independent process restart; fixed expiry
and cascade cleanup; malformed/private-input non-reflection; body/state/event/
version/quota bounds; concurrent separate-process cold initialization and
quota reservation; separate-process optimistic updates; deletion/update and
completion/update races; read-only SQL with no pruning/owner locks; a reader
completing before an open write is committed; bounded write-admission timeout
without mutation; throttled cleanup with forced capacity reclamation; isolated
100-thread create/300-read bursts using one and two store instances; a separate
two-process burst with 50 threads per process; engine feasibility/budget/deferrals; every completion
feature; no future date; partial baseline and explicit replacement confirmation.
PostgreSQL coverage is DDL/UPDATE compilation, **not runtime proof**.

The pre-optimization parent HTTP diagnostic recorded 31/100 successful
workspace creations and 20/31 successful subsequent reads, with the other
workspace operations receiving 503; it recorded **no actual cross-owner
responses**. The 69 reads following failed creations correctly received 401.
This prompted removing GET write locks/pruning and introducing WAL and write
admission. The parent's harness and reports were inspected, not changed.
The parent's later **partial-WAL** HTTP run recorded 39/100 successful creations,
39/39 successful reads of created workspaces, and 30/39 successful deletions;
the remaining writes were 503. All 500 calculation requests passed. This
confirms progress on reads, **not a passing end-to-end workload**.
The parent owns the post-final-change/per-worker-warmup HTTP burst; local
database tests are not a claim that that complete HTTP workload has passed.
If writes still fail, record the static error code (`workspace_busy` admission
timeout versus `workspace_unavailable` database error) before changing limits.
Keep any further admission queue finite and off the event loop, and never
automatically retry a possibly completed write or bypass optimistic versions.

Final measured results on 10 October 2026:

- Final workspace API/store suite, including warmup/schema checks:
  **103 passed in 11.70 seconds**.
- Required backend regression command: **330 passed in 11.10 seconds**.
- Python compilation of both modules and both test files succeeded; scoped
  `git diff --check` succeeded.
- Three additional isolated bursts each used **100 concurrent threads, two
  store instances sharing one SQLite file, 100 creations and 300 reads**.
  All three trials completed every operation and every exact workspace match
  without a 401, 409, 429, 503, ownership mismatch or retry:

  | Trial | Total seconds | Workflow p95 seconds | Workflow maximum seconds |
  | --- | ---: | ---: | ---: |
  | 1 | 0.999 | 0.885 | 0.911 |
  | 2 | 0.948 | 0.850 | 0.885 |
  | 3 | 1.177 | 1.024 | 1.068 |

  Workflows were creation plus three reads, using full fictional demo homes.
  These timings exclude HTTP, main-app middleware and concurrent model
  workloads. They are not a forecast for production or the parent HTTP rerun.
- The suite separately passed the **two spawned processes × 50 threads**
  creation/read test, with 100 distinct workspaces and matching reads.

The existing Starlette warning that its httpx TestClient adapter is deprecated
was observed; no unrelated HTTP-client dependency was changed.

## Dependency documentation consulted

### Final HTTP integration

The parent added a per-worker bounded mutation executor: one writer for local
SQLite (four for PostgreSQL configuration), capacity 128. This avoids consuming
the general HTTP thread pool with many threads waiting on SQLite's single
writer. Reads keep their read-only path. No write is automatically retried and
in-flight work is not abandoned merely because a caller times out.
Storage warm-up runs before traffic and its pool closes at shutdown.

After this integration, two local HTTP runs each completed 100 separate
workspaces and 800 recorded requests, all HTTP 200 with matching scoped reads
and successful deletion. This is an explicitly limited burst/workflow result.
The earlier failing diagnostics are retained, not erased.

Current official SQLAlchemy 2.0, FastAPI and Psycopg 3 documentation was queried
through Context7 during implementation:

- SQLAlchemy version-counter conditional UPDATE / row-count semantics,
  explicit `Engine.begin()` transactions, SQLite transaction-control events,
  foreign-key connection pragmas, custom transaction execution options, and
  PostgreSQL read-only transactions.
- FastAPI strict/extra-forbidden Pydantic request models and router integration.
- Psycopg 3 optional binary installation and libpq connection keyword options.

This is implementation evidence, not a PostgreSQL runtime or security
certification. Parent API/CORS/proxy integration and frontend confirmation/
unsaved-change UX remain owned by the other build workers.
