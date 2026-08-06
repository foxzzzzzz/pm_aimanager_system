from pathlib import Path

from project_manager_api.db.base import Base

ROOT = Path(__file__).resolve().parents[3]


def test_phase1_database_metadata_contains_import_and_version_tables() -> None:
    assert set(Base.metadata.tables) == {
        "import_records",
        "project_versions",
        "projects",
    }


def test_phase1_initial_migration_exists() -> None:
    migrations = list((ROOT / "apps" / "api" / "migrations" / "versions").glob("*.py"))

    assert len(migrations) == 1
    migration_text = migrations[0].read_text(encoding="utf-8")
    assert 'revision: str = "0001_phase1"' in migration_text
    assert migration_text.count("op.create_table(") == 3
    assert '"projects",' in migration_text
    assert '"project_versions",' in migration_text
    assert '"import_records",' in migration_text
