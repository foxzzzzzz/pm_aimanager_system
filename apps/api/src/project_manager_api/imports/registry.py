from pathlib import Path
from zipfile import BadZipFile, is_zipfile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from project_manager_api.imports.errors import InvalidWorkbookError, TemplateNotSupportedError
from project_manager_api.imports.lyra_v1 import LyraTemplateV1Parser
from project_manager_api.imports.manifest import load_manifest
from project_manager_api.imports.report import ParseResult


class ParserRegistry:
    def __init__(self, parsers: list[LyraTemplateV1Parser]) -> None:
        self._parsers = parsers

    @classmethod
    def from_manifest_paths(cls, paths: list[Path]) -> "ParserRegistry":
        return cls([LyraTemplateV1Parser(load_manifest(path)) for path in paths])

    @property
    def supported_versions(self) -> list[str]:
        return [parser.manifest.identifier for parser in self._parsers]

    def parse(self, path: Path) -> ParseResult:
        if path.suffix.lower() != ".xlsx":
            raise InvalidWorkbookError("only .xlsx workbooks are supported")
        if not path.is_file() or not is_zipfile(path):
            raise InvalidWorkbookError("file is not a valid Office Open XML workbook")
        try:
            workbook = load_workbook(path, data_only=False, read_only=False)
        except (BadZipFile, InvalidFileException, KeyError, OSError) as exc:
            raise InvalidWorkbookError("file is not a readable .xlsx workbook") from exc
        try:
            for parser in self._parsers:
                if parser.has_template_identity(workbook):
                    return parser.parse_workbook(workbook, path)
        finally:
            workbook.close()
        raise TemplateNotSupportedError(self.supported_versions)
