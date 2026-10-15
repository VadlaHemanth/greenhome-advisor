"""Explicit operator schema provisioning for the optional shared PostgreSQL cap."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from greenhome.shared_budget import database, metadata

load_dotenv(ROOT/".env", override=False)
url = os.environ.get("GREENHOME_PROVIDER_BUDGET_DATABASE_URL", "").strip()
if not url:
    raise SystemExit("Configure a shared PostgreSQL provider budget URL first.")
try:
    metadata.create_all(database(url))
except Exception:
    raise SystemExit("Shared budget schema provisioning failed; configuration was not printed.") from None
print("Shared provider-budget schema is ready. This did not contact Gemini.")
