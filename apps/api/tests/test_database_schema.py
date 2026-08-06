from pathlib import Path

from project_manager_api.db.base import Base

ROOT = Path(__file__).resolve().parents[3]


def test_phase1_database_metadata_contains_import_and_version_tables() -> None:
    assert set(Base.metadata.tables) == {
        "audit_logs",
        "change_proposals",
        "idempotency_records",
        "import_records",
        "issues",
        "project_memberships",
        "project_versions",
        "projects",
    }


def test_phase1_initial_migration_exists() -> None:
    migrations = list((ROOT / "apps" / "api" / "migrations" / "versions").glob("*.py"))

    assert len(migrations) == 2
    revisions = "\n".join(path.read_text(encoding="utf-8") for path in migrations)
    assert 'revision: str = "0001_phase1"' in revisions
    assert 'revision: str = "0002_phase2"' in revisions
    for table in (
        "audit_logs",
        "change_proposals",
        "idempotency_records",
        "issues",
        "project_memberships",
    ):
        assert f'"{table}",' in revisions
