# Hosting GreenHome Advisor

This is a personal/non-commercial portfolio demonstration. Vercel Hobby and
Neon Free have quotas, eligibility rules and idle behaviour; neither implies
unlimited or guaranteed free production service.

## Verified deployment

- Public demo: `https://greenhome-advisor-xi.vercel.app`
- Application source revision: `754b5fbfe1ff6de346ed2523c07224c24872a36e`
- Platform observed on 15 October 2026: Vercel Hobby, FastAPI, Python 3.12,
  Node.js 22; Neon Free database in London. Neon Auth is not enabled.
- React is built with Vite and served by the FastAPI application. The app's
  saved fictional workspaces use Neon PostgreSQL, not the function filesystem.
- Public HTTPS checks, separate-workspace isolation, browser reload, and
  restoration of a previously saved plan after a production redeployment passed.
  See `docs/VALIDATION.md` and the safe receipts in `reports/hosted_*.json`.

No paid plan, card entry or upgrade was used for this release. This records the
configuration observed at deployment, not a permanent pricing or availability
guarantee. The public alias is accessible without Vercel login; individual
deployment/preview URLs may require Vercel authentication.

## Runtime

The root `app.py` exposes FastAPI. The build command builds the React/Vite
frontend; FastAPI mounts only `frontend/dist/assets` and serves its built index,
never the repository. URLs use client-side hash routes, so refresh stays on `/`.

Models are pre-trained and their hashes are checked against
`reports/training_metrics.json` before inference. No training occurs at request
time. The hosted entry requires `GREENHOME_WORKSPACE_DATABASE_URL` or
`DATABASE_URL` for persistent PostgreSQL. It
configures the existing SQLAlchemy workspace and provider-budget stores; there
is no `/tmp` or ephemeral SQLite fallback for saved records.

The hosted entry uses exact Vercel deployment/production hosts. An additional
custom host may be set as `GREENHOME_CANONICAL_HOST`, without scheme or path.
No wildcard origins are accepted. Public cookies remain Secure, HttpOnly and
SameSite=Strict. These flags and secure-origin/save/reload behaviour were checked
against the public alias; this does not constitute a penetration test.

The public portfolio deployment forces local explanations. It does not expose
provider credentials or offer an unbounded free-model gateway. Optional provider
integration remains in the source for separately reviewed deployments.

## Setup

1. Use an eligible free hosting account and free Postgres project.
2. Connect the free database only to the intended project. For this Neon
   configuration, set `GREENHOME_WORKSPACE_DATABASE_URL` as a secret to the
   **unpooled SSL connection string**, using `postgresql+psycopg` as the scheme.
   The hosted adapter assigns the same durable store to workspace and
   provider-budget storage.
3. Create/link the intended Vercel project and select the FastAPI framework.
4. Build with the command in `vercel.json`. The scientific Python dependencies
   need the platform's supported larger-bundle path; see the build check below.
5. Confirm `/api/health`, `/api/readiness`, a fictional assessment, tariff
   comparison, workspace creation/save/reload, cross-workspace rejection and
   the deployed version.
6. Save a fictional plan, redeploy, and check that the same workspace and
   selection are restored. Do not call a successful page load proof of
   persistence or all application functionality.

Do not enter a payment method, upgrade a plan or enable paid usage simply to
make this demo deploy. Pause and reassess if quotas or build limits do not fit.
No secrets belong in `vercel.json`, frontend environment variables or Git.

### Why the unpooled Neon connection is required here

The first cloud deployment built successfully but its API failed during
database connection. The automatically supplied pooled URL rejected the
adapter's startup option: `unsupported startup parameter in options:
statement_timeout`. The unpooled SSL URL worked with the existing adapter.
The fix is a server-side secret override; statement-timeout safeguards were
not removed. Do not expose the connection string in frontend variables or
command output.

An unpooled connection is not permission for unlimited database connections.
The existing SQLAlchemy connection pools, serverless scaling, and the
provider's connection/compute/storage limits still apply. A database-provider
restart, sustained cloud load test and production capacity certification have
not been performed.

### Repeat deployment

This project is deployed explicitly with the authenticated Vercel CLI.
Git integration is **not** connected, so a Git push alone does not update it.
Use a clean source archive (never upload the working directory's `work/`,
private state or environment files), build the frontend, and set
`GREENHOME_REVISION` to the exact full source commit for that deployment.
Keep database credentials in Vercel secrets. Recheck `/api/release` against the
intended commit after deployment.

The verified project uses `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` for its scientific
Python dependencies. The actual Hobby deployment with this setting succeeded;
no model artifact was replaced or removed. Capabilities can vary between
accounts or platform versions; do not upgrade to a paid plan if a future build
does not fit.

Cold starts, idle database wake-up, concurrency and free-tier limits can
affect availability and latency. The sample API timings are observations, not
latency guarantees. The public application forces local explanations and makes
no live provider call, avoiding an unbounded paid-model endpoint.

## Local platform-builder check

On 15 October 2026, the installed Vercel Python builder (`@vercel/python`
25.1.0, from Vercel CLI 64.2.0) built the public source at revision
`0bb881598506009722c38509886e0341191f5d3f` with Python 3.12. This was a local
builder invocation, not an authenticated deployment.

The default local builder path exceeded its 225 MiB packaging threshold after
dependency externalisation. The same source succeeded when the documented
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` capability was supplied to that local build.
The resulting function's measured files totalled 358,521,734 bytes
(approximately 342 MiB), with both original model hashes unchanged, the
required API modules present, and 23 frontend asset files included. No model
or feature was removed to obtain this result.

Current Vercel documentation describes a 500 MB standard Python limit and
Large Functions up to 5 GB on eligible Fluid-compute projects. The installed
builder's default local mode and the actual project capability are not
interchangeable. The later real Hobby deployment succeeded; the local flag alone
did not establish this. Do not upgrade to a paid plan. If supported, configure
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` as a non-secret project build setting.

The local output routed requests to a `python3.12` FastAPI function and retained
the built frontend within it. The check used syntactically valid placeholder
database settings only; it did not connect to a cloud database or establish
hosted persistence. A separate isolated local PostgreSQL restart test is
recorded in `docs/VALIDATION.md`.

## Official references checked 15 October 2026

- Vercel FastAPI: `https://vercel.com/docs/frameworks/backend/fastapi`
- Hobby eligibility: `https://vercel.com/docs/plans/hobby`
- Neon plans: `https://neon.com/docs/introduction/plans`
- Vercel function limits and larger bundles:
  `https://vercel.com/docs/functions/limitations`

These describe platform configuration. Evidence for this particular deployment
is recorded separately in `docs/VALIDATION.md`; local build evidence retains its
original, narrower scope.
