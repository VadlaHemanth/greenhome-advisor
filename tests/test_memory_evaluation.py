"""Offline checks of the chronological experiment, not participant evidence."""
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from scripts import evaluate_memory as memory


@pytest.fixture(scope="module")
def measured():
    # No report write: the CLI owns the one user-facing JSON.
    return memory.run_experiment()


def test_frozen_customer_disjoint_episode_design():
    episodes = memory.frozen_episodes()
    memory.validate_plan(episodes)
    assert memory.digest(episodes) == memory.PLAN_SHA256
    assert len(episodes) == 8
    assert len({e["customer_id"] for e in episodes}) == 8
    assert sum(len([s for s in e["steps"] if s["kind"] == "query"]) for e in episodes) == 64
    assert {e["split"] for e in episodes} == {"dev", "test"}
    assert len({e["property_group_id"] for e in episodes}) == 8
    # The app's four immutable aliases recur: never call these global IDs.
    assert len({e["home"]["property_id"] for e in episodes}) == 4


def test_customer_overlap_rejected():
    episodes = memory.frozen_episodes()
    episodes[4]["customer_id"] = episodes[0]["customer_id"]
    with pytest.raises(ValueError, match="customer_id"):
        memory.validate_plan(episodes)


def test_backdated_completion_not_visible_before_recording():
    episode = memory.frozen_episodes()[0]
    complete = next(s for s in episode["steps"] if s["kind"] == "complete")
    before = memory.prefix_truth(episode, complete["at"])
    after = memory.prefix_truth(episode, complete["at"] + 1)
    assert complete["completed_on"] == "2026-10-09"
    assert before["events"] == [] and before["home"]["insulation"] == "poor"
    assert after["home"]["insulation"] == "good"
    assert after["home"]["electricity_kwh"] is None
    assert after["home"]["gas_kwh"] is None
    assert after["events"][0]["created_at"] == memory.iso(complete["at"])


def test_foreign_episode_events_cannot_change_a_prefix():
    first, second = memory.frozen_episodes()[:2]
    stamp = first["steps"][-1]["at"]
    original = memory.prefix_truth(first, stamp)
    second["steps"][2]["kind"] = "complete"
    second["steps"][2].update(retrofit_id="heat_pump", completed_on="2026-10-09")
    assert memory.prefix_truth(first, stamp) == original


def test_future_and_unconfirmed_attempts_have_no_reference_effect():
    episode = memory.frozen_episodes()[0]
    for kind in ("future_attempt", "unconfirmed_restore"):
        step = next(s for s in episode["steps"] if s["kind"] == kind)
        assert memory.prefix_truth(episode, step["at"]) == memory.prefix_truth(episode, step["at"] + 1)


def test_original_frozen_protocol_bytes_unchanged():
    record = memory.protocol_record()
    assert record["original_frozen_protocol_unchanged"]
    assert record["legacy_reference_full_file_hash_matches"]
    assert record["memory_protocol_path"] == "docs/MEMORY_EVALUATION.md"


def test_network_guard_denies_connections_without_contact(tmp_path):
    with memory.offline_runtime(tmp_path / "state" / "memory.sqlite3") as counters:
        with pytest.raises(RuntimeError, match="forbidden"):
            socket.create_connection(("example.invalid", 443))
        assert counters["network_attempts"] == 1


def test_local_cookie_is_httponly_and_path_scoped(tmp_path):
    from fastapi.testclient import TestClient
    with memory.offline_runtime(tmp_path / "state" / "memory.sqlite3", public=False) as counters:
        app, store = memory.build_app([memory.START], counters)
        try:
            with TestClient(app, base_url="http://testserver") as client:
                response = client.post(memory.BASE, json={"consent": True})
                assert response.status_code == 200
                header = response.headers["set-cookie"]
                assert "HttpOnly" in header and "SameSite=strict" in header
                assert "Path=/api/workspace" in header and "Domain=" not in header
                assert "Secure" not in header
                assert client.get("/_memory_cookie_probe").json() == {"workspace_cookie_present": False}
                assert client.get(memory.BASE).status_code == 200
        finally:
            store.close()


def test_actual_experiment_completes_without_network_or_model_inference(measured):
    assert measured["status"] == "completed", measured.get("failed_checks") or measured.get("exceptions")
    assert measured["counts"]["executed_episodes"] == 8
    assert measured["counts"]["executed_queries"] == 64
    assert measured["counts"]["controller_outputs"] == 192
    assert measured["counts"]["database_rows_before_cleanup"] == {"workspaces": 2, "customers": 8}
    assert measured["runtime_guards"]["network_attempts"] == 0
    assert measured["runtime_guards"]["persistence_ranker_calls"] == 0
    assert measured["runtime_guards"]["ml_stub_calls"] > 0


