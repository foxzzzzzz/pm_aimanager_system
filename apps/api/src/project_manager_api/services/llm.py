from __future__ import annotations

import json
import random
import re
from time import sleep
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
        retry_base_delay_seconds: float = 0.5,
        retry_max_delay_seconds: float = 8,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.structured_output_mode = structured_output_mode
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds

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
            except HTTPError as exc:
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise
                if attempt == self.max_retries:
                    raise ServiceError("LLM structured output request failed") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
                self._wait_before_retry(attempt, retry_after)
            except OSError as exc:
                if attempt == self.max_retries:
                    raise ServiceError("LLM structured output request failed") from exc
                self._wait_before_retry(attempt)
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if attempt == self.max_retries:
                    raise ServiceError("LLM structured output request failed") from exc
                self._wait_before_retry(attempt)
            else:
                if not isinstance(result, dict):
                    if attempt == self.max_retries:
                        raise ServiceError("LLM structured output must be an object")
                    self._wait_before_retry(attempt)
                    continue
                try:
                    validate(instance=result, schema=schema)
                except ValidationError as exc:
                    if attempt == self.max_retries:
                        raise ServiceError(
                            "LLM structured output violates JSON Schema"
                        ) from exc
                    self._wait_before_retry(attempt)
                    continue
                return result
        raise ServiceError("LLM structured output request failed")

    def _wait_before_retry(self, attempt: int, retry_after: str | None = None) -> None:
        if retry_after is not None:
            try:
                delay = min(float(retry_after), self.retry_max_delay_seconds)
            except ValueError:
                delay = self._jittered_delay(attempt)
        else:
            delay = self._jittered_delay(attempt)
        sleep(max(0, delay))

    def _jittered_delay(self, attempt: int) -> float:
        ceiling = min(
            self.retry_base_delay_seconds * (2**attempt),
            self.retry_max_delay_seconds,
        )
        return random.uniform(ceiling * 0.5, ceiling)
