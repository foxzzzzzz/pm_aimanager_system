from project_manager_api.imports.diff import DiffOperation, semantic_diff


def test_semantic_diff_reports_field_level_changes() -> None:
    before = {
        "project": {"code": "ZPD1322", "name": "Lyra Pro"},
        "milestones": [{"code": "M01", "end_date": "2026-07-30"}],
    }
    after = {
        "project": {"code": "ZPD1322", "name": "Lyra Pro"},
        "milestones": [{"code": "M01", "end_date": "2026-08-01"}],
    }

    changes = semantic_diff(before, after)

    assert len(changes) == 1
    assert changes[0].operation is DiffOperation.CHANGED
    assert changes[0].path == "milestones[M01].end_date"
    assert changes[0].before == "2026-07-30"
    assert changes[0].after == "2026-08-01"


def test_semantic_diff_is_empty_for_identical_documents() -> None:
    document = {"project": {"code": "ZPD1322"}, "milestones": []}

    assert semantic_diff(document, document) == []
