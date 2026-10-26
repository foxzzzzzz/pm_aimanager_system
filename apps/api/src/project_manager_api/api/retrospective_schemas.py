from __future__ import annotations

import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class RetrospectiveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    baseline_version_number: int | None = Field(default=None, ge=1)
    baseline_plan_name: Text | None = None
    supersedes_report_id: uuid.UUID | None = None


class ReasonReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    milestone_code: Text
    category: str = ""
    confirmed_reason: str = ""
    evidence: str = ""
    fact_confirmed_by: str = ""
    confirmation_source: str = ""
    status: Literal["pending", "confirmed"] = "pending"

    @model_validator(mode="after")
    def require_confirmation_evidence(self) -> Self:
        if self.status == "confirmed" and not all(
            (
                self.category,
                self.confirmed_reason,
                self.evidence,
                self.fact_confirmed_by,
                self.confirmation_source,
            )
        ):
            raise ValueError("confirmed reasons require reason, evidence, confirmer and source")
        return self


class ImprovementRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    milestone_code: Text | None = None
    source_event_ids: list[Text] = Field(default_factory=list)
    scenario: Text
    action: Text
    proposed_owner: Text
    acceptance: Text


class RetrospectiveUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    baseline_confirmed: bool
    baseline_note: str = ""
    reason_reviews: list[ReasonReview] = Field(default_factory=list)
    improvements: list[ImprovementRegistration] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_baseline_note(self) -> Self:
        if self.baseline_confirmed and not self.baseline_note:
            raise ValueError("baseline confirmation requires a supporting note")
        return self


class RetrospectiveConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
