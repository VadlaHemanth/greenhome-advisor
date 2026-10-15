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
| Final frontend suite | 328 passed in 27 files |
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
