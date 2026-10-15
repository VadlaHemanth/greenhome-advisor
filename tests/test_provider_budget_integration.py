import json
import pytest

from greenhome import engine, explain
from greenhome.provider_budget import BudgetExceeded, BudgetUnavailable, ProviderBudget


def test_exhausted_budget_blocks_before_sdk(monkeypatch, tmp_path):
    path = tmp_path / "state/attempts.sqlite3"
    ProviderBudget(path, 1).consume()
    monkeypatch.setenv("GREENHOME_PROVIDER_BUDGET_PATH", str(path))
    monkeypatch.setenv("GREENHOME_GEMINI_DAILY_REQUEST_LIMIT", "1")
    with pytest.raises(BudgetExceeded):
        explain._sdk_transport("synthetic-key-no-network", "unit-test")("", {}, 1)


def test_invalid_budget_fails_closed(monkeypatch):
    monkeypatch.setenv("GREENHOME_GEMINI_DAILY_REQUEST_LIMIT", "invalid")
    with pytest.raises(BudgetUnavailable):
        explain._reserve_provider_attempt()


def test_budget_statuses_hide_internal_errors():
    assert explain._failure_status(BudgetExceeded("private internal data")) == "fallback_daily_limit"
    assert explain._failure_status(BudgetUnavailable("private internal data")) == "fallback_budget_unavailable"
    assert "private internal data" not in explain.STATUS_MESSAGES["fallback_budget_unavailable"]


@pytest.mark.parametrize("failure,status", [
    (BudgetExceeded, "fallback_daily_limit"),
    (BudgetUnavailable, "fallback_budget_unavailable"),
])
def test_second_stage_budget_failure_does_not_deny_first_stage_call(failure, status):
    calls = []

    def transport(prompt, schema, timeout):
        payload = json.loads(prompt.split("\n", 1)[1])
        calls.append(payload)
        if "candidate" in payload:
            return payload["candidate"]
        raise failure("private internal data")

    reply = explain.answer_question(
        "Explain my score", engine.demo_homes()[0], [],
        transport=transport, use_gemini=True,
    )
    assert len(calls) == 2
    assert reply.status == status
    assert reply.parser_mode == "live_gemini"
    assert reply.explanation_mode == "local_template"
    assert "no further provider request was sent" in reply.message.lower()
    assert "private internal data" not in reply.message
    assert reply.lines
