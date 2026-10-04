import asyncio
from types import SimpleNamespace

import httpx

from api.filtering import ollama


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self.response


class SequenceClient:
    def __init__(self, responses):
        self.responses = responses
        self.request_count = 0

    async def post(self, url, **kwargs):
        self.request_count += 1
        return self.responses.pop(0)


def openai_response():
    return httpx.Response(
        200,
        json={
            "choices": [{
                "message": {
                    "content": '{"results":[{"index":1,"allow":true,"category":"technology","language":"en","confidence":0.9,"reason":"Relevant tutorial"}]}'
                }
            }]
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )


def test_openai_provider_sends_authorized_chat_completion(monkeypatch):
    monkeypatch.setattr(ollama, "AI_PROVIDER", "openai")
    monkeypatch.setattr(ollama, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ollama, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(ollama, "OPENAI_MODEL", "gpt-test")
    client = FakeClient(FakeResponse({
        "choices": [{
            "message": {
                "content": '{"results":[{"index":1,"allow":true,"category":"technology","language":"en","confidence":0.9,"reason":"Relevant tutorial"}]}'
            }
        }]
    }))
    video = SimpleNamespace(
        title="Python tutorial",
        channel="Example",
        description="A useful guide",
        tags=["python"],
    )

    results, _ = asyncio.run(ollama._classify_batch(client, [video], "learn python", 1, 1))

    url, request = client.request
    assert url == "https://api.openai.com/v1/chat/completions"
    assert request["headers"] == {"Authorization": "Bearer test-key"}
    assert request["json"]["model"] == "gpt-test"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert "learn python" in request["json"]["messages"][1]["content"]
    assert results[0]["allow"] is True
    assert results[0]["confidence"] == 0.9


def test_ollama_provider_remains_available(monkeypatch):
    monkeypatch.setattr(ollama, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(ollama, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(ollama, "OLLAMA_MODEL", "local-test")
    client = FakeClient(FakeResponse({
        "message": {
            "content": '{"results":[{"index":1,"allow":true,"category":"technology","language":"en","confidence":0.8,"reason":"Relevant"}]}'
        }
    }))
    video = SimpleNamespace(title="Local test", channel="", description="", tags=[])

    results, _ = asyncio.run(ollama._classify_batch(client, [video], "test", 1, 1))

    url, request = client.request
    assert url == "http://localhost:11434/api/chat"
    assert request["json"]["model"] == "local-test"
    assert request["json"]["format"] == "json"
    assert results[0]["allow"] is True


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr(ollama, "AI_PROVIDER", "openai")
    monkeypatch.setattr(ollama, "OPENAI_API_KEY", "")
    video = SimpleNamespace(title="Test", channel="", description="", tags=[])

    results = asyncio.run(ollama.classify_videos([video]))

    assert results[0]["allow"] is False
    assert "OPENAI_API_KEY is required" in results[0]["reason"]


def test_openai_rate_limit_retries_after_retry_header(monkeypatch):
    monkeypatch.setattr(ollama, "AI_PROVIDER", "openai")
    monkeypatch.setattr(ollama, "OPENAI_API_KEY", "test-key")

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(ollama.asyncio, "sleep", no_wait)
    rate_limited = httpx.Response(
        429,
        json={"error": {"code": "rate_limit_exceeded", "message": "Please retry."}},
        headers={"Retry-After": "0"},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    client = SequenceClient([rate_limited, openai_response()])
    video = SimpleNamespace(title="Test", channel="", description="", tags=[])

    results, _ = asyncio.run(ollama._classify_batch(client, [video], "test", 1, 1))

    assert client.request_count == 2
    assert results[0]["allow"] is True


def test_openai_quota_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(ollama, "AI_PROVIDER", "openai")
    monkeypatch.setattr(ollama, "OPENAI_API_KEY", "test-key")
    quota_error = httpx.Response(
        429,
        json={"error": {"code": "insufficient_quota", "message": "Quota exceeded."}},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    client = SequenceClient([quota_error])
    video = SimpleNamespace(title="Test", channel="", description="", tags=[])

    results, _ = asyncio.run(ollama._classify_batch(client, [video], "test", 1, 1))

    assert client.request_count == 1
    assert results[0]["allow"] is False
    assert "Check the API account's billing" in results[0]["reason"]
