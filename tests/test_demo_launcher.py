"""Exercise the local launcher's environment without starting a server."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("port", [None, "8001"])
def test_local_demo_overrides_old_public_settings_for_its_actual_port(tmp_path, port):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run_demo.sh").write_bytes((ROOT / "scripts/run_demo.sh").read_bytes())
    (scripts / "run_local.sh").write_text(
        '#!/usr/bin/env bash\nexec "$TEST_PYTHON" -c '
        '\'import os,json; print(json.dumps({k:os.environ.get(k) for k in '
        '["GREENHOME_PUBLIC_MODE","GREENHOME_GATEWAY_TOKEN",'
        '"GREENHOME_ALLOWED_HOSTS","GREENHOME_ALLOWED_ORIGINS"]}))\'\n'
    )
    environment = {
        **os.environ,
        "TEST_PYTHON": sys.executable,
        "GREENHOME_PUBLIC_MODE": "true",
        "GREENHOME_GATEWAY_TOKEN": "synthetic-gateway-value",
        "GREENHOME_ALLOWED_HOSTS": "old-public.example",
        "GREENHOME_ALLOWED_ORIGINS": "https://old-public.example",
    }
    environment.pop("PORT", None)
    if port is not None:
        environment["PORT"] = port
    result = subprocess.run(
        ["bash", str(scripts / "run_demo.sh")], cwd=tmp_path, env=environment,
        check=True, capture_output=True, text=True, timeout=10,
    )
    settings = json.loads(result.stdout)
    expected_port = port or "8000"
    assert settings == {
        "GREENHOME_PUBLIC_MODE": "false",
        "GREENHOME_GATEWAY_TOKEN": "",
        "GREENHOME_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "GREENHOME_ALLOWED_ORIGINS": (
            f"http://localhost:{expected_port},http://127.0.0.1:{expected_port}"
        ),
    }
