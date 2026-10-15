"""Independent raw contract oracles. Never regenerate labels from the candidate."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ownership_evaluation", ROOT / "scripts/evaluate_ownership.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


@pytest.fixture(autouse=True)
def isolated_operator_settings():
    """Override broad conftest fixture: evaluator supplies its own offline sandbox."""
    yield


def test_ids_assigned_before_properties_and_three_disjoint_splits():
    data = evaluation.generate_cases()
    assert len(data["assignments_before_expansion"]) == 15
    assert all(set(row) == {"customer_id", "split"} for row in data["assignments_before_expansion"])
    ids = {}
    for split, count, properties in (("train", 9, 21), ("validation", 3, 7), ("test", 3, 7)):
        cases = [c for c in data["cases"] if c["split"] == split]
        assert len(cases) == count
        assert sum(c["property_count"] for c in cases) == properties
        assert set(c["property_count"] for c in cases) == {1, 2, 4}
        ids[split] = {c["customer_id"] for c in cases}
        for case in cases:
            assert all(p["logical_property_id"].startswith(case["customer_id"] + "-P")
                       for p in case["properties"])
    assert not ids["train"] & ids["validation"]
    assert not ids["train"] & ids["test"]
    assert not ids["validation"] & ids["test"]


def case_four():
    return next(c for c in evaluation.generate_cases()["cases"]
                if c["split"] == "test" and c["property_count"] == 4)


def truth(case, phase):
    return deepcopy(next(s["expected"] for s in case["steps"] if s.get("phase") == phase))


def test_literal_reference_distinguishes_customer_and_property_preferences():
    case = case_four()
    local = truth(case, "local_exclusion")
    assert local["properties"][0]["home"]["excluded_retrofits"] == ["solar_pv"]
    assert local["properties"][1]["home"]["excluded_retrofits"] == []
    shared = truth(case, "customer_exclusion")
    assert shared["properties"][0]["home"]["excluded_retrofits"] == ["smart_controls", "solar_pv"]
    assert shared["properties"][1]["home"]["excluded_retrofits"] == ["smart_controls"]
    assert shared["properties"][1]["preferences"]["deferred_retrofits"] == []
    assert shared["portfolio_budget_gbp"] is None


def test_literal_planning_accounting_and_non_target_completion_invariance():
    case = case_four()
    before = truth(case, "shared_cap")
    after = truth(case, "after_recording_backdated_event")
    assert before["budget_summary"] == {
        "planned_upper_gbp": 1600, "completed_reserved_gbp": 0,
        "total_reserved_gbp": 1600, "remaining_gbp": 350.0, "status": "within_budget",
    }
    assert after["budget_summary"] == {
        "planned_upper_gbp": 0, "completed_reserved_gbp": 1600,
        "total_reserved_gbp": 1600, "remaining_gbp": 350.0, "status": "within_budget",
    }
    assert before["properties"][1:] == after["properties"][1:]
    p = after["properties"][0]
    assert p["home"]["insulation"] == "good"
    assert p["home"]["gas_kwh"] is None and p["home"]["electricity_kwh"] is None
    assert p["baseline_status"] == "needs_update"
    assert p["selected_retrofits"] == []
    assert p["events"][0]["planning_cost_upper_gbp"] == 1600


def test_recording_time_not_past_occurrence_controls_reference_availability():
    case = case_four()
    prior = truth(case, "before_recording_backdated_event")["properties"][0]
    later = truth(case, "after_recording_backdated_event")["properties"][0]
    assert prior["events"] == []
    assert prior["home"]["insulation"] == "poor"
    assert prior["home"]["gas_kwh"] > 0
    assert later["events"][0]["completed_on"] == "2026-10-09"
    assert later["events"][0]["created_at"].startswith("2026-10-10T")
    assert later["home"]["gas_kwh"] is None


def test_owner_blind_control_actually_applies_completion_to_wrong_property():
    case = case_four()
    step = next(s for s in case["steps"] if s.get("phase") == "after_recording_backdated_event")
    blind = evaluation.reference_prefix(case, step["at"], owner_blind=True)["properties"]
    scoped = step["expected"]["properties"]
    assert blind[1]["home"]["insulation"] == "good"
    assert blind[1]["home"]["gas_kwh"] is None
    assert scoped[1]["home"]["insulation"] == "poor"
    assert scoped[1]["home"]["gas_kwh"] > 0
    assert blind[1]["home"]["property_id"] == scoped[1]["home"]["property_id"]


def test_raw_semantic_oracle_rejects_constant_abstention_and_wrong_property():
    expected = truth(case_four(), "initial")["properties"][1]
    output = {"selected": [], "feasible": [], "status": "insufficient_evidence",
              "improvement_percent": None, "electricity_saving_kwh": None, "gas_saving_kwh": None}
    criteria = evaluation.semantic_criteria(expected["home"], output, expected)
    assert criteria["exact_property_facts"]
    assert not criteria["baseline_availability"]
    assert not criteria["all_semantics"]
    wrong = {**expected["home"], "gas_kwh": 0}
    assert not evaluation.semantic_criteria(wrong, output, expected)["exact_property_facts"]


@pytest.mark.historical_artifacts
def test_hash_freeze_has_not_changed():
    data, manifest = evaluation.load_frozen()
    assert evaluation.sha(data) == manifest["reference_sha256"]
    assert manifest["candidate_executed_before_freeze"] is False
    assert evaluation.hashes(evaluation.PROTECTED) == manifest["protected_files_sha256"]
    assert data["protocol"]["train_use"].startswith("design-only")


def test_guard_blocks_socket_and_model_loading(tmp_path):
    with evaluation.offline_guard(tmp_path / "never-created.sqlite3") as counters:
        with pytest.raises(AssertionError, match="external"):
            socket.create_connection(("127.0.0.1", 9))
        import joblib
        with pytest.raises(AssertionError, match="Fitted"):
            joblib.load("not-opened.joblib")
        assert counters["network_attempts"] == 1
        assert counters["model_load_attempts"] == 1
    assert not (tmp_path / "never-created.sqlite3").exists()


@pytest.fixture(scope="module")
def http_report():
    data, manifest = evaluation.load_frozen()
    return evaluation.evaluate(data, manifest)


@pytest.mark.historical_artifacts
def test_real_http_ownership_contract(http_report):
    assert http_report["status"] == "passed", {
        "cases": http_report["case_results"],
        "failures": [c for c in http_report["checks"] if not c["passed"]][:20],
        "failed_report_gates": http_report["failed_report_gates"],
        "changed_sources_during_run": http_report["changed_sources_during_run"],
    }


@pytest.mark.historical_artifacts
def test_actual_replay_counts_and_train_is_not_claimed_as_executed(http_report):
    assert http_report["fit_performed"] is False
    assert http_report["train_results"] is None
    assert http_report["counts"]["train"]["executed_customers"] == 0
    for split in ("validation", "test"):
        assert http_report["counts"][split]["executed_customers"] == 3
        assert http_report["counts"][split]["actual_property_queries"] == 63
        assert http_report["counts"][split]["actual_completion_events"] == 3
        assert http_report["counts"][split]["actual_customer_records_created"] == 24
        assert http_report["counts"][split]["actual_property_records_created"] == 28
        assert http_report["counts"][split]["actual_workspaces_created"] == 6
    assert len(http_report["queries"]) == 126
    assert all(row["queries"] == row["properties"] * 9 for row in http_report["case_results"])
    assert sum(r["http_requests"] for r in http_report["case_results"]) == len(http_report["requests"])
    assert http_report["raw_reference_unchanged"]


@pytest.mark.historical_artifacts
def test_real_single_property_control_ties_and_multi_property_control_fails(http_report):
    one = http_report["by_cardinality"]["1"]
    assert one["paired_all_semantics"] == {"both_satisfied": 18}
    for n in ("2", "4"):
        paired = http_report["by_cardinality"][n]["paired_all_semantics"]
        assert paired.get("scoped_only", 0) > 0
        assert paired.get("owner_blind_only", 0) == 0
        assert paired.get("neither", 0) == 0
    for q in http_report["queries"]:
        assert q["arms"]["scoped_memory"]["output"] == q["arms"]["explicit_current_facts"]["output"]


@pytest.mark.historical_artifacts
def test_real_prior_http_snapshots_are_not_retroactively_completed(http_report):
    for phase, completed, insulation in (
        ("before_recording_backdated_event", 0, "poor"),
        ("after_recording_backdated_event", 1, "good"),
    ):
        rows = [q for q in http_report["queries"]
                if q["phase"] == phase and q["logical_property_id"].endswith("-P01")]
        assert len(rows) == 6
        assert all(q["available_completion_events"] == completed for q in rows), [
            (q["customer_id"], q["phase"], q["available_completion_events"]) for q in rows
        ]
        assert all(q["arms"]["scoped_memory"]["input"]["insulation"] == insulation for q in rows)


@pytest.mark.historical_artifacts
def test_runtime_guards_and_sources_unchanged(http_report):
    assert http_report["offline_guards"]["network_attempts"] == 0
    assert http_report["offline_guards"]["provider_attempts"] == 0
    assert http_report["offline_guards"]["model_load_attempts"] == 0
    assert http_report["source_stable"], http_report["changed_sources_during_run"]
    assert http_report["protected_evidence_unchanged"]


@pytest.mark.historical_artifacts
def test_raw_http_history_and_identity_evidence_is_recorded(http_report):
    for q in http_report["queries"]:
        assert len(q["actual_property_state"]["events"]) == q["available_completion_events"]
        for event in q["actual_property_state"]["events"]:
            assert event["created_at"] < q["query_at"]
            assert event["completed_on"] == "2026-10-09"
            assert event["planning_cost_upper_gbp"] == 1600
    for row in http_report["case_results"]:
        mapping = row["identity_map"]
        assert len(mapping["properties"]) == row["properties"]
        assert mapping["logical_customer_id"] == row["customer_id"]
        assert len({p["resource_id"] for p in mapping["properties"]}) == row["properties"]
