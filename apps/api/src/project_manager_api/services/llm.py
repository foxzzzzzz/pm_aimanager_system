from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from jsonschema import ValidationError, validate

from project_manager_api.services.errors import ServiceError


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_structured(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract a project milestone update. Return only fields allowed by the "
                        "provided JSON schema. Never approve or publish a change."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "milestone_update_prefill",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.load(response)
            content = response_payload["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (OSError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ServiceError("LLM structured output request failed") from exc
        if not isinstance(result, dict):
            raise ServiceError("LLM structured output must be an object")
        try:
            validate(instance=result, schema=schema)
        except ValidationError as exc:
            raise ServiceError("LLM structured output violates JSON Schema") from exc
        return result
