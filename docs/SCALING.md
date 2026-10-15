# Scaling the application without rewriting its calculations

This is a bounded service designed for replication, not unlimited capacity.
Capacity is measured for a workload, machine, database and provider allowance.

## Current design

- React uses same-origin JSON endpoints; no provider key or calculation logic
  ships to the browser.
- Pure score/package/ranking functions carry no customer session between calls.
- Each API process has a bounded calculation pool and a separate bounded
  explanation pool. Slow providers cannot fill the score pool. Timed-out or
  cancelled requests do not free work that is still actually running.
- Each worker verifies and warms model artifacts before accepting traffic.
- `WEB_CONCURRENCY` selects server processes. CPU pool sizes and finite queue
  bounds are explicit environment settings, not unbounded background jobs.
- Workspace identity is a private cookie; records live in the configured
  database, not a worker. A request can reach another worker and still read the
  same workspace. Optimistic versions prevent silently overwriting another save.
- SQLite is the local demonstration storage. `GREENHOME_WORKSPACE_DATABASE_URL`
  accepts `postgresql+psycopg://...` for shared multi-host storage. Provision and
  load-test the actual PostgreSQL service before claiming a fleet capacity.
- The default provider-attempt ledger is single-host SQLite. For multi-host
  deployments, set `GREENHOME_PROVIDER_BUDGET_DATABASE_URL` to PostgreSQL and
  run `scripts/init_shared_budget.py` first. Its atomic admission uses the
  database's UTC date; unavailable/exhausted accounting blocks provider calls.
  Set the same configured allowance on every replica.
- Both PostgreSQL adapters require the `psycopg` driver. It is not installed or
  a running PostgreSQL service validated merely by installing SQLAlchemy.
  Install `requirements-postgres.txt` for that deployment. The optional
  `Dockerfile` builds the frontend and packages the API/model artifacts without
  `.env`, state or source datasets. It is a template until built and tested on
  a Docker host; this environment has no Docker daemon.

## Deliberate resource limits

Request sizes, catalogue size, workspace/event counts, queues, timeouts and daily
AI attempts are bounded. Do not remove them to make an “unlimited” claim.
Increase an operational limit only alongside measured resource capacity and
corresponding tests. Quotas can be conservative for a hackathon demonstration.

Per-process IP request windows are a local abuse guard, not distributed per-user
billing. Uvicorn ignores arbitrary forwarding headers. A configured authenticated
loopback gateway is explicitly recognized via its server-only token; this does
not grant customer roles. In a multi-host rollout, the ingress must enforce
fleet-wide rate limits and reliably establish client identity. The current shared
ngrok login remains a demonstration access boundary.

## Test command

```bash
.venv/bin/python scripts/load_test.py --users 100 --rounds 5 --workers 2
```

This command starts **local isolated staging** on an unused loopback port. It
overrides provider keys/live flags to empty/false, uses a temporary workspace
database, and closes only its own server. Clients have distinct actual loopback
source addresses; no forwarding-header spoofing or disabled rate limiter is used.
They create private workspaces and run scoring, comparison, decision checking,
ranking and local explanations with real trained model inference, then reread
and delete their own data. The report records errors and overload responses.

A burst test is not a sustained SLA, physical-user study or proof about every
host. Real Gemini throughput requires a separate live provider quota/cost plan.
The PostgreSQL admission transaction is unit/concurrency-tested through SQLite
with the corresponding SQL dialect; this does not establish PostgreSQL runtime
integration. Keep that distinction until real PostgreSQL integration tests run.

## Before scaling further

1. Pin a release and run the same test with the chosen CPU/RAM and real database.
2. Exercise a sustained realistic workload and larger overload; report latency,
   throughput and intended 429/503 separately from unexpected failures.
3. Test two replicas, shutdown/restart, database outage and restore, queue
   pressure, provider quota and timeout, ownership isolation and version conflicts.
4. Monitor redacted operational metrics and costs, with an accountable alert
   recipient and a tested rollback. Never log raw homes, questions or secrets.
5. Real multi-user adviser/customer sharing requires managed identities and
   backend roles. Two views of one private fictional workspace do not provide it.
