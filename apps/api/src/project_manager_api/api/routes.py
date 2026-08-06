from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from project_manager_api.api.schemas import (
    InvitationAccept,
    IssueCreate,
    IssueUpdate,
    MemberInvitationCreate,
    MilestoneUpdateCreate,
    NaturalLanguagePrefillRequest,
    ProgressProposalCreate,
    ProjectCreate,
    PublishRequest,
    RejectRequest,
    WechatLoginRequest,
)
from project_manager_api.db.models import IdempotencyRecord, MobileUser
from project_manager_api.imports.errors import ImportErrorBase
from project_manager_api.services.errors import ConflictError, ServiceError
from project_manager_api.services.mobile import (
    MobileService,
    authenticate_mobile_user,
    natural_language_prefill,
)
from project_manager_api.services.projects import ProjectService

router = APIRouter(prefix="/api/v1")


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_actor_id(x_actor_id: str = Header(min_length=1)) -> str:
    return x_actor_id


def get_idempotency_key(x_idempotency_key: str = Header(min_length=1)) -> str:
    return x_idempotency_key


SessionDependency = Annotated[Session, Depends(get_session)]
ActorDependency = Annotated[str, Depends(get_actor_id)]
IdempotencyDependency = Annotated[str, Depends(get_idempotency_key)]
UploadDependency = Annotated[UploadFile, File()]


def get_mobile_user(
    session: SessionDependency,
    authorization: str = Header(min_length=1),
) -> MobileUser:
    return authenticate_mobile_user(session, authorization)


MobileUserDependency = Annotated[MobileUser, Depends(get_mobile_user)]


