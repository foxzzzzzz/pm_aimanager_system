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
        "issue_create_proposals",
        "issue_delete_proposals",
        "in_app_messages",
        "member_bindings",
        "milestone_runtime_states",
        "mobile_sessions",
        "mobile_users",
        "notification_deliveries",
        "project_memberships",
        "project_change_sets",
        "project_versions",
        "projects",
        "wechat_subscription_grants",
    }
    assert "base_runtime_revision" in Base.metadata.tables["change_proposals"].c
    assert {
        "schedule_plan_name",
        "schedule_revision",
        "completion_revision",
    }.issubset(Base.metadata.tables["milestone_runtime_states"].c.keys())


def test_database_migration_chain_exists() -> None:
    migrations = list((ROOT / "apps" / "api" / "migrations" / "versions").glob("*.py"))

    assert len(migrations) == 12
    revisions = "\n".join(path.read_text(encoding="utf-8") for path in migrations)
    assert 'revision: str = "0001_phase1"' in revisions
    assert 'revision: str = "0002_phase2"' in revisions
    assert 'revision: str = "0003_phase3"' in revisions
    assert 'revision: str = "0004_phase31"' in revisions
    assert 'revision: str = "0005_phase4"' in revisions
    assert 'revision: str = "0006_change_sets"' in revisions
    assert 'revision: str = "0007_reliability_hardening"' in revisions
    assert 'revision: str = "0008_issue_raci"' in revisions
    assert 'revision: str = "0009_project_manager_permissions"' in revisions
    assert 'revision: str = "0010_issue_create_proposals"' in revisions
    assert 'revision: str = "0011_issue_delete_proposals"' in revisions
    assert 'revision: str = "0012_milestone_runtime_states"' in revisions
    assert '"base_runtime_revision"' in revisions
    assert "substr(phone, length(phone) - 3, 4)" in revisions
    for table in (
        "audit_logs",
        "change_proposals",
        "idempotency_records",
        "issues",
        "issue_create_proposals",
        "issue_delete_proposals",
        "project_memberships",
        "project_change_sets",
        "mobile_users",
        "mobile_sessions",
        "member_bindings",
        "milestone_runtime_states",
        "in_app_messages",
    ):
        assert f'"{table}",' in revisions
