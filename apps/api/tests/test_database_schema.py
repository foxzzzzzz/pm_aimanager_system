from pathlib import Path

from project_manager_api.db.base import Base

ROOT = Path(__file__).resolve().parents[3]


def test_database_metadata_contains_versioned_project_data_tables() -> None:
    assert set(Base.metadata.tables) == {
        "audit_logs",
        "change_proposals",
        "idempotency_records",
        "import_records",
        "issues",
        "in_app_messages",
        "member_bindings",
        "mobile_sessions",
        "mobile_users",
        "notification_deliveries",
        "project_memberships",
        "project_change_sets",
        "project_versions",
        "projects",
        "wechat_subscription_grants",
    }


def test_database_migration_chain_exists() -> None:
    migrations = list((ROOT / "apps" / "api" / "migrations" / "versions").glob("*.py"))

    assert len(migrations) == 8
    revisions = "\n".join(path.read_text(encoding="utf-8") for path in migrations)
    assert 'revision: str = "0001_phase1"' in revisions
    assert 'revision: str = "0002_phase2"' in revisions
    assert 'revision: str = "0003_phase3"' in revisions
    assert 'revision: str = "0004_phase31"' in revisions
    assert 'revision: str = "0005_phase4"' in revisions
    assert 'revision: str = "0006_change_sets"' in revisions
    assert 'revision: str = "0007_reliability_hardening"' in revisions
    assert 'revision: str = "0008_issue_raci"' in revisions
    assert "substr(phone, length(phone) - 3, 4)" in revisions
    for table in (
        "audit_logs",
        "change_proposals",
        "idempotency_records",
        "issues",
        "project_memberships",
        "project_change_sets",
        "mobile_users",
        "mobile_sessions",
        "member_bindings",
        "in_app_messages",
    ):
        assert f'"{table}",' in revisions
