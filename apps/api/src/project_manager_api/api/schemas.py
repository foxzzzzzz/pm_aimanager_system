from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class PublishRequest(BaseModel):
    expected_project_version: int = Field(ge=0)


class ProjectDataOperation(BaseModel):
    op: str = Field(pattern="^(add|replace|remove)$")
    resource: str = Field(pattern="^(product_spec|member|milestone|plan|raci)$")
    key: str = Field(min_length=1, max_length=255)
    value: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_value(self) -> ProjectDataOperation:
        if self.op == "remove" and self.value is not None:
            raise ValueError("remove operations cannot contain value")
        if self.op != "remove" and self.value is None:
            raise ValueError("add and replace operations require value")
        return self


class ProjectChangeSetCreate(BaseModel):
    base_version_number: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    operations: list[ProjectDataOperation] = Field(min_length=1, max_length=100)


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
    accountable_names: list[str] = Field(min_length=1)
    consulted_names: list[str] = Field(default_factory=list)
    informed_names: list[str] = Field(default_factory=list)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    due_date: date

    @field_validator("accountable_names", "consulted_names", "informed_names")
    @classmethod
    def normalize_role_names(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(name.strip() for name in values if name.strip()))
        if values and not normalized:
            raise ValueError("issue RACI member names cannot be blank")
        return normalized


class IssueUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    impact: str | None = Field(default=None, min_length=1, max_length=5000)
    owner_name: str | None = Field(default=None, min_length=1, max_length=255)
    accountable_names: list[str] | None = Field(default=None, min_length=1)
    consulted_names: list[str] | None = None
    informed_names: list[str] | None = None
    severity: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    due_date: date | None = None
    status: str | None = Field(
        default=None,
        pattern="^(待处理|处理中|待验证|已解决|已关闭)$",
    )

    @field_validator("accountable_names", "consulted_names", "informed_names")
    @classmethod
    def normalize_role_names(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(dict.fromkeys(name.strip() for name in values if name.strip()))
        if values and not normalized:
            raise ValueError("issue RACI member names cannot be blank")
        return normalized


class IssueDelete(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


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


class SubscriptionGrantCreate(BaseModel):
    template_id: str = Field(min_length=1, max_length=128)


class NotificationScanRequest(BaseModel):
    business_date: date | None = None
