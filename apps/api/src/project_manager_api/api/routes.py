from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_manager_api.api.schemas import (
    InvitationAccept,
    IssueCreate,
    IssueDelete,
    IssueUpdate,
    MemberInvitationCreate,
    MilestoneUpdateCreate,
    NaturalLanguagePrefillRequest,
    NotificationScanRequest,
    ProgressProposalCreate,
    ProjectChangeSetCreate,
    ProjectCreate,
    ProjectUpdate,
    PublishRequest,
    RejectRequest,
    SubscriptionGrantCreate,
    WechatLoginRequest,
)
from project_manager_api.db.models import IdempotencyRecord, MobileUser, NotificationDelivery
from project_manager_api.imports.errors import ImportErrorBase
from project_manager_api.services.errors import (
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PersistedConflictError,
    ServiceError,
    UnauthorizedError,
)
from project_manager_api.services.mobile import (
    MobileService,
    authenticate_mobile_user,
    natural_language_prefill,
)
from project_manager_api.services.notification_adapters import (
    TencentSmsSender,
    WechatSubscriptionSender,
)
from project_manager_api.services.notifications import NotificationService
from project_manager_api.services.operations import build_operational_status, current_business_date
from project_manager_api.services.projects import ProjectService
from project_manager_api.services.wechat import generate_invitation_entries

