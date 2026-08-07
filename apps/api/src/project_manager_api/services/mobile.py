from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from project_manager_api.api.schemas import (
    InvitationAccept,
    IssueCreate,
    IssueDelete,
    IssueUpdate,
    MemberInvitationCreate,
    MilestoneUpdateCreate,
)
from project_manager_api.db.models import (
    AuditLog,
    BindingStatus,
    ChangeProposal,
    InAppMessage,
    Issue,
    MemberBinding,
    MobileSession,
    MobileUser,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectVersion,
    ProposalStatus,
    WechatSubscriptionGrant,
)
from project_manager_api.services.crypto import PhoneCipher
from project_manager_api.services.errors import (
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
)
from project_manager_api.services.llm import OpenAICompatibleClient
from project_manager_api.services.projects import ProjectService
from project_manager_api.services.wechat import exchange_wechat_code, exchange_wechat_phone
from project_manager_api.settings import AppSettings

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
MILESTONE_PATTERN = re.compile(r"M\d{1,3}", re.IGNORECASE)


def authenticate_mobile_user(session: Session, authorization: str) -> MobileUser:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ForbiddenError("valid mobile bearer token is required")
    mobile_session = session.scalar(
        select(MobileSession).where(MobileSession.token_hash == _hash_token(token))
    )
    if mobile_session is None or _expired(mobile_session.expires_at):
        raise ForbiddenError("mobile session is invalid or expired")
    user = session.get(MobileUser, mobile_session.user_id)
    if user is None:
        raise ForbiddenError("mobile user no longer exists")
    return user


