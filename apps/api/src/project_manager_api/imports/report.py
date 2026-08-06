from pydantic import BaseModel, Field

from project_manager_api.domain.models import CanonicalProjectDraft


class ImportCounts(BaseModel):
    product_specs: int
    members: int
    milestones: int
    plan_versions: int


class ImportReport(BaseModel):
    template: str
    source_sha256: str
    counts: ImportCounts
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ParseResult(BaseModel):
    draft: CanonicalProjectDraft
    report: ImportReport
