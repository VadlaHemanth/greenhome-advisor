# Release validation — 15 October 2026

## 16 October upgrade — local verification

The current/proposed interactive geometry, 200-home fictional catalogue and
shared dashboard bill comparison have been implemented. The original training
artifacts, four seed homes and private workspace limits are unchanged.

| Check | Actual result |
|---|---|
| Full backend suite excluding explicitly marked training/archive dependencies | 1,339 passed; 14 deselected |
| Full frontend suite | 448 passed across 35 files |
| TypeScript/Vite production build | Passed |
| Local desktop/mobile workflows, including six building families | 58 checks; 20 screenshots; 0 JavaScript page errors |
| Additional browser touchscreen, friendly-region search and zero-rate checks | 5 passed |

These counts overlap earlier scoped tests; do not add them. Browser checks
covered 320/390/768/1280/1440 widths, linked camera controls, pointer drag,
shared rates between Dashboard and Costs & packages, missing and negative
savings, home switching, static catalogue pages and no continuous idle
animation-frame loop. Touchscreen input was Chrome emulation, not a
physical-device study.

The local browser reproduced £2,040 → £1,946 and £94/year at the explicit
illustrative 25p/7p rates, and −£8/year for heat pump alone. An additional
regression withholds proposed geometry when the selected package has no valid
assessment. The independent integration review found no blocking issue; its
friendly-region search finding was fixed and tested.

The 200-example catalogue has 200 unique physical-input fingerprints, six
building families, 180 numerically assessed cases and 20 evidence-needed or
unsupported cases under its fixed snapshot. These are authored demonstrations,
not measured homes, a population sample, additional model training or new
accuracy evidence. Details are in `docs/DEMO_CATALOGUE.md`.

**Hosted status for this upgrade:** pending the final deployment verification.
The completed hosted evidence below still refers to the earlier application
revision. Do not treat local screenshots or a successful build as proof of a
new public deployment.

This record distinguishes local verification from checks on the actual public
deployment. Counts overlap and must not be added.

## Public deployment verified

**URL:** `https://greenhome-advisor-xi.vercel.app`

**Application revision:** `754b5fbfe1ff6de346ed2523c07224c24872a36e`

Verified on 15 October 2026 using Vercel Hobby and Neon Free (London).
Documentation/evidence commits after this application revision do not change
the deployed application. `/api/release` and the Reports screen expose the
application revision; a Git push is not an automatic deployment.

| Public check | Actual result |
|---|---|
| HTTPS API and isolation checks | 27 passed |
| Same saved workspace, customer, property and selection after production redeployment; source unchanged | 5 passed |
| Isolated browser workflows on the production alias | 42 checks; 24 screenshots; 0 JavaScript page errors |
| Focused live keyboard and tariff error-state checks | 12 passed |
| Principal viewport captures | 1440×900 desktop and 390×844 mobile |
| Additional overflow checks | 320px and 768px on start, money, reports and homes |
| Live model-provider calls during hosted verification | 0 |

The API checks cover health/readiness/release identity, anonymous entry,
blocked private-file and OpenAPI paths, signed energy/carbon and currency
results, negative saving without payback, missing-tariff abstention, invalid
input rejection, user-entered value abstention, local explanation, consent and
secure cookies, plan save/stale-version rejection, separate-workspace read/write
isolation, cross-origin rejection, own-workspace export and fresh-session
isolation. Only generated fictional data was used.

Safe receipts contain no credentials, cookies, connection strings or workspace
identifiers:

- `reports/hosted_api_checks.json`
- `reports/hosted_persistence_checks.json`
- `reports/hosted_browser_checks.json`
- `reports/hosted_interaction_checks.json`

The additional interaction checks exercised keyboard opening/navigation of the
mobile menu, modal focus entry/trapping/Escape/return, keyboard scrolling of the
mobile cost table, immediate hiding of stale amounts after a tariff edit,
missing-rate partial results, accessible invalid-rate errors, explicit zero
rates and absence of JavaScript page errors. This is a focused check, not a
comprehensive accessibility audit.

### What the persistence check proves

A fictional workspace and selection were saved on the public app. The same
source was redeployed to a new production Vercel deployment. With the original
verification session, the same workspace, customer, property and saved
selection were returned from Neon afterwards. Browser reload persistence was
also checked on desktop and mobile.

This proves persistence across the tested application redeployment, **not** a
forced Neon/database-provider restart, disaster recovery, cross-device login
or indefinite retention. Anonymous access depends on the browser cookie;
fictional workspaces expire after 30 days.

### Screenshot scope

Twelve views were captured on each device: start, dashboard, score dialog,
home inputs, improvements, selected results, costs/packages, explanation,
adviser homes, saved workspace, plan and evidence. The screenshot bundle is a
local release artifact, not a new public database or an upload of real home
data. No page-wide horizontal overflow was found at the tested sizes.

For the money example, DEMO-01 with loft insulation and heat pump uses the
**explicitly illustrative** 25p electricity / 7p gas preset. Annual variable
charges change from **£2,040 to £1,946: £94/year saved**. Electricity increases
by 2,312 kWh while gas falls by 9,600 kWh; the 7,288 kWh net reduction is not the
same percentage as the bill reduction. Heat pump alone produces **−£8/year**
at these illustrative tariffs, with no positive payback shown.

All values are model/scenario estimates, not measured household savings.

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

After public deployment, the focused 204-test backend suite, full 330-test
frontend suite and production frontend build were run again and passed against
the unchanged application source. An independent final scoped review of the
tracked publication boundary, hosted configuration, model hashes, metadata and
hosted receipts found no material blocker. It was not a penetration test or
an independent repeat of every live test.

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
test. The separate hosted connection, ingress and application-redeployment
checks above used Neon. Its default pooled connection rejected a startup
timeout option; the working configuration uses the unpooled SSL secret
override described in `docs/HOSTING.md`.

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

## Remaining limits

- No production capacity/SLA, sustained hosted load test, accessibility
  certification or real-participant usability study is claimed.
- No Neon-provider restart, backup restore or disaster-recovery test was run.
- No live Gemini/provider behaviour was tested on this public deployment;
  explanations deliberately use the local fallback.
- The property-value model remains synthetic, not market-calibrated or causal;
  user-entered homes abstain from value-premium predictions.
- The data-backed pilot covers England and Wales. Results are screening
  estimates, not EPC certificates, installer quotes, loan decisions or savings
  guarantees. Tariffs, cost ranges and assumptions must be reviewed.
- Free hosting has quotas, idle behaviour and eligibility rules; this is a
  personal demonstration, not guaranteed free production service.
