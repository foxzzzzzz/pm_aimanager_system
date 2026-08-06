class ImportErrorBase(ValueError):
    """Base class for diagnosable import failures."""


class InvalidWorkbookError(ImportErrorBase):
    """The upload is not a supported Office Open XML workbook."""


class WorkbookValidationError(ImportErrorBase):
    """The workbook matches a template but violates its structure or semantics."""


class TemplateNotSupportedError(ImportErrorBase):
    def __init__(self, supported_versions: list[str]) -> None:
        self.supported_versions = supported_versions
        supported = ", ".join(supported_versions)
        super().__init__(f"unknown template; supported versions: {supported}")
