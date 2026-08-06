from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class PublishRequest(BaseModel):
    expected_project_version: int = Field(ge=0)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ProgressProposalCreate(BaseModel):
    base_version_number: int = Field(ge=1)
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_date_order(self) -> ProgressProposalCreate:
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


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


class WechatLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=255)


class MemberInvitationCreate(BaseModel):
    member_name: str = Field(min_length=1, max_length=255)
    expected_phone: str | None = Field(default=None, min_length=6, max_length=32)


class InvitationAccept(BaseModel):
    invitation_token: str = Field(min_length=16, max_length=512)
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    phone_code: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def require_phone_source(self) -> InvitationAccept:
        if not self.phone and not self.phone_code:
            raise ValueError("phone or phone_code is required")
        return self


class MilestoneUpdateCreate(BaseModel):
    kind: str = Field(pattern="^(completed|delay)$")
    base_version_number: int = Field(ge=1)
    actual_completion_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> MilestoneUpdateCreate:
        if self.kind == "completed" and self.actual_completion_date is None:
            raise ValueError("actual_completion_date is required for completed updates")
        if self.kind == "delay":
            if self.start_date is None or self.end_date is None:
                raise ValueError("start_date and end_date are required for delay updates")
            if self.start_date > self.end_date:
                raise ValueError("start_date must be on or before end_date")
        return self


class NaturalLanguagePrefillRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
