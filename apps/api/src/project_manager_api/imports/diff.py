from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class DiffOperation(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


class DiffEntry(BaseModel):
    path: str
    operation: DiffOperation
    before: Any = None
    after: Any = None


def semantic_diff(before: Any, after: Any) -> list[DiffEntry]:
    changes: list[DiffEntry] = []
    _compare(before, after, "", changes)
    return changes


def _compare(before: Any, after: Any, path: str, changes: list[DiffEntry]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append(
                    DiffEntry(path=child_path, operation=DiffOperation.ADDED, after=after[key])
                )
            elif key not in after:
                changes.append(
                    DiffEntry(path=child_path, operation=DiffOperation.REMOVED, before=before[key])
                )
            else:
                _compare(before[key], after[key], child_path, changes)
        return
    if isinstance(before, list) and isinstance(after, list):
        if _is_keyed_list(before) and _is_keyed_list(after):
            _compare_keyed_lists(before, after, path, changes)
            return
        for index in range(max(len(before), len(after))):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                changes.append(
                    DiffEntry(path=child_path, operation=DiffOperation.ADDED, after=after[index])
                )
            elif index >= len(after):
                changes.append(
                    DiffEntry(
                        path=child_path, operation=DiffOperation.REMOVED, before=before[index]
                    )
                )
            else:
                _compare(before[index], after[index], child_path, changes)
        return
    if before != after:
        changes.append(
            DiffEntry(path=path, operation=DiffOperation.CHANGED, before=before, after=after)
        )


def _is_keyed_list(value: list[Any]) -> bool:
    return bool(value) and all(isinstance(item, dict) and "code" in item for item in value)


def _compare_keyed_lists(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    path: str,
    changes: list[DiffEntry],
) -> None:
    before_by_code = {str(item["code"]): item for item in before}
    after_by_code = {str(item["code"]): item for item in after}
    for code in sorted(before_by_code.keys() | after_by_code.keys()):
        child_path = f"{path}[{code}]"
        if code not in before_by_code:
            changes.append(
                DiffEntry(
                    path=child_path,
                    operation=DiffOperation.ADDED,
                    after=after_by_code[code],
                )
            )
        elif code not in after_by_code:
            changes.append(
                DiffEntry(
                    path=child_path,
                    operation=DiffOperation.REMOVED,
                    before=before_by_code[code],
                )
            )
        else:
            _compare(before_by_code[code], after_by_code[code], child_path, changes)
