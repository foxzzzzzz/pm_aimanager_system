from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError
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
        max_retries: int = 2,
        structured_output_mode: str = "auto",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.structured_output_mode = structured_output_mode

    def generate_structured(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        sanitized_text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[PHONE]", text)
        modes = (
            ["strict", "json"]
            if self.structured_output_mode == "auto"
            else [self.structured_output_mode]
        )
        last_error: Exception | None = None
        for mode in modes:
            try:
                return self._request(sanitized_text, schema, mode)
            except HTTPError as exc:
                last_error = exc
                if mode == "strict" and self.structured_output_mode == "auto" and exc.code in {
                    400,
                    404,
                    422,
                }:
                    continue
                raise ServiceError("LLM structured output request failed") from exc
        raise ServiceError("LLM structured output request failed") from last_error

    def _request(self, text: str, schema: dict[str, Any], mode: str) -> dict[str, Any]:
        response_format: dict[str, Any]
        if mode == "strict":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "milestone_update_prefill",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            response_format = {"type": "json_object"}
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract a project milestone update. Return only fields allowed by the "
                        "provided JSON schema. Never approve or publish a change. "
                        f"Schema: {json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": text},
            ],
            "response_format": response_format,
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
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    response_payload = json.load(response)
                content = response_payload["choices"][0]["message"]["content"]
                result = json.loads(content)
            except HTTPError:
                raise
            except OSError as exc:
                if attempt == self.max_retries:
                    raise ServiceError("LLM structured output request failed") from exc
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if attempt == self.max_retries:
                    raise ServiceError("LLM structured output request failed") from exc
            else:
                if not isinstance(result, dict):
                    if attempt == self.max_retries:
                        raise ServiceError("LLM structured output must be an object")
                    continue
                try:
                    validate(instance=result, schema=schema)
                except ValidationError as exc:
                    if attempt == self.max_retries:
                        raise ServiceError(
                            "LLM structured output violates JSON Schema"
                        ) from exc
                    continue
                return result
        raise ServiceError("LLM structured output request failed")
