# Hosting GreenHome Advisor

This is a personal/non-commercial portfolio demonstration. Vercel Hobby and
Neon Free have quotas, eligibility rules and idle behaviour; neither implies
unlimited or guaranteed free production service.

## Runtime

The root `app.py` exposes FastAPI. The build command builds the React/Vite
frontend; FastAPI mounts only `frontend/dist/assets` and serves its built index,
never the repository. URLs use client-side hash routes, so refresh stays on `/`.

Models are pre-trained and their hashes are checked against
`reports/training_metrics.json` before inference. No training occurs at request
time. The hosted entry requires `DATABASE_URL` for persistent PostgreSQL. It
configures the existing SQLAlchemy workspace and provider-budget stores; there
is no `/tmp` or ephemeral SQLite fallback for saved records.

The hosted entry uses exact Vercel deployment/production hosts. An additional
custom host may be set as `GREENHOME_CANONICAL_HOST`, without scheme or path.
No wildcard origins are accepted. Public cookies remain Secure, HttpOnly and
SameSite=Strict. Hosting still needs actual secure-origin and save/reload tests.

The public portfolio deployment forces local explanations. It does not expose
provider credentials or offer an unbounded free-model gateway. Optional provider
integration remains in the source for separately reviewed deployments.

## Setup

1. Use an eligible free hosting account and free Postgres project.
2. Set `DATABASE_URL` as a secret environment variable on the hosting service.
3. Import this repository and select the FastAPI framework.
4. Build with the command in `vercel.json`. The scientific Python dependencies
   need the platform's supported larger-bundle path; see the build check below.
5. Confirm `/api/health`, `/api/readiness`, a fictional assessment, tariff
   comparison, workspace creation/save/reload, cross-workspace rejection and
   the deployed version.
6. Check storage after a restart. Do not call a successful page load proof of
   persistence or all application functionality.

Do not enter a payment method, upgrade a plan or enable paid usage simply to
make this demo deploy. Pause and reassess if quotas or build limits do not fit.
No secrets belong in `vercel.json`, frontend environment variables or Git.

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
interchangeable. Check the real Hobby project's eligibility and deployment
result. Do not upgrade to a paid plan or claim the local flag establishes
free hosted availability. If needed and supported, configure
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

These describe supported configuration, not proof this particular deployment
has completed. Final verified URLs and limitations belong in the release
validation record.
