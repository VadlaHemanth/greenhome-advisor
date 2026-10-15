"""Local artifact and secret preflight; does not publish or claim deployment."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    failures = []
    for rel in ["frontend/dist/index.html", "models/energy_benchmark.joblib",
                "models/synthetic_value.joblib", "reports/training_metrics.json",
                "deliverables/M1.pdf", "LICENSE", "ai_chat.md"]:
        if not (ROOT / rel).is_file():
            failures.append(f"Missing {rel}")
    if (ROOT / "reports/training_metrics.json").exists():
        metrics = json.loads((ROOT / "reports/training_metrics.json").read_text())
        for rel, record in metrics["artifacts"].items():
            p = ROOT / rel
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != record["sha256"]:
                failures.append(f"Model/prediction hash mismatch: {rel}")
    if subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        failures.append(".env must not be tracked")
    # Never print a secret value, even if a match is found.
    from dotenv import dotenv_values
    settings = dotenv_values(ROOT / ".env", interpolate=False)
    secrets = [str(settings[k]).encode() for k in ("GEMINI_API_KEY", "GEMINI_KEY", "XKIRO_API_KEY", "GREENHOME_GATEWAY_TOKEN", "GREENHOME_DEMO_PASSWORD")
               if settings.get(k) and len(str(settings[k])) > 8]
    candidates = list((ROOT / "frontend" / "dist").rglob("*")) if (ROOT / "frontend" / "dist").is_dir() else []
    for path in candidates:
        if path.is_file() and any(secret in path.read_bytes() for secret in secrets):
            failures.append(f"Secret content found in built asset {path.relative_to(ROOT)}")
    for problem in failures:
        print("BLOCKER:", problem)
    print("Artifact/secret preflight:", "PASS" if not failures else "FAIL")
    print("This is not proof of public deployment, real-world model accuracy or remote submission.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
