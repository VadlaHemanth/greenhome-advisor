import json
import pytest

from greenhome import engine, explain


@pytest.mark.parametrize("question", [
    "What should I do first?", "What should I improve first?",
    "Which improvements suit my home?", "Explain this plan",
])
def test_common_explanation_does_not_install_anything(question):
    proposal = explain.parse_local(question)
    assert proposal.action == "explain"
    assert proposal.topic == "feasibility"
    assert proposal.retrofit_ids == ()


@pytest.mark.parametrize("question,detail", [
    ("I have £5,000. What should I do first?", "budget"),
    ("How much will my bills go down?", "tariffs"),
    ("Remember that I do not want solar panels", "saved demo workspace"),
    ("I installed loft insulation last month", "new measured baseline"),
])
def test_unsupported_changes_give_actionable_guidance_without_provider(question, detail):
    def forbidden(*args):
        pytest.fail("Unsupported input should not contact Gemini.")
    result = explain.answer_question(
        question, engine.demo_homes()[0], [],
        transport=forbidden, use_gemini=True,
    )
    assert result.needs_clarification
    assert not result.applied
    assert detail in result.message
    assert result.selected_retrofits == []


def test_provider_deadline_has_timeout_status():
    class ProviderTimeout(Exception):
        code = 504
    assert explain._failure_status(ProviderTimeout()) == "fallback_timeout"


def test_single_provider_call_occurs_only_after_validated_recalculation():
    calls = []
    home = engine.demo_homes()[0]
    def transport(prompt, schema, remaining):
        payload = json.loads(prompt.split("\n", 1)[1])
        assert "candidate" not in payload
        assert payload["selected_retrofits"] == ["loft_insulation", "heat_pump"]
        assert "energy.electricity_increase" in payload["claims"]
        calls.append(payload)
        return {"claim_ids": ["energy.electricity", "energy.gas"]}
    result = explain.answer_question(
        "Add loft insulation and a heat pump", home, [], transport=transport,
        interpret_with_gemini=False,
    )
    assert len(calls) == 1
    assert result.status == "live_gemini"
    assert result.parser_mode == "local_rules"
    assert result.explanation_mode == "live_gemini"
    assert result.applied
    assert result.assessment["home"]["epc_rating"] == home["epc_rating"]
    assert result.lines == [explain.build_claims(result.assessment)[key] for key in result.claim_ids]


def test_single_call_mode_infeasible_selection_does_not_reach_provider():
    home = {**engine.demo_homes()[0], "roof_access": False}
    def forbidden(*args):
        pytest.fail("Infeasible changes must not use a provider.")
    result = explain.answer_question(
        "Add solar panels", home, [], transport=forbidden, interpret_with_gemini=False,
    )
    assert result.needs_clarification
    assert not result.applied
