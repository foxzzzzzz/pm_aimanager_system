from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanDateState(StrEnum):
    SCHEDULED = "scheduled"
    TBD = "tbd"
    NOT_APPLICABLE = "not_applicable"


class RaciRole(StrEnum):
    RESPONSIBLE = "R"
    ACCOUNTABLE = "A"
    CONSULTED = "C"
    INFORMED = "I"


class PlanWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: PlanDateState
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_state(self) -> Self:
        has_dates = self.start_date is not None or self.end_date is not None
        if self.state is PlanDateState.SCHEDULED:
            if self.start_date is None or self.end_date is None:
                raise ValueError("scheduled plan windows require start_date and end_date")
            if self.end_date < self.start_date:
                raise ValueError("end_date cannot be earlier than start_date")
        elif has_dates:
            raise ValueError("TBD and not-applicable plan windows cannot contain dates")
        return self


class ProjectIdentity(BaseModel):
    code: str
    name: str


class ProductSpecItem(BaseModel):
    row_number: int
    major_category: str | None = None
    category: str | None = None
    item: str
    configuration: str | None = None
    core_information: str | None = None
    selected_model: str | None = None
    notes: str | None = None
    check_confirmation: str | None = None
    check_content: str | None = None


class ProjectMemberDraft(BaseModel):
    role: str
    name: str
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class MilestoneDefinition(BaseModel):
    code: str
    name: str
    output: str | None = None
    actual_completion: PlanWindow
    variance_days: int | None = None
    variance_note: str | None = None
    risk_note: str | None = None
    assignments: dict[RaciRole, list[str]] = Field(default_factory=dict)


class PlanVersionDraft(BaseModel):
    name: str
    milestones: dict[str, PlanWindow]


class CanonicalProjectDraft(BaseModel):
    template_id: str
    template_version: str
    document_version: str
    source_sha256: str
    project: ProjectIdentity
    product_specs: list[ProductSpecItem]
    members: list[ProjectMemberDraft]
    milestones: list[MilestoneDefinition]
    plan_versions: list[PlanVersionDraft]
    active_plan_name: str

    @property
    def active_plan(self) -> PlanVersionDraft:
        for plan in self.plan_versions:
            if plan.name == self.active_plan_name:
                return plan
        raise ValueError(f"active plan not found: {self.active_plan_name}")
