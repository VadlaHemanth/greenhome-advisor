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
4. Build with the command in `vercel.json`.
5. Confirm `/api/health`, `/api/readiness`, a fictional assessment, tariff
   comparison, workspace creation/save/reload, cross-workspace rejection and
   the deployed version.
6. Check storage after a restart. Do not call a successful page load proof of
   persistence or all application functionality.

Do not enter a payment method, upgrade a plan or enable paid usage simply to
make this demo deploy. Pause and reassess if quotas or build limits do not fit.
No secrets belong in `vercel.json`, frontend environment variables or Git.

## Official references checked 15 October 2026

- Vercel FastAPI: `https://vercel.com/docs/frameworks/backend/fastapi`
- Hobby eligibility: `https://vercel.com/docs/plans/hobby`
- Neon plans: `https://neon.com/docs/introduction/plans`

These describe supported configuration, not proof this particular deployment
has completed. Final verified URLs and limitations belong in the release
validation record.
