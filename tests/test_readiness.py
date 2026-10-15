import hashlib
import json
from pathlib import Path

from greenhome.readiness import MODEL_FILES, Readiness


def files(root: Path):
    built = root / "frontend/dist/assets"
    built.mkdir(parents=True)
    (built / "app.js").write_text("/* synthetic fixture */")
    (root / "frontend/dist/index.html").write_text('<script src="/assets/app.js"></script>')
    (root / "models").mkdir()
    manifest = {"artifacts": {}}
    for name in MODEL_FILES:
        p = root / name
        p.write_bytes(b"synthetic fixture, never deserialize")
        manifest["artifacts"][name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    (root / "reports").mkdir()
    (root / "reports/training_metrics.json").write_text(json.dumps(manifest))


def test_ready_and_cached_result_not_mutable(tmp_path):
    files(tmp_path)
    calls = []
    def warm():
        calls.append(True)
        return True
    checker = Readiness(tmp_path, warm=warm)
    result = checker.check()
    assert result["status"] == "ready"
    result["checks"]["frontend"] = False
    assert checker.check()["checks"]["frontend"] is True
    assert len(calls) == 1


def test_integrity_failure_never_loads_model(tmp_path):
    files(tmp_path)
    (tmp_path / MODEL_FILES[0]).write_bytes(b"modified")
    def warm():
        raise AssertionError("Must not load corrupted artifact")
    result = Readiness(tmp_path, warm=warm).check()
    assert result["status"] == "not_ready"
    assert result["checks"]["model_integrity"] is False


def test_missing_build_asset_and_failed_inference(tmp_path):
    files(tmp_path)
    (tmp_path / "frontend/dist/assets/app.js").unlink()
    result = Readiness(tmp_path, warm=lambda: False).check()
    assert result["checks"] == {"frontend": False, "model_integrity": True, "local_inference": False}


def test_corrupt_manifest_has_no_private_error(tmp_path):
    files(tmp_path)
    (tmp_path / "reports/training_metrics.json").write_text("PRIVATE_SECRET invalid json")
    result = Readiness(tmp_path, warm=lambda: True).check()
    assert result["status"] == "not_ready"
    assert "PRIVATE_SECRET" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)
