from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class PublishRequest(BaseModel):
    expected_project_version: int = Field(ge=0)


class ProgressProposalCreate(BaseModel):
    base_version_number: int = Field(ge=1)
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=2000)


class IssueCreate(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    impact: str = Field(min_length=1, max_length=5000)
    owner_name: str = Field(min_length=1, max_length=255)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    due_date: date


class IssueUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    impact: str | None = Field(default=None, min_length=1, max_length=5000)
    owner_name: str | None = Field(default=None, min_length=1, max_length=255)
    severity: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    due_date: date | None = None
    status: str | None = Field(
        default=None,
        pattern="^(待处理|处理中|待验证|已解决|已关闭)$",
    )


class ApiRecord(BaseModel):
    id: str
    data: dict[str, Any] = Field(default_factory=dict)
