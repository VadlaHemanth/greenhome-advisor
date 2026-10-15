"""Deployment readiness checks with no provider calls or credential inspection."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
MODEL_FILES = ("models/energy_benchmark.joblib", "models/synthetic_value.joblib")


def _warm_models() -> bool:
    from greenhome.engine import demo_homes
    from greenhome.ml import predict_energy_benchmark, predict_value_impact
    home = demo_homes()[0]
    energy = predict_energy_benchmark(home)
    value = predict_value_impact(home, ["loft_insulation"])
    return bool(
        energy
        and energy.get("status") == "observed_benchmark"
        and value.get("status") == "synthetic_illustration"
    )


class Readiness:
    def __init__(self, root: Path = ROOT, warm=_warm_models, ttl: float = 10):
        self.root = Path(root)
        self.warm = warm
        self.ttl = ttl
        self.lock = threading.Lock()
        self.cached = None
        self.expires = 0.0

    def check(self) -> dict:
        with self.lock:
            if self.cached is not None and time.monotonic() < self.expires:
                return deepcopy(self.cached)
            checks = {"frontend": False, "model_integrity": False, "local_inference": False}
            try:
                built = self.root / "frontend" / "dist"
                index = built / "index.html"
                if index.is_file():
                    html = index.read_text()
                    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
                    checks["frontend"] = bool(assets) and all(
                        (built / path.lstrip("/")).resolve().is_relative_to(built.resolve())
                        and (built / path.lstrip("/")).is_file()
                        for path in assets
                    )
                manifest = json.loads((self.root / "reports/training_metrics.json").read_text())
                checks["model_integrity"] = all(
                    (self.root / name).is_file()
                    and hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                    == manifest["artifacts"][name]["sha256"]
                    for name in MODEL_FILES
                )
                # Only load artifacts after their recorded hashes match.
                if checks["model_integrity"]:
                    checks["local_inference"] = self.warm() is True
            except Exception:
                # Public readiness must not expose file paths or exception text.
                pass
            ready = all(checks.values())
            self.cached = {
                "status": "ready" if ready else "not_ready",
                "checks": checks,
                "live_provider_tested": False,
                "note": "Local deployment checks only; not a claim of model accuracy or live Gemini availability.",
            }
            self.expires = time.monotonic() + self.ttl
            return deepcopy(self.cached)
