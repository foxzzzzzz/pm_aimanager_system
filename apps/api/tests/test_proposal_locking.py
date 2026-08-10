from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from project_manager_api.services.projects import ProjectService


def test_rejection_uses_the_same_project_lock_as_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    project_id = uuid.uuid4()
    proposal = SimpleNamespace(project_id=project_id, milestone_code="M01")
    session = SimpleNamespace(get=lambda _model, _identifier: proposal)
    service = ProjectService(session, "actor-1")  # type: ignore[arg-type]

    def require_project(identifier: uuid.UUID, manager: bool = False, lock: bool = False) -> Any:
        assert identifier == project_id
        assert manager is False
        assert lock is True
        raise RuntimeError("lock checked")

    monkeypatch.setattr(service, "_require_project", require_project)

    with pytest.raises(RuntimeError, match="lock checked"):
        service.reject_proposal(uuid.uuid4(), "reason")
