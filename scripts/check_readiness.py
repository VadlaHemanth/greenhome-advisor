"""Exit nonzero unless compiled assets and trusted local inference are ready."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from greenhome.readiness import Readiness

result = Readiness().check()
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["status"] == "ready" else 1)
