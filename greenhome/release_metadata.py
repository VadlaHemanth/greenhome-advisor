"""Small allowlisted public deployment identity, without environment dumps."""
import re
from collections.abc import Mapping


def release_metadata(env: Mapping[str, str]) -> dict:
    revision = env.get("VERCEL_GIT_COMMIT_SHA") or env.get("GREENHOME_REVISION")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        revision = None
    return {
        "name": "GreenHome Advisor",
        "version": "2026.10",
        "revision": revision,
        "environment": "hosted" if env.get("VERCEL") == "1" else "local",
    }
