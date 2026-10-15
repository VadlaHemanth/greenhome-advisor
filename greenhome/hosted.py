"""Explicit hosted configuration; never fall back to ephemeral saved state."""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit


def hosted_environment(env: dict[str, str]) -> dict[str, str]:
    """Return hosting defaults without exposing or logging credential values."""
    if env.get("VERCEL") != "1":
        return {}
    database = env.get("GREENHOME_WORKSPACE_DATABASE_URL") or env.get("DATABASE_URL", "")
    try:
        parsed = urlsplit(database)
        valid_database = parsed.scheme in ("postgres", "postgresql", "postgresql+psycopg") and bool(parsed.hostname) and bool(parsed.path.strip("/"))
    except ValueError:
        valid_database = False
    if not valid_database:
        raise RuntimeError("Hosted workspaces require persistent PostgreSQL storage; configure DATABASE_URL.")
    database = "postgresql+psycopg:" + database.split(":", 1)[1]
    domains = []
    for key in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "GREENHOME_CANONICAL_HOST"):
        value = env.get(key, "").strip().lower()
        if not value:
            continue
        if (len(value) > 253 or "." not in value
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value)
                or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in value.split("."))):
            raise RuntimeError("Configure a valid public hostname, without a scheme, path or wildcard.")
        if value not in domains:
            domains.append(value)
    if not domains:
        raise RuntimeError("Hosted runtime requires an explicit public hostname.")
    # This public portfolio deployment intentionally uses only local explanations.
    # Optional provider code remains available in the application for a separately
    # reviewed authenticated deployment, not as an unbounded public endpoint.
    return {
        "GREENHOME_PUBLIC_MODE": "true",
        "GREENHOME_LIVE_LLM": "false",
        "GREENHOME_LIVE_GEMINI": "false",
        "GREENHOME_WORKSPACE_DATABASE_URL": database,
        "GREENHOME_PROVIDER_BUDGET_DATABASE_URL": database,
        "GREENHOME_ALLOWED_HOSTS": ",".join(domains),
        "GREENHOME_ALLOWED_ORIGINS": ",".join("https://" + host for host in domains),
        "GREENHOME_CALC_WORKERS": "2",
        "GREENHOME_CALC_CAPACITY": "64",
        "GREENHOME_EXPLAIN_WORKERS": "1",
        "GREENHOME_EXPLAIN_CAPACITY": "16",
    }


def configure_hosted() -> None:
    os.environ.update(hosted_environment(dict(os.environ)))
