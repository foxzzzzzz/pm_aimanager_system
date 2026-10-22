from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, model_validator


class Marker(BaseModel):
    sheet: str
    cell: str
    contains: str | None = None
    equals: str | None = None


class ProductSpecConfig(BaseModel):
    sheet: str
    first_row: int
    last_row: int
    columns: dict[str, str]


class TeamConfig(BaseModel):
    sheet: str
    first_row: int
    last_row: int
    project_manager_role: str
    columns: dict[str, str]


class ProgressConfig(BaseModel):
    sheet: str
    milestone_header_row: int
    first_milestone_column: int
    plan_first_row: int
    plan_last_row: int
    actual_completion_row: int
    variance_days_row: int
    variance_note_row: int
    risk_note_row: int
    raci_rows: dict[str, int]
    output_row: int


class MilestoneConfig(BaseModel):
    code: str
    name: str
    legacy_code: str | None = None


class TemplateManifest(BaseModel):
    template_id: str
    template_version: str
    legacy_template_version: str | None = None
    required_sheets: dict[str, str]
    identity_markers: list[Marker]
    required_markers: list[Marker]
    product_specs: ProductSpecConfig
    team: TeamConfig
    progress: ProgressConfig
    milestones: list[MilestoneConfig]

    @model_validator(mode="after")
    def validate_legacy_codes(self) -> Self:
        if self.legacy_template_version is not None:
            codes = [milestone.legacy_code for milestone in self.milestones]
            if any(not code for code in codes) or len(codes) != len(set(codes)):
                raise ValueError("legacy milestone codes must be complete and unique")
        return self

    @property
    def identifier(self) -> str:
        return f"{self.template_id}/{self.template_version}"


def load_manifest(path: Path) -> TemplateManifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return TemplateManifest.model_validate(data)