@router.get("/projects")
def list_projects(
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_projects()


@router.post("/mobile/auth/wechat")
def mobile_wechat_login(
    payload: WechatLoginRequest,
    request: Request,
    session: SessionDependency,
) -> dict[str, Any]:
    return _execute_transaction(
        session,
        lambda: MobileService(session, request.app.state.settings).login(
            payload.code, payload.display_name
        ),
    )


@router.post("/projects/{project_id}/member-invitations", status_code=201)
def create_member_invitation(
    project_id: uuid.UUID,
    payload: MemberInvitationCreate,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        lambda: MobileService(session, request.app.state.settings).create_invitation(
            project_id, actor_id, payload
        ),
    )


@router.post("/mobile/invitations/accept")
def accept_member_invitation(
    payload: InvitationAccept,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> dict[str, Any]:
    return _execute_transaction(
        session,
        lambda: MobileService(session, request.app.state.settings, user).accept_invitation(payload),
    )


@router.post("/member-bindings/{binding_id}/approve")
def approve_member_binding(
    binding_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: MobileService(session, request.app.state.settings).approve_binding(
            binding_id, actor_id
        ),
    )


@router.get("/projects/{project_id}/member-bindings")
def list_member_bindings(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return MobileService(session, request.app.state.settings).list_bindings(project_id, actor_id)


@router.get("/mobile/projects")
def list_mobile_projects(
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(session, request.app.state.settings, user).list_projects()


@router.get("/mobile/projects/{project_id}/dashboard")
def get_mobile_dashboard(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> dict[str, Any]:
    return MobileService(session, request.app.state.settings, user).dashboard(project_id)


@router.post("/mobile/projects/{project_id}/milestones/{milestone_code}/proposals", status_code=201)
def create_mobile_milestone_proposal(
    project_id: uuid.UUID,
    milestone_code: str,
    payload: MilestoneUpdateCreate,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    actor_id = f"mobile:{user.id}"
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        lambda: MobileService(session, request.app.state.settings, user).create_milestone_proposal(
            project_id, milestone_code, payload
        ),
    )


@router.post("/mobile/change-proposals/{proposal_id}/approve")
def approve_mobile_proposal(
    proposal_id: uuid.UUID,
    payload: PublishRequest,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    actor_id = f"mobile:{user.id}"
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: ProjectService(session, actor_id).approve_proposal(
            proposal_id, payload.expected_project_version
        ),
    )


@router.post("/mobile/projects/{project_id}/issues", status_code=201)
def create_mobile_issue(
    project_id: uuid.UUID,
    payload: IssueCreate,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    actor_id = f"mobile:{user.id}"
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        lambda: MobileService(session, request.app.state.settings, user).create_issue(
            project_id, payload
        ),
    )


@router.get("/mobile/projects/{project_id}/issues")
def list_mobile_issues(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    service = MobileService(session, request.app.state.settings, user)
    service.dashboard(project_id)
    return ProjectService(session, f"mobile:{user.id}").list_issues(project_id)


@router.get("/mobile/messages")
def list_mobile_messages(
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(session, request.app.state.settings, user).list_messages()


@router.post("/mobile/natural-language/prefill")
def prefill_mobile_update(
    payload: NaturalLanguagePrefillRequest,
    request: Request,
    _user: MobileUserDependency,
) -> dict[str, Any]:
    return natural_language_prefill(payload.text, request.app.state.settings)


@router.post("/projects", status_code=201)
def create_project(
    payload: ProjectCreate,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        lambda: ProjectService(session, actor_id).create_project(payload.code, payload.name),
    )


@router.post("/projects/{project_id}/imports", status_code=201)
async def create_import(
    project_id: uuid.UUID,
    request: Request,
    file: UploadDependency,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    cached = _cached_response(session, actor_id, request_key, request.method, request.url.path)
    if cached is not None:
        return cached
    content = await file.read(request.app.state.settings.max_import_size_bytes + 1)
    if len(content) > request.app.state.settings.max_import_size_bytes:
        raise ServiceError("uploaded workbook exceeds configured size limit")
    object_key, stored_path = request.app.state.import_storage.put(
        file.filename or "upload.xlsx", content
    )
    try:
        parsed = request.app.state.parser_registry.parse(stored_path)
    except ImportErrorBase as exc:
        request.app.state.import_storage.delete(object_key)
        request.app.state.import_storage.release(stored_path)
        raise ServiceError(str(exc)) from exc
    try:
        return _execute_idempotent(
            session,
            actor_id,
            request_key,
            request.method,
            request.url.path,
            201,
            lambda: ProjectService(session, actor_id).create_import(
                project_id,
                file.filename or "upload.xlsx",
                object_key,
                parsed,
            ),
        )
    except Exception:
        request.app.state.import_storage.delete(object_key)
        raise
    finally:
        request.app.state.import_storage.release(stored_path)


@router.get("/projects/{project_id}/imports")
def list_imports(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_imports(project_id)


@router.get("/imports/{import_id}")
def get_import(
    import_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return ProjectService(session, actor_id).get_import(import_id)


@router.post("/imports/{import_id}/publish")
def publish_import(
    import_id: uuid.UUID,
    payload: PublishRequest,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: ProjectService(session, actor_id).publish_import(
            import_id, payload.expected_project_version
        ),
    )


@router.post("/imports/{import_id}/cancel")
def cancel_import(
    import_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: ProjectService(session, actor_id).cancel_import(import_id),
    )


@router.get("/projects/{project_id}/versions")
def list_versions(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_versions(project_id)


@router.get("/projects/{project_id}/dashboard")
def get_dashboard(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return ProjectService(session, actor_id).dashboard(project_id)


@router.post(
    "/projects/{project_id}/milestones/{milestone_code}/progress-proposals", status_code=201
)
def create_progress_proposal(
    project_id: uuid.UUID,
    milestone_code: str,
    payload: ProgressProposalCreate,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        lambda: ProjectService(session, actor_id).create_progress_proposal(
            project_id, milestone_code, payload
        ),
    )


@router.post("/change-proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: uuid.UUID,
    payload: PublishRequest,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: ProjectService(session, actor_id).approve_proposal(
            proposal_id, payload.expected_project_version
        ),
    )


@router.get("/projects/{project_id}/change-proposals")
def list_change_proposals(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_proposals(project_id)


@router.post("/change-proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: uuid.UUID,
    payload: RejectRequest,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: ProjectService(session, actor_id).reject_proposal(proposal_id, payload.reason),
    )


@router.post("/projects/{project_id}/issues", status_code=201)
def create_issue(
    project_id: uuid.UUID,
    payload: IssueCreate,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        lambda: ProjectService(session, actor_id).create_issue(project_id, payload),
    )


@router.patch("/issues/{issue_id}")
def update_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    return _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        200,
        lambda: ProjectService(session, actor_id).update_issue(issue_id, payload),
    )


@router.get("/projects/{project_id}/issues")
def list_issues(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_issues(project_id)


@router.get("/projects/{project_id}/audit-logs")
def list_audit_logs(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_audit_logs(project_id)


def _cached_response(
    session: Session,
    actor_id: str,
    request_key: str,
    method: str,
    path: str,
) -> JSONResponse | None:
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.request_key == request_key,
        )
    )
    if record is None:
        return None
    if record.method != method or record.path != path:
        raise ConflictError("idempotency key was already used for another request")
    return JSONResponse(status_code=record.response_status, content=record.response_body)


def _execute_idempotent(
    session: Session,
    actor_id: str,
    request_key: str,
    method: str,
    path: str,
    status_code: int,
    operation: Callable[[], dict[str, Any]],
) -> JSONResponse:
    cached = _cached_response(session, actor_id, request_key, method, path)
    if cached is not None:
        return cached
    try:
        body = jsonable_encoder(operation())
        session.add(
            IdempotencyRecord(
                actor_id=actor_id,
                request_key=request_key,
                method=method,
                path=path,
                response_status=status_code,
                response_body=body,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return JSONResponse(status_code=status_code, content=body)


def _execute_transaction(
    session: Session,
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        body = operation()
        session.commit()
    except Exception:
        session.rollback()
        raise
    return body
