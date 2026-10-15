import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from greenhome import api, engine, explain, providers


def test_provider_configuration_never_exposes_key(monkeypatch):
    monkeypatch.setenv("GREENHOME_LLM_PROVIDER", "xkiro")
    monkeypatch.setenv("XKIRO_API_KEY", "test-secret-not-live")
    monkeypatch.setenv("GREENHOME_LIVE_LLM", "true")
    p = providers.configured_provider()
    assert p.configured and p.name == "xkiro"
    assert p.model == "qwen/qwen3.8-max:free"
    assert p.public()["llm_label"] == "Qwen via Xkiro"
    assert p.key not in repr(p) and p.key not in json.dumps(p.public())


def test_invalid_provider_does_not_silently_switch(monkeypatch):
    monkeypatch.setenv("GREENHOME_LLM_PROVIDER", "other")
    with pytest.raises(RuntimeError):
        providers.configured_provider()


def mock_sdk(monkeypatch, content='{"claim_ids":["score.summary"]}', finish="stop"):
    calls = []
    class Client:
        def __init__(self, **kw):
            calls.append(("client", kw))
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            calls.append(("closed", True))
        def create(self, **kw):
            calls.append(("request", kw))
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(content=content, tool_calls=None, refusal=None),
            )])
    import openai
    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(openai, "DefaultHttpxClient", lambda **kw: kw)
    monkeypatch.setattr(explain, "_reserve_provider_attempt", lambda: calls.append(("reserved", True)))
    return calls


def test_xkiro_transport_fixed_destination_bounded_and_closed(monkeypatch):
    calls = mock_sdk(monkeypatch)
    answer = providers.xkiro_transport("test-no-network", providers.XKIRO_MODEL)("Select JSON", {}, 12)
    assert answer == {"claim_ids":["score.summary"]}
    assert calls[0][0] == "reserved"
    options = calls[1][1]
    assert options["base_url"] == "https://api.xkiro.com/v1"
    assert options["max_retries"] == 0
    assert options["timeout"] == 12
    assert options["http_client"]["follow_redirects"] is False
    request = calls[2][1]
    assert request["response_format"] == {"type":"json_object"}
    assert request["max_tokens"] == 768 and request["stream"] is False
    assert calls[-1] == ("closed", True)


@pytest.mark.parametrize("text", [
    '```json\n{"claim_ids":["score.summary"]}\n```',
    '{"claim_ids":[],"claim_ids":["score.summary"]}', 'NaN', '[]', '{} trailing',
    '', '{"value": Infinity}',
])
def test_bad_json_is_rejected(monkeypatch, text):
    mock_sdk(monkeypatch, text)
    with pytest.raises(explain.InvalidResponse):
        providers.xkiro_transport("fake", providers.XKIRO_MODEL)("", {}, 1)


@pytest.mark.parametrize("finish", ["length","content_filter","tool_calls",None])
def test_incomplete_generation_is_rejected(monkeypatch, finish):
    mock_sdk(monkeypatch, finish=finish)
    with pytest.raises(explain.InvalidResponse):
        providers.xkiro_transport("fake", providers.XKIRO_MODEL)("", {}, 1)


def test_api_calls_active_provider_once_after_recalculation(monkeypatch):
    monkeypatch.setenv("GREENHOME_LLM_PROVIDER", "xkiro")
    monkeypatch.setenv("XKIRO_API_KEY", "synthetic-key")
    monkeypatch.setenv("GREENHOME_LIVE_LLM", "true")
    calls = []
    def factory(key, model):
        assert key == "synthetic-key"
        assert model == providers.XKIRO_MODEL
        def run(prompt, schema, timeout):
            evidence = json.loads(prompt.split("\n",1)[1])
            assert evidence["selected_retrofits"] == ["heat_pump"]
            assert "energy.electricity_increase" in evidence["claims"]
            calls.append(evidence)
            return {"claim_ids":["energy.electricity","energy.gas"]}
        return run
    monkeypatch.setattr(api, "xkiro_transport", factory)
    c = TestClient(api.create_app(load_environment=False))
    health = c.get("/api/health").json()
    assert health["llm_configured"] and health["llm_provider"] == "xkiro"
    response = c.post("/api/what-if", json={
        "home":engine.demo_homes()[0], "selected_retrofits":[],
        "question":"Add a heat pump", "use_gemini":True,
    })
    assert response.status_code == 200
    r=response.json()
    assert len(calls)==1 and r["status"]=="live_llm"
    assert r["provider"]=="xkiro" and r["explanation_mode"]=="live_llm"
    assert "Gemini" not in r["message"]
    assert "synthetic-key" not in response.text


def test_active_provider_failure_stays_local_no_google_fallback(monkeypatch):
    def failed(*args):
        raise RuntimeError("provider confidential details")
    r=explain.answer_question("Explain my score",engine.demo_homes()[0],[],
        transport=failed, provider="xkiro", model_name=providers.XKIRO_MODEL,
        interpret_with_gemini=False)
    assert r.status=="fallback_error" and r.explanation_mode=="local_template"
    assert "provider confidential details" not in repr(r)
    assert "Gemini" not in r.message