router = APIRouter(prefix="/api/v1")


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_admin_actor(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    configured_token = request.app.state.settings.admin_api_token
    if not configured_token:
        raise ConfigurationError("administrator authentication is not configured")
    if not authorization:
        raise UnauthorizedError("administrator bearer token is required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("administrator bearer token is required")
    if not hmac.compare_digest(token, configured_token):
        raise ForbiddenError("invalid administrator bearer token")
    return str(request.app.state.settings.admin_actor_id)


def get_idempotency_key(x_idempotency_key: str = Header(min_length=1, max_length=128)) -> str:
    return x_idempotency_key


SessionDependency = Annotated[Session, Depends(get_session)]
ActorDependency = Annotated[str, Depends(get_admin_actor)]
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
    response = _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        201,
        _request_hash(payload),
        lambda: MobileService(session, request.app.state.settings).create_invitation(
            project_id, actor_id, payload
        ),
    )
    body: dict[str, Any] = json.loads(bytes(response.body))
    entries = generate_invitation_entries(body["invitation_token"], request.app.state.settings)
    return JSONResponse(status_code=response.status_code, content={**body, **entries})


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


@router.post("/mobile/subscription-grants")
def create_subscription_grant(
    payload: SubscriptionGrantCreate,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> dict[str, Any]:
    return _execute_transaction(
        session,
        lambda: MobileService(session, request.app.state.settings, user).grant_subscription(
            payload.template_id
        ),
    )


@router.post("/notifications/scans/{scan_kind}")
def run_notification_scan(
    scan_kind: str,
    payload: NotificationScanRequest,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, int]:
    if scan_kind not in {"daily", "weekly"}:
        raise NotFoundError("unsupported notification scan")
    service = NotificationService(
        session,
        request.app.state.settings,
        wechat=WechatSubscriptionSender(request.app.state.settings),
        sms=TencentSmsSender(request.app.state.settings),
    )
    operation = service.scan_daily if scan_kind == "daily" else service.scan_weekly
    business_date = payload.business_date or current_business_date(request.app.state.settings)
    result = operation(business_date)
    return {"created": result.created, "skipped": result.skipped}


@router.get("/notifications")
def list_notification_deliveries(
    session: SessionDependency,
    actor_id: ActorDependency,
    project_id: uuid.UUID | None = None,
    channel: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    query = select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()).limit(500)
    if project_id is not None:
        query = query.where(NotificationDelivery.project_id == project_id)
    if channel is not None:
        query = query.where(NotificationDelivery.channel == channel)
    if status is not None:
        query = query.where(NotificationDelivery.status == status)
    return [
        {
            "id": str(item.id),
            "project_id": str(item.project_id) if item.project_id else None,
            "user_id": str(item.user_id) if item.user_id else None,
            "event_type": item.event_type,
            "object_type": item.object_type,
            "object_id": item.object_id,
            "channel": item.channel,
            "business_date": item.business_date.isoformat(),
            "status": item.status,
            "attempts": item.attempts,
            "error_message": item.error_message,
            "created_at": item.created_at.isoformat(),
        }
        for item in session.scalars(query)
    ]


@router.get("/operations/status")
def get_operational_status(
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return build_operational_status(session, request.app.state.settings)


@router.post("/notifications/{delivery_id}/retry")
def retry_notification_delivery(
    delivery_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return NotificationService(
        session,
        request.app.state.settings,
        wechat=WechatSubscriptionSender(request.app.state.settings),
        sms=TencentSmsSender(request.app.state.settings),
    ).retry_failed(delivery_id)


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
        _request_hash(None),
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


@router.get("/mobile/my-tasks")
def list_mobile_my_tasks(
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(session, request.app.state.settings, user).list_my_tasks()


@router.get("/mobile/projects/{project_id}/dashboard")
def get_mobile_dashboard(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> dict[str, Any]:
    return MobileService(session, request.app.state.settings, user).dashboard(project_id)


@router.get("/mobile/projects/{project_id}/review")
def get_mobile_project_review(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> dict[str, Any]:
    return MobileService(session, request.app.state.settings, user).project_review(project_id)


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
        _request_hash(payload),
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).approve_proposal(
            proposal_id, payload.expected_project_version
        ),
    )


@router.post("/mobile/change-proposals/{proposal_id}/reject")
def reject_mobile_proposal(
    proposal_id: uuid.UUID,
    payload: RejectRequest,
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).reject_proposal(proposal_id, payload.reason),
    )


@router.get("/mobile/projects/{project_id}/change-proposals")
def list_mobile_approvable_proposals(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(session, request.app.state.settings, user).list_approvable_proposals(
        project_id
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
        _request_hash(payload),
        lambda: MobileService(session, request.app.state.settings, user).create_issue(
            project_id, payload
        ),
    )


@router.post("/mobile/projects/{project_id}/issue-create-proposals", status_code=201)
def create_mobile_issue_create_proposal(
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
        _request_hash(payload),
        lambda: MobileService(session, request.app.state.settings, user).create_issue(
            project_id, payload
        ),
    )


@router.get("/mobile/projects/{project_id}/issue-create-proposals")
def list_mobile_issue_create_proposals(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(
        session, request.app.state.settings, user
    ).list_issue_create_proposals(project_id)


@router.post("/mobile/issue-create-proposals/{proposal_id}/approve")
def approve_mobile_issue_create_proposal(
    proposal_id: uuid.UUID,
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
        _request_hash({}),
        lambda: MobileService(
            session, request.app.state.settings, user
        ).approve_issue_create_proposal(proposal_id),
    )


@router.post("/mobile/issue-create-proposals/{proposal_id}/reject")
def reject_mobile_issue_create_proposal(
    proposal_id: uuid.UUID,
    payload: RejectRequest,
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
        _request_hash(payload),
        lambda: MobileService(
            session, request.app.state.settings, user
        ).reject_issue_create_proposal(proposal_id, payload.reason),
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
    return ProjectService(
        session,
        f"mobile:{user.id}",
        current_business_date(request.app.state.settings),
        request.app.state.settings.mobile_upcoming_days,
    ).list_issues(project_id)


@router.patch("/mobile/issues/{issue_id}")
def update_mobile_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
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
        _request_hash(payload),
        lambda: MobileService(session, request.app.state.settings, user).update_issue(
            issue_id, payload
        ),
    )


@router.delete("/mobile/issues/{issue_id}", status_code=201)
def delete_mobile_issue(
    issue_id: uuid.UUID,
    payload: IssueDelete,
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
        _request_hash(payload),
        lambda: MobileService(session, request.app.state.settings, user).delete_issue(
            issue_id, payload
        ),
    )


@router.get("/mobile/projects/{project_id}/issue-delete-proposals")
def list_mobile_issue_delete_proposals(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(
        session, request.app.state.settings, user
    ).list_issue_delete_proposals(project_id)


@router.post("/mobile/issue-delete-proposals/{proposal_id}/approve")
def approve_mobile_issue_delete_proposal(
    proposal_id: uuid.UUID,
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
        _request_hash({}),
        lambda: MobileService(
            session, request.app.state.settings, user
        ).approve_issue_delete_proposal(proposal_id),
    )


@router.post("/mobile/issue-delete-proposals/{proposal_id}/reject")
def reject_mobile_issue_delete_proposal(
    proposal_id: uuid.UUID,
    payload: RejectRequest,
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
        _request_hash(payload),
        lambda: MobileService(
            session, request.app.state.settings, user
        ).reject_issue_delete_proposal(proposal_id, payload.reason),
    )


@router.get("/mobile/messages")
def list_mobile_messages(
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> list[dict[str, Any]]:
    return MobileService(session, request.app.state.settings, user).list_messages()


@router.patch("/mobile/messages/{message_id}/read")
def mark_mobile_message_read(
    message_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    user: MobileUserDependency,
) -> dict[str, Any]:
    return _execute_transaction(
        session,
        lambda: MobileService(session, request.app.state.settings, user).mark_message_read(
            message_id
        ),
    )


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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).create_project(payload.code, payload.name),
    )


@router.patch("/projects/{project_id}")
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).update_empty_project(
            project_id, payload.code, payload.name
        ),
    )


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> Response:
    _execute_idempotent(
        session,
        actor_id,
        request_key,
        request.method,
        request.url.path,
        204,
        _request_hash({}),
        lambda: ProjectService(session, actor_id).delete_empty_project(project_id),
    )
    return Response(status_code=204)


@router.post("/imports", status_code=201)
async def create_project_from_import(
    request: Request,
    file: UploadDependency,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    content = await file.read(request.app.state.settings.max_import_size_bytes + 1)
    if len(content) > request.app.state.settings.max_import_size_bytes:
        raise ServiceError("uploaded workbook exceeds configured size limit")
    filename = file.filename or "upload.xlsx"
    if Path(filename).suffix.lower() not in request.app.state.settings.allowed_import_extensions:
        raise ServiceError("uploaded workbook extension is not allowed")
    request_hash = _request_hash(
        {"filename": filename, "sha256": hashlib.sha256(content).hexdigest()}
    )
    cached = _cached_response(
        session, actor_id, request_key, request.method, request.url.path, request_hash
    )
    if cached is not None:
        return cached
    object_key, stored_path = request.app.state.import_storage.put(filename, content)
    try:
        parsed = await asyncio.to_thread(
            request.app.state.parser_registry.parse_isolated,
            stored_path,
            timeout_seconds=request.app.state.settings.import_timeout_seconds,
            max_uncompressed_size_bytes=(
                request.app.state.settings.max_import_uncompressed_size_bytes
            ),
            max_archive_entries=request.app.state.settings.max_import_archive_entries,
        )
        return _execute_idempotent(
            session,
            actor_id,
            request_key,
            request.method,
            request.url.path,
            201,
            request_hash,
            lambda: ProjectService(session, actor_id).create_project_from_import(
                filename, object_key, parsed
            ),
            on_concurrent_replay=lambda: request.app.state.import_storage.delete(object_key),
        )
    except ImportErrorBase as exc:
        request.app.state.import_storage.delete(object_key)
        raise ServiceError(str(exc)) from exc
    except Exception:
        request.app.state.import_storage.delete(object_key)
        raise
    finally:
        request.app.state.import_storage.release(stored_path)


@router.post("/projects/{project_id}/imports", status_code=201)
async def create_import(
    project_id: uuid.UUID,
    request: Request,
    file: UploadDependency,
    session: SessionDependency,
    actor_id: ActorDependency,
    request_key: IdempotencyDependency,
) -> JSONResponse:
    content = await file.read(request.app.state.settings.max_import_size_bytes + 1)
    if len(content) > request.app.state.settings.max_import_size_bytes:
        raise ServiceError("uploaded workbook exceeds configured size limit")
    filename = file.filename or "upload.xlsx"
    if Path(filename).suffix.lower() not in request.app.state.settings.allowed_import_extensions:
        raise ServiceError("uploaded workbook extension is not allowed")
    request_hash = _request_hash(
        {"filename": filename, "sha256": hashlib.sha256(content).hexdigest()}
    )
    cached = _cached_response(
        session, actor_id, request_key, request.method, request.url.path, request_hash
    )
    if cached is not None:
        return cached
    object_key, stored_path = request.app.state.import_storage.put(
        filename, content
    )
    try:
        parsed = await asyncio.to_thread(
            request.app.state.parser_registry.parse_isolated,
            stored_path,
            timeout_seconds=request.app.state.settings.import_timeout_seconds,
            max_uncompressed_size_bytes=(
                request.app.state.settings.max_import_uncompressed_size_bytes
            ),
            max_archive_entries=request.app.state.settings.max_import_archive_entries,
        )
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
            request_hash,
            lambda: ProjectService(session, actor_id).create_import(
                project_id,
                filename,
                object_key,
                parsed,
            ),
            on_concurrent_replay=lambda: request.app.state.import_storage.delete(
                object_key
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
        _request_hash(payload),
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
        _request_hash(None),
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
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return ProjectService(
        session,
        actor_id,
        current_business_date(request.app.state.settings),
        request.app.state.settings.mobile_upcoming_days,
    ).dashboard(project_id)


@router.get("/projects/{project_id}/review")
def get_project_review(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return ProjectService(session, actor_id).review(project_id)


@router.get("/projects/{project_id}/editable-data")
def get_project_editable_data(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return ProjectService(session, actor_id).editable_data(project_id)


@router.post("/projects/{project_id}/change-sets", status_code=201)
def create_project_change_set(
    project_id: uuid.UUID,
    payload: ProjectChangeSetCreate,
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).create_change_set(project_id, payload),
    )


@router.get("/projects/{project_id}/change-sets")
def list_project_change_sets(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_change_sets(project_id)


@router.get("/change-sets/{change_set_id}")
def get_project_change_set(
    change_set_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> dict[str, Any]:
    return ProjectService(session, actor_id).get_change_set(change_set_id)


@router.post("/change-sets/{change_set_id}/publish")
def publish_project_change_set(
    change_set_id: uuid.UUID,
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).publish_change_set(
            change_set_id, payload.expected_project_version
        ),
    )


@router.post("/change-sets/{change_set_id}/cancel")
def cancel_project_change_set(
    change_set_id: uuid.UUID,
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
        _request_hash(None),
        lambda: ProjectService(session, actor_id).cancel_change_set(change_set_id),
    )


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
        _request_hash(payload),
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
        _request_hash(payload),
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
        _request_hash(payload),
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
        _request_hash(payload),
        lambda: ProjectService(
            session,
            actor_id,
            current_business_date(request.app.state.settings),
            request.app.state.settings.mobile_upcoming_days,
        ).create_issue_proposal(project_id, payload),
    )


@router.get("/projects/{project_id}/issue-create-proposals")
def list_issue_create_proposals(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_issue_create_proposals(project_id)


@router.post("/issue-create-proposals/{proposal_id}/approve")
def approve_issue_create_proposal(
    proposal_id: uuid.UUID,
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
        _request_hash({}),
        lambda: ProjectService(session, actor_id).approve_issue_create_proposal(proposal_id),
    )


@router.post("/issue-create-proposals/{proposal_id}/reject")
def reject_issue_create_proposal(
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).reject_issue_create_proposal(
            proposal_id, payload.reason
        ),
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
        _request_hash(payload),
        lambda: ProjectService(
            session,
            actor_id,
            current_business_date(request.app.state.settings),
            request.app.state.settings.mobile_upcoming_days,
        ).update_issue(issue_id, payload),
    )


@router.get("/projects/{project_id}/issue-delete-proposals")
def list_issue_delete_proposals(
    project_id: uuid.UUID,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(session, actor_id).list_issue_delete_proposals(project_id)


@router.post("/issue-delete-proposals/{proposal_id}/approve")
def approve_issue_delete_proposal(
    proposal_id: uuid.UUID,
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
        _request_hash({}),
        lambda: ProjectService(session, actor_id).approve_issue_delete_proposal(proposal_id),
    )


@router.post("/issue-delete-proposals/{proposal_id}/reject")
def reject_issue_delete_proposal(
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
        _request_hash(payload),
        lambda: ProjectService(session, actor_id).reject_issue_delete_proposal(
            proposal_id, payload.reason
        ),
    )


@router.delete("/issues/{issue_id}", status_code=201)
def delete_issue(
    issue_id: uuid.UUID,
    payload: IssueDelete,
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
        _request_hash(payload),
        lambda: ProjectService(
            session,
            actor_id,
            current_business_date(request.app.state.settings),
            request.app.state.settings.mobile_upcoming_days,
        ).create_issue_delete_proposal(issue_id, payload),
    )


@router.get("/projects/{project_id}/issues")
def list_issues(
    project_id: uuid.UUID,
    request: Request,
    session: SessionDependency,
    actor_id: ActorDependency,
) -> list[dict[str, Any]]:
    return ProjectService(
        session,
        actor_id,
        current_business_date(request.app.state.settings),
        request.app.state.settings.mobile_upcoming_days,
    ).list_issues(project_id)


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
    request_hash: str,
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
    if record.request_hash is not None and record.request_hash != request_hash:
        raise ConflictError("idempotency key was already used with another request")
    return JSONResponse(status_code=record.response_status, content=record.response_body)


def _execute_idempotent(
    session: Session,
    actor_id: str,
    request_key: str,
    method: str,
    path: str,
    status_code: int,
    request_hash: str,
    operation: Callable[[], dict[str, Any]],
    on_concurrent_replay: Callable[[], None] | None = None,
) -> JSONResponse:
    cached = _cached_response(session, actor_id, request_key, method, path, request_hash)
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
                request_hash=request_hash,
                response_status=status_code,
                response_body=body,
            )
        )
        session.commit()
    except PersistedConflictError:
        session.commit()
        raise
    except IntegrityError as exc:
        session.rollback()
        cached = _cached_response(session, actor_id, request_key, method, path, request_hash)
        if cached is not None:
            if on_concurrent_replay is not None:
                on_concurrent_replay()
            return cached
        raise exc
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


def _request_hash(payload: Any) -> str:
    encoded = json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