def test_observed_pair_counts_and_non_placebo_controls(measured):
    stats = measured["metrics"]["by_split"]["all"]
    with_mem, without = stats["with_memory"], stats["without_memory"]
    for metric, n in (("deferred", 48), ("budget", 40), ("completed", 24), ("fuel_abstention", 16)):
        assert with_mem[metric]["eligible_queries"] == n
        assert with_mem[metric]["violations"] == 0
        assert without[metric]["violations"] > 0
    assert stats["reentered_current_facts"] == with_mem
    controls = measured["operational_check_summary"]
    assert controls["negative_control_no_memory_advantage"] == {"n": 16, "passed": 16}
    assert controls["current_facts_control_same_output"] == {"n": 64, "passed": 64}
    assert controls["metadata_only_does_not_change_plan"] == {"n": 8, "passed": 8}


def test_actual_cross_private_client_reads_and_mutations_denied(measured):
    attacks = [op for op in measured["operations"] if op["action"] in (
        "foreign_customer_read", "foreign_customer_update", "foreign_customer_completion")]
    assert len(attacks) == 24
    assert all(op["actual_status"] == 404 for op in attacks)
    assert measured["operational_check_summary"]["foreign_attempts_leave_both_workspaces_unchanged"] == {"n": 8, "passed": 8}
    assert measured["operational_check_summary"]["independent_store_restores_committed_state"] == {"n": 8, "passed": 8}
    assert measured["operational_check_summary"]["public_cookie_attributes"] == {"n": 2, "passed": 2}
    assert measured["operational_check_summary"]["only_token_hashes_persisted"] == {"n": 1, "passed": 1}


def test_actual_future_and_unconfirmed_writes_rejected_with_no_leakage(measured):
    denied = [op for op in measured["operations"] if op["action"] in ("future_attempt", "unconfirmed_restore")]
    assert len(denied) == 16 and all(op["actual_status"] == 422 for op in denied)
    assert measured["operational_check_summary"]["rejected_operation_has_no_state_effect"] == {"n": 16, "passed": 16}
    assert measured["operational_check_summary"]["exact_recorded_event_prefix"] == {"n": 64, "passed": 64}
    for query in measured["queries"]:
        if query["phase"] in ("cold_start", "metadata_only", "deferred", "budget_changed", "future_rejected"):
            assert query["legitimate_recorded_events"] == []
        assert all(e["created_at"] < query["query_at"] for e in query["legitimate_recorded_events"])


def test_completion_refusal_and_refresh_are_outcome_changes_not_labels(measured):
    for eid in {q["episode_id"] for q in measured["queries"]}:
        phases = {q["phase"]: q for q in measured["queries"] if q["episode_id"] == eid}
        for phase in ("completed", "unconfirmed_restore_rejected"):
            output = phases[phase]["arms"]["with_memory"]["output"]
            assert output["improvement_percent"] is None
            assert output["status"] == "insufficient_evidence"
            assert phases[phase]["arms"]["without_memory"]["output"]["improvement_percent"] is not None
        refresh = phases["baseline_refreshed"]
        assert refresh["arms"]["with_memory"]["output"]["improvement_percent"] is not None
        assert refresh["arms"]["with_memory"]["criteria"]["completed"] is True


def test_metric_detects_always_abstain_and_ignored_memory(measured):
    always_abstain = {"selected": [], "feasible": [], "status": "insufficient_evidence",
                      "improvement_percent": None, "cost_gbp": None,
                      "electricity_saving_kwh": None, "gas_saving_kwh": None}
    episode = memory.frozen_episodes()[0]
    cold = memory.prefix_truth(episode, episode["steps"][1]["at"])
    assert memory.evaluate_plan_output(always_abstain, cold)["evidence_status"] is False
    # Counterfactual corruption of actual outputs must hurt measured outcomes,
    # not leave a hard-coded "memory success" label in place.
    queries = deepcopy(measured["queries"])
    for query in queries:
        query["arms"]["with_memory"] = deepcopy(query["arms"]["without_memory"])
    summary = memory.summarize_queries(queries)["by_split"]["all"]
    assert summary["with_memory"]["deferred"]["violations"] > 0
    assert summary["with_memory"]["fuel_abstention"]["violations"] == 16


def test_controller_failure_does_not_change_reference_applicability():
    episode = memory.frozen_episodes()[0]
    cold = memory.prefix_truth(episode, episode["steps"][1]["at"])
    assert memory.evaluate_plan_output({"error": "RuntimeError"}, cold) == {
        "deferred": None, "budget": None, "completed": None,
        "fuel_abstention": None, "evidence_status": False,
    }


def test_report_has_no_disposable_bearer_values_or_claimed_user_study(measured):
    encoded = json.dumps(measured)
    assert '"set-cookie"' not in encoded
    assert '"token_hash"' not in encoded
    assert measured["evidence_kind"].endswith("NOT_real_customer_effect")
    assert any("not a better learned algorithm" in line for line in measured["limitations"])
    assert measured["source_hashes_before"] == measured["source_hashes_after"]
