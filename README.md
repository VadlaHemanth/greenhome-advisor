# GreenHome Advisor

An England and Wales home-improvement screening demo. Python owns the
calculations; React shows the assumptions and comparisons. Currency is GBP.

## Try the hosted demo

**[Open GreenHome Advisor](https://greenhome-advisor-xi.vercel.app)**

Choose **Explore an example home** to start without an account. Add improvements,
then open **Costs & packages** and enter your own tariffs or explicitly choose
the illustrative preset. Saved workspace is optional and accepts fictional
household data only. No shared username or password is required.

The public demo uses local explanations, not paid/live AI calls.
See `docs/VALIDATION.md` for the tested source revision and release checks.

## Run locally

Requires Python 3.12 and a supported Node.js runtime.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
```

Choose an unused port. Example:

```bash
export GREENHOME_ALLOWED_ORIGINS=http://127.0.0.1:8016,http://localhost:8016
export GREENHOME_ALLOWED_HOSTS=localhost,127.0.0.1
export GREENHOME_LIVE_LLM=false
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8016
```

Open `http://127.0.0.1:8016`. No provider key is required. Optional private
configuration belongs in an ignored `.env`; use `.env.example` as a template.
Do not expose the local-mode server through a public tunnel.

## Verify

```bash
.venv/bin/python -m pytest tests/test_money.py tests/test_money_api.py tests/test_hosted.py -q
.venv/bin/python -m pytest -m "not training_data and not historical_artifacts" -q
npm test --prefix frontend -- --maxWorkers=1
npm run build --prefix frontend
```

Tests marked `training_data` validate the raw/prepared datasets and full
prediction replay. Obtain the public data using the preparation instructions
in `docs/DATA_AND_MODELS.md`, then run `.venv/bin/python -m pytest -q` to include
them. Tests marked `historical_artifacts` additionally audit the original frozen
experiment archive, including exact historical log hashes; that local archive
is deliberately not republished. Neither group is silently skipped or reported
as passing in a clean checkout. The ordinary test run includes current
workspace/API isolation tests and uses the included trained artifacts and frozen
prediction reports; no confidential data is needed.

## Hosted configuration

See `docs/HOSTING.md`. Hosting requires persistent Postgres for saved
fictional workspaces; an ephemeral filesystem is not a substitute.
The public entry defaults to local explanations and does not need live AI
credentials. Free plans have eligibility rules and usage limits.
Deployment is currently explicit through the Vercel CLI; pushing to GitHub
does **not** automatically deploy this project.

## Data and models

The repository includes permitted trained model artifacts. Dataset sources,
preparation commands, licence notes and model limitations are in
`docs/DATA_AND_MODELS.md`; money assumptions are in `docs/MONEY.md`.
Do not use this demo as an EPC certificate, installer quote, valuation,
loan decision or savings guarantee.

MIT licence, Team 225.
