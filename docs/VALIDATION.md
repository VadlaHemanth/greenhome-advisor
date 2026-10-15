# Release validation — 15 October 2026

This record distinguishes local verification from public deployment.

## Completed locally

- New tariff/package API and UI: tested explicit illustrative rates, unknown and
  zero prices, signed per-fuel money changes, package selection, stale-response
  rejection, cost/payback boundaries and safe error handling.
- Money API review findings were fixed: the parent injects its bounded
  calculation service; redundant costly alternatives are omitted while an
  explicit user selection is preserved with a warning.
- Adviser review findings were fixed: summary counts follow the visible filter;
  unavailable results are not represented as zero homes.
- Hosted configuration rejects missing/ephemeral database settings and
  normalises supported PostgreSQL schemes while preserving credentials.

### Test receipts

| Scope | Actual result |
|---|---|
| Full release working-tree backend run, before final three configuration regression cases | 1,298 passed |
| Exact staged public-file checkout, excluding explicitly marked data/archive-dependent checks | 1,286 passed, 1 skipped, 14 deselected |
| Built public-checkout security/readiness tests, including the previously skipped asset check | 20 passed |
| Frontend suite before release-identity panel | 328 passed in 27 files |
| Latest frontend suite including release-identity panel | 330 passed in 28 files |
| Latest release metadata/API/hosted/money checks | 204 passed |
| Final React/TypeScript production build | Passed |
| Independent scoped review of adviser/configuration fixes | 7 frontend and 12 configuration tests passed |

Counts overlap and must not be added. The data/archive-dependent tests validate
raw dataset and historical experiment hashes that are deliberately not all
republished. README commands explicitly exclude those groups for a clean
checkout and explain their requirements; they are not reported as passing.

### Browser checks

A fresh isolated local browser captured 12 principal views at 1440×900 and
390×844: entry, dashboard, score, inputs, improvements, selected results, money,
explanation, adviser, workspace, plan and evidence. It exercised local
workspace reload, reported zero page errors, and found no document-wide
horizontal overflow in those captures. Additional landing-page checks ran at
320px and 768px.

The reviewed money fixture was DEMO-01 with loft insulation and heat pump:
25p electricity and 7p gas are **explicitly illustrative**, giving £2,040 before,
£1,946 after and £94/year variable-charge saving. Live providers were not called.
These are software and scenario checks, not measured household outcomes or
participant research.

### Local PostgreSQL and hosted-mode checks

The actual application was exercised against a task-created PostgreSQL 18.6
database, using HTTPS TestClient requests. Twelve checks passed: readiness,
explicit workspace consent, Secure/HttpOnly/SameSite cookie flags, plan save,
stale-version rejection, cross-origin rejection, wrong-host rejection, distinct
workspaces, cross-workspace read/write rejection, shared provider-budget
admission, and restoration of the saved plan after both database and application
restart. No live provider call was made. The task database was stopped after
verification; no existing database or service was stopped.

This establishes that the existing PostgreSQL adapter worked in this local
test. It does not replace the pending hosted connection, pooler, ingress,
restart and persistence checks.

### Deployment identity

`/api/release` now exposes only the app name, release version, validated Git
revision (or null), and local/hosted indicator. Reports shows this metadata.
Missing metadata stays explicitly unknown, and arbitrary environment values
are not returned. The identity panel is not an uptime or correctness guarantee.

### Local Vercel builder

The exact public application at revision `0bb8815` was built through the
installed official Python builder with the larger-function capability enabled
locally. The output contains both unchanged trained model files, required API
modules and 23 frontend assets. Function files measured approximately 342 MiB.
The default local packaging mode did not fit; `docs/HOSTING.md` records this
constraint and the distinction between local capability simulation and actual
free-account eligibility. No cloud deployment or database was created by the
build check.

## Not yet established by this record

- Successful public deployment of this revision.
- Production HTTPS ingress, database persistence across hosted restarts, or
  hosted multi-client isolation.
- Final deployed desktop/mobile screenshot set.
- Production capacity, SLA, accessibility certification or real property-value
  accuracy.

The hosting configuration is prepared for an eligible free personal demo with
durable Postgres. Account authorisation and database provisioning must succeed
before deployment can be declared complete. A public GitHub repository is not
proof of a working hosted application.