class MobileService:
    def __init__(self, session: Session, settings: AppSettings, user: MobileUser | None = None):
        self.session = session
        self.settings = settings
        self.user = user

    def login(self, code: str, display_name: str) -> dict[str, Any]:
        openid = exchange_wechat_code(code, self.settings)
        user = self.session.scalar(select(MobileUser).where(MobileUser.openid == openid))
        if user is None:
            user = MobileUser(openid=openid, display_name=display_name)
            self.session.add(user)
            self.session.flush()
        else:
            user.display_name = display_name
        token = secrets.token_urlsafe(32)
        self.session.add(
            MobileSession(
                user_id=user.id,
                token_hash=_hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(days=self.settings.mobile_session_days),
            )
        )
        return {
            "access_token": token,
            "expires_in": self.settings.mobile_session_days * 86400,
            "user": _user_dict(user),
        }

    def create_invitation(
        self,
        project_id: uuid.UUID,
        actor_id: str,
        payload: MemberInvitationCreate,
    ) -> dict[str, Any]:
        project, snapshot = self._manager_project(project_id, actor_id)
        if not any(item["name"] == payload.member_name for item in snapshot.get("members", [])):
            raise NotFoundError("member is not present in the current project version")
        existing = self.session.scalar(
            select(MemberBinding).where(
                MemberBinding.project_id == project.id,
                MemberBinding.member_name == payload.member_name,
            )
        )
        if existing is not None and existing.status == BindingStatus.BOUND:
            raise ConflictError("member is already bound")
        token = secrets.token_urlsafe(32)
        if existing is None:
            binding = MemberBinding(
                project_id=project.id,
                member_name=payload.member_name,
                invitation_token_hash=_hash_token(token),
                expected_phone_hash=self._phone_hash(payload.expected_phone),
                expected_phone_masked=_mask_phone(payload.expected_phone),
                status=BindingStatus.INVITED,
                invitation_expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            self.session.add(binding)
        else:
            binding = existing
            binding.invitation_token_hash = _hash_token(token)
            binding.expected_phone_hash = self._phone_hash(payload.expected_phone)
            binding.expected_phone_masked = _mask_phone(payload.expected_phone)
            binding.status = BindingStatus.INVITED
            binding.invitation_expires_at = datetime.now(UTC) + timedelta(days=7)
        self.session.flush()
        self._audit(
            project.id,
            actor_id,
            "member.invited",
            "member_binding",
            str(binding.id),
        )
        return {**_binding_dict(binding), "invitation_token": token}

    def accept_invitation(self, payload: InvitationAccept) -> dict[str, Any]:
        user = self._user()
        binding = self.session.scalar(
            select(MemberBinding).where(
                MemberBinding.invitation_token_hash == _hash_token(payload.invitation_token)
            )
        )
        if binding is None or binding.status != BindingStatus.INVITED:
            raise NotFoundError("invitation is invalid")
        if _expired(binding.invitation_expires_at):
            raise ConflictError("invitation has expired")
        if payload.phone:
            if not self.settings.allow_development_wechat_login:
                raise ServiceError("direct phone input is allowed only in development")
            phone = payload.phone
        else:
            phone = exchange_wechat_phone(payload.phone_code or "", self.settings)
        other_binding = self.session.scalar(
            select(MemberBinding).where(
                MemberBinding.project_id == binding.project_id,
                MemberBinding.user_id == user.id,
                MemberBinding.id != binding.id,
                MemberBinding.status != BindingStatus.REVOKED,
            )
        )
        if other_binding is not None:
            raise ConflictError("user is already bound to another member in this project")
        phone_hash = self._phone_hash(phone)
        binding.user_id = user.id
        binding.actor_id = _actor_id(user)
        binding.provided_phone_hash = phone_hash
        binding.provided_phone_masked = _mask_phone(phone)
        user.phone_hash = phone_hash
        user.phone_masked = _mask_phone(phone)
        try:
            user.phone_ciphertext = PhoneCipher(self.settings.phone_encryption_key).encrypt(phone)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        user.phone_key_version = 1
        if binding.expected_phone_hash and binding.expected_phone_hash != phone_hash:
            binding.status = BindingStatus.PENDING_REVIEW
        else:
            self._activate_binding(binding, user)
        self.session.flush()
        return _binding_dict(binding)

    def grant_subscription(self, template_id: str) -> dict[str, Any]:
        user = self._user()
        configured = self.settings.wechat_subscription_template_id
        if not configured or template_id != configured:
            raise ConflictError("subscription template is not configured for this application")
        grant = self.session.scalar(
            select(WechatSubscriptionGrant).where(
                WechatSubscriptionGrant.user_id == user.id,
                WechatSubscriptionGrant.template_id == template_id,
            )
        )
        if grant is None:
            grant = WechatSubscriptionGrant(
                user_id=user.id, template_id=template_id, remaining_uses=1
            )
            self.session.add(grant)
        else:
            grant.remaining_uses += 1
        self.session.flush()
        return {"template_id": template_id, "remaining_uses": grant.remaining_uses}

    def approve_binding(self, binding_id: uuid.UUID, actor_id: str) -> dict[str, Any]:
        binding = self.session.get(MemberBinding, binding_id)
        if binding is None or binding.user_id is None:
            raise NotFoundError("member binding not found")
        self._manager_project(binding.project_id, actor_id)
        if binding.status != BindingStatus.PENDING_REVIEW:
            raise ConflictError("member binding is not awaiting review")
        user = self.session.get(MobileUser, binding.user_id)
        if user is None:
            raise NotFoundError("mobile user not found")
        self._activate_binding(binding, user)
        self._audit(
            binding.project_id,
            actor_id,
            "member.binding_approved",
            "member_binding",
            str(binding.id),
        )
        return _binding_dict(binding)

    def list_bindings(self, project_id: uuid.UUID, actor_id: str) -> list[dict[str, Any]]:
        self._manager_project(project_id, actor_id)
        query = (
            select(MemberBinding)
            .where(MemberBinding.project_id == project_id)
            .order_by(MemberBinding.created_at)
        )
        return [_binding_dict(binding) for binding in self.session.scalars(query)]

    def list_projects(self) -> list[dict[str, Any]]:
        actor_id = _actor_id(self._user())
        query = (
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(ProjectMembership.actor_id == actor_id)
            .order_by(Project.created_at.desc())
        )
        return [
            {
                "id": str(project.id),
                "code": project.code,
                "name": project.name,
                "status": project.status,
                "current_version_number": project.current_version_number or 0,
            }
            for project in self.session.scalars(query)
        ]

    def dashboard(self, project_id: uuid.UUID) -> dict[str, Any]:
        project, binding, snapshot = self._bound_project(project_id)
        active_name = snapshot.get("active_plan_name")
        plan: dict[str, Any] = next(
            (item for item in snapshot.get("plan_versions", []) if item["name"] == active_name),
            {"milestones": {}},
        )
        milestones = []
        for milestone in snapshot.get("milestones", []):
            milestones.append(
                {
                    **milestone,
                    "plan": plan["milestones"].get(milestone["name"]),
                    "can_update": binding.member_name
                    in milestone.get("assignments", {}).get("R", []),
                    "can_approve": binding.member_name
                    in milestone.get("assignments", {}).get("A", []),
                }
            )
        return {
            "project": {"id": str(project.id), "code": project.code, "name": project.name},
            "current_version_number": project.current_version_number or 0,
            "active_plan_name": active_name,
            "member_name": binding.member_name,
            "milestones": milestones,
        }

    def create_milestone_proposal(
        self,
        project_id: uuid.UUID,
        milestone_code: str,
        payload: MilestoneUpdateCreate,
    ) -> dict[str, Any]:
        project, binding, snapshot = self._bound_project(project_id)
        if project.current_version_number != payload.base_version_number:
            raise ConflictError("proposal base version is stale")
        milestone = _milestone(snapshot, milestone_code)
        if binding.member_name not in milestone.get("assignments", {}).get("R", []):
            raise ForbiddenError("only the responsible member can update this milestone")
        if payload.kind == "completed":
            if payload.actual_completion_date is None:
                raise ConflictError("completion date is required")
            before = milestone["actual_completion"]
            after = {
                "state": "scheduled",
                "start_date": payload.actual_completion_date.isoformat(),
                "end_date": payload.actual_completion_date.isoformat(),
            }
            target_path = f"milestones.{milestone_code}.actual_completion"
        else:
            if payload.start_date is None or payload.end_date is None:
                raise ConflictError("delay start and end dates are required")
            before = _active_window(snapshot, milestone["name"])
            after = {
                "state": "scheduled",
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat(),
            }
            target_path = f"active_plan.milestones.{milestone_code}"
        proposal = ChangeProposal(
            project_id=project.id,
            milestone_code=milestone_code,
            proposal_kind=payload.kind,
            target_path=target_path,
            base_version_number=payload.base_version_number,
            before_value=before,
            after_value=after,
            reason=payload.reason,
            status=ProposalStatus.PENDING,
            submitted_by_actor_id=_actor_id(self._user()),
        )
        self.session.add(proposal)
        self.session.flush()
        self._audit(
            project.id,
            _actor_id(self._user()),
            "change_proposal.created",
            "change_proposal",
            str(proposal.id),
        )
        return _proposal_dict(proposal)

    def create_issue(self, project_id: uuid.UUID, payload: IssueCreate) -> dict[str, Any]:
        self._bound_project(project_id)
        return ProjectService(self.session, _actor_id(self._user())).create_issue(
            project_id, payload
        )

    def list_messages(self) -> list[dict[str, Any]]:
        user = self._user()
        query = (
            select(InAppMessage)
            .where(InAppMessage.user_id == user.id)
            .order_by(InAppMessage.created_at.desc())
        )
        return [_message_dict(message) for message in self.session.scalars(query)]

    def list_approvable_proposals(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        _, binding, snapshot = self._bound_project(project_id)
        accountable_codes = {
            item["code"]
            for item in snapshot.get("milestones", [])
            if binding.member_name in item.get("assignments", {}).get("A", [])
        }
        query = (
            select(ChangeProposal)
            .where(
                ChangeProposal.project_id == project_id,
                ChangeProposal.status == ProposalStatus.PENDING,
                ChangeProposal.milestone_code.in_(accountable_codes),
            )
            .order_by(ChangeProposal.created_at.desc())
        )
        return [_proposal_dict(proposal) for proposal in self.session.scalars(query)]

    def update_issue(self, issue_id: uuid.UUID, payload: IssueUpdate) -> dict[str, Any]:
        issue = self.session.get(Issue, issue_id)
        if issue is None:
            raise NotFoundError("issue not found")
        _, binding, _ = self._bound_project(issue.project_id)
        if binding.member_name != issue.owner_name:
            raise ForbiddenError("only the issue owner can update this issue")
        if payload.owner_name is not None and payload.owner_name != issue.owner_name:
            raise ForbiddenError("the issue owner cannot reassign ownership")
        return ProjectService(self.session, _actor_id(self._user())).update_issue_as_member(
            issue, payload
        )

    def delete_issue(self, issue_id: uuid.UUID, payload: IssueDelete) -> dict[str, Any]:
        issue = self.session.get(Issue, issue_id)
        if issue is None:
            raise NotFoundError("issue not found")
        _, binding, _ = self._bound_project(issue.project_id)
        if binding.member_name != issue.owner_name:
            raise ForbiddenError("only the issue owner can delete this issue")
        return ProjectService(self.session, _actor_id(self._user())).delete_issue_as_member(
            issue, payload
        )

    def mark_message_read(self, message_id: uuid.UUID) -> dict[str, Any]:
        message = self.session.get(InAppMessage, message_id)
        if message is None or message.user_id != self._user().id:
            raise NotFoundError("message not found")
        message.is_read = True
        return _message_dict(message)

    def _phone_hash(self, phone: str | None) -> str | None:
        if phone is None:
            return None
        if not self.settings.phone_hmac_key:
            raise ServiceError("phone HMAC key is not configured")
        return hmac.new(
            self.settings.phone_hmac_key.encode(), phone.encode(), hashlib.sha256
        ).hexdigest()

    def _activate_binding(self, binding: MemberBinding, user: MobileUser) -> None:
        binding.status = BindingStatus.BOUND
        actor_id = _actor_id(user)
        binding.actor_id = actor_id
        project, snapshot = self._project_snapshot(binding.project_id)
        if not any(item.get("name") == binding.member_name for item in snapshot.get("members", [])):
            raise ConflictError("member is no longer present in the current project version")
        role = _member_role(snapshot, binding.member_name)
        membership = self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.actor_id == actor_id,
            )
        )
        if membership is None:
            self.session.add(ProjectMembership(project_id=project.id, actor_id=actor_id, role=role))
        else:
            membership.role = role
        self.session.add(
            InAppMessage(
                user_id=user.id,
                project_id=project.id,
                type="binding_approved",
                title="项目绑定成功",
                body=f"你已绑定项目 {project.code}，身份为 {binding.member_name}。",
            )
        )

    def _manager_project(
        self, project_id: uuid.UUID, actor_id: str
    ) -> tuple[Project, dict[str, Any]]:
        membership = self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.actor_id == actor_id,
                ProjectMembership.role == ProjectRole.MANAGER,
            )
        )
        if membership is None:
            raise ForbiddenError("project-manager role is required")
        return self._project_snapshot(project_id)

    def _bound_project(
        self, project_id: uuid.UUID
    ) -> tuple[Project, MemberBinding, dict[str, Any]]:
        user = self._user()
        binding = self.session.scalar(
            select(MemberBinding).where(
                MemberBinding.project_id == project_id,
                MemberBinding.user_id == user.id,
                MemberBinding.status == BindingStatus.BOUND,
            )
        )
        if binding is None:
            raise ForbiddenError("user is not bound to this project")
        project, snapshot = self._project_snapshot(project_id)
        return project, binding, snapshot

    def _project_snapshot(self, project_id: uuid.UUID) -> tuple[Project, dict[str, Any]]:
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("project not found")
        version = self.session.scalar(
            select(ProjectVersion).where(
                ProjectVersion.project_id == project.id,
                ProjectVersion.version_number == project.current_version_number,
            )
        )
        if version is None:
            raise ConflictError("project has no published version")
        return project, version.snapshot

    def _user(self) -> MobileUser:
        if self.user is None:
            raise ForbiddenError("mobile authentication is required")
        return self.user

    def _audit(
        self, project_id: uuid.UUID, actor_id: str, action: str, entity_type: str, entity_id: str
    ) -> None:
        self.session.add(
            AuditLog(
                project_id=project_id,
                actor_id=actor_id,
                source="mini_program",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )


def natural_language_prefill(text: str, settings: AppSettings) -> dict[str, Any]:
    if settings.llm_api_key:
        try:
            result = OpenAICompatibleClient(
                settings.llm_base_url,
                settings.llm_api_key,
                settings.llm_model,
                settings.llm_timeout_seconds,
                settings.llm_max_retries,
                settings.llm_structured_output_mode,
            ).generate_structured(text, _prefill_schema())
            return {
                **result,
                "requires_confirmation": True,
                "requires_manual_input": False,
                "source": "llm",
            }
        except ServiceError:
            pass
    milestone = MILESTONE_PATTERN.search(text)
    date_value = DATE_PATTERN.search(text)
    return {
        "milestone_code": milestone.group(0).upper() if milestone else None,
        "kind": "delay" if "延期" in text else None,
        "start_date": date_value.group(0) if date_value else None,
        "end_date": date_value.group(0) if date_value else None,
        "reason": text.split("原因", maxsplit=1)[-1].lstrip("是：:，, "),
        "requires_confirmation": True,
        "requires_manual_input": milestone is None or date_value is None,
        "source": "local_rule",
    }


def _prefill_schema() -> dict[str, Any]:
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object",
        "properties": {
            "milestone_code": nullable_string,
            "kind": {"anyOf": [{"enum": ["completed", "delay"]}, {"type": "null"}]},
            "start_date": nullable_string,
            "end_date": nullable_string,
            "reason": {"type": "string"},
        },
        "required": ["milestone_code", "kind", "start_date", "end_date", "reason"],
        "additionalProperties": False,
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


def _actor_id(user: MobileUser) -> str:
    return f"mobile:{user.id}"


def _member_role(snapshot: dict[str, Any], member_name: str) -> str:
    assignments = [item.get("assignments", {}) for item in snapshot.get("milestones", [])]
    if any(member_name in item.get("A", []) for item in assignments):
        return ProjectRole.ACCOUNTABLE
    if any(member_name in item.get("R", []) for item in assignments):
        return ProjectRole.RESPONSIBLE
    return ProjectRole.COLLABORATOR


def _milestone(snapshot: dict[str, Any], milestone_code: str) -> dict[str, Any]:
    milestone = next(
        (item for item in snapshot.get("milestones", []) if item["code"] == milestone_code),
        None,
    )
    if milestone is None:
        raise NotFoundError("milestone not found")
    return milestone


def _active_window(snapshot: dict[str, Any], milestone_name: str) -> dict[str, Any]:
    active_name = snapshot.get("active_plan_name")
    plan = next(
        (item for item in snapshot.get("plan_versions", []) if item["name"] == active_name),
        None,
    )
    if plan is None or milestone_name not in plan["milestones"]:
        raise NotFoundError("active milestone plan not found")
    return plan["milestones"][milestone_name]


def _user_dict(user: MobileUser) -> dict[str, Any]:
    return {"id": str(user.id), "display_name": user.display_name, "phone": user.phone_masked}


def _binding_dict(binding: MemberBinding) -> dict[str, Any]:
    return {
        "id": str(binding.id),
        "project_id": str(binding.project_id),
        "member_name": binding.member_name,
        "status": binding.status,
        "provided_phone": binding.provided_phone_masked,
        "expected_phone": binding.expected_phone_masked,
    }


def _mask_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    if len(phone) <= 7:
        return f"{phone[:2]}***{phone[-2:]}"
    return f"{phone[:3]}****{phone[-4:]}"


def _proposal_dict(proposal: ChangeProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "project_id": str(proposal.project_id),
        "milestone_code": proposal.milestone_code,
        "kind": proposal.proposal_kind,
        "base_version_number": proposal.base_version_number,
        "before_value": proposal.before_value,
        "after_value": proposal.after_value,
        "reason": proposal.reason,
        "status": proposal.status,
    }


def _message_dict(message: InAppMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "project_id": str(message.project_id) if message.project_id else None,
        "type": message.type,
        "title": message.title,
        "body": message.body,
        "is_read": message.is_read,
        "created_at": message.created_at.isoformat(),
    }
