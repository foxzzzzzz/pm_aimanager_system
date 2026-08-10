import multiprocessing
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile, is_zipfile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from project_manager_api.imports.errors import InvalidWorkbookError, TemplateNotSupportedError
from project_manager_api.imports.lyra_v1 import LyraTemplateV1Parser
from project_manager_api.imports.manifest import load_manifest
from project_manager_api.imports.report import ParseResult


class ParserRegistry:
    def __init__(self, parsers: list[LyraTemplateV1Parser], manifest_paths: list[Path]) -> None:
        self._parsers = parsers
        self._manifest_paths = manifest_paths

    @classmethod
    def from_manifest_paths(cls, paths: list[Path]) -> "ParserRegistry":
        return cls([LyraTemplateV1Parser(load_manifest(path)) for path in paths], paths)

    @property
    def supported_versions(self) -> list[str]:
        return [parser.manifest.identifier for parser in self._parsers]

    def parse(
        self,
        path: Path,
        *,
        max_uncompressed_size_bytes: int | None = None,
        max_archive_entries: int | None = None,
    ) -> ParseResult:
        if path.suffix.lower() != ".xlsx":
            raise InvalidWorkbookError("only .xlsx workbooks are supported")
        if not path.is_file() or not is_zipfile(path):
            raise InvalidWorkbookError("file is not a valid Office Open XML workbook")
        self._validate_archive_limits(
            path,
            max_uncompressed_size_bytes=max_uncompressed_size_bytes,
            max_archive_entries=max_archive_entries,
        )
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

    def parse_isolated(
        self,
        path: Path,
        *,
        timeout_seconds: float,
        max_uncompressed_size_bytes: int,
        max_archive_entries: int,
    ) -> ParseResult:
        context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_parse_in_child,
            args=(
                self._manifest_paths,
                path,
                max_uncompressed_size_bytes,
                max_archive_entries,
                child_connection,
            ),
        )
        process.start()
        child_connection.close()
        if not parent_connection.poll(timeout_seconds):
            process.terminate()
            process.join()
            parent_connection.close()
            raise InvalidWorkbookError("workbook parsing timed out")
        try:
            status, payload = parent_connection.recv()
        except EOFError as exc:
            raise InvalidWorkbookError("workbook parser process failed") from exc
        finally:
            parent_connection.close()
            process.join()
        if status == "error":
            raise InvalidWorkbookError(str(payload))
        return ParseResult.model_validate(payload)

    @staticmethod
    def _validate_archive_limits(
        path: Path,
        *,
        max_uncompressed_size_bytes: int | None,
        max_archive_entries: int | None,
    ) -> None:
        try:
            with ZipFile(path) as archive:
                entries = archive.infolist()
                if max_archive_entries is not None and len(entries) > max_archive_entries:
                    raise InvalidWorkbookError("workbook exceeds configured archive entry limit")
                expanded_size = sum(entry.file_size for entry in entries)
                if (
                    max_uncompressed_size_bytes is not None
                    and expanded_size > max_uncompressed_size_bytes
                ):
                    raise InvalidWorkbookError("workbook exceeds configured expanded size limit")
        except BadZipFile as exc:
            raise InvalidWorkbookError("file is not a valid Office Open XML workbook") from exc


def _parse_in_child(
    manifest_paths: list[Path],
    path: Path,
    max_uncompressed_size_bytes: int,
    max_archive_entries: int,
    connection: Any,
) -> None:
    try:
        result = ParserRegistry.from_manifest_paths(manifest_paths).parse(
            path,
            max_uncompressed_size_bytes=max_uncompressed_size_bytes,
            max_archive_entries=max_archive_entries,
        )
    except Exception as exc:
        connection.send(("error", str(exc)))
    else:
        connection.send(("ok", result.model_dump(mode="json")))
    finally:
        connection.close()
