"""Keep offline tests independent of the operator's real deployment and secrets."""
import os

import pytest

# These process-only defaults precede imports of api.py, whose default app loads
# .env without override. They do not modify the running service or the .env file.
TEST_ENV = {
    "GREENHOME_LLM_PROVIDER": "gemini",
    "XKIRO_API_KEY": "",
    "GEMINI_API_KEY": "",
    "GEMINI_KEY": "",
    "GEMINI_MODEL": "offline-test",
    "GREENHOME_PUBLIC_MODE": "false",
    "GREENHOME_LIVE_GEMINI": "false",
    "GREENHOME_WARM_MODELS": "false",
    "GREENHOME_GATEWAY_TOKEN": "",
    "GREENHOME_ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
    "GREENHOME_ALLOWED_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
}
os.environ.update(TEST_ENV)


@pytest.fixture(autouse=True)
def isolated_operator_settings(monkeypatch, tmp_path):
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GREENHOME_PROVIDER_BUDGET_PATH", str(tmp_path / "provider-state/budget.sqlite3"))
    monkeypatch.setenv("GREENHOME_GEMINI_DAILY_REQUEST_LIMIT", "100")
    monkeypatch.delenv("GREENHOME_LIVE_LLM", raising=False)
    monkeypatch.setenv("GREENHOME_WORKSPACE_DATABASE_URL", f"sqlite:///{tmp_path}/workspace/state.sqlite3")
