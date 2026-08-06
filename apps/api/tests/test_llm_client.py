import io
import json
from typing import Any, cast
from urllib.request import Request

import pytest

from project_manager_api.services.errors import ServiceError
from project_manager_api.services.llm import OpenAICompatibleClient


def test_openai_compatible_client_requests_strict_json_schema(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(cast(bytes, request.data))
        captured["timeout"] = timeout
        response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "milestone_code": "M23",
                            }
                        )
                    }
                }
            ]
        }
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("project_manager_api.services.llm.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        base_url="https://llm.example/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=12,
    )

    result = client.generate_structured(
        "M23延期到2026-08-30，原因是驱动联调",
        {
            "type": "object",
            "properties": {"milestone_code": {"type": "string"}},
            "required": ["milestone_code"],
            "additionalProperties": False,
        },
    )

    assert result["milestone_code"] == "M23"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["timeout"] == 12


def test_openai_compatible_client_rejects_output_that_violates_schema(
    monkeypatch: Any,
) -> None:
    def fake_urlopen(_request: Request, timeout: int) -> io.BytesIO:
        del timeout
        response = {"choices": [{"message": {"content": '{"kind":"delay"}'}}]}
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("project_manager_api.services.llm.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        base_url="https://llm.example/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=12,
    )

    with pytest.raises(ServiceError, match="violates JSON Schema"):
        client.generate_structured(
            "M23延期",
            {
                "type": "object",
                "properties": {"milestone_code": {"type": "string"}},
                "required": ["milestone_code"],
                "additionalProperties": False,
            },
        )
