export interface Project {
  id: string;
  code: string;
  name: string;
  status: string;
  current_version_number: number;
}

export interface Dashboard {
  project: Project;
  current_version_number: number;
  active_plan_name: string | null;
  milestones: Record<string, PlanWindow>;
  counts: {
    members: number;
    milestones: number;
    product_specs: number;
    issues_open: number;
  };
}

export interface PlanWindow {
  state: "scheduled" | "tbd" | "not_applicable";
  start_date: string | null;
  end_date: string | null;
}

export interface DiffEntry {
  path: string;
  operation: "added" | "removed" | "changed";
  before: unknown;
  after: unknown;
}

export interface ImportRecord {
  id: string;
  filename: string;
  status: string;
  base_version_number: number;
  diff: DiffEntry[];
  diff_count: number;
  report: {
    counts: {
      product_specs: number;
      members: number;
      milestones: number;
      plan_versions: number;
    };
    warnings: string[];
  };
}

export interface ProjectVersion {
  id: string;
  version_number: number;
  template_id: string;
  template_version: string;
  document_version: string;
  created_at: string;
}

export interface Issue {
  id: string;
  description: string;
  impact: string;
  owner_name: string;
  severity: string;
  due_date: string;
  status: string;
  revision: number;
}

export interface AuditLog {
  id: string;
  actor_id: string;
  action: string;
  entity_type: string;
  reason: string | null;
  created_at: string;
}

export interface MemberBinding {
  id: string;
  member_name: string;
  status: "invited" | "pending_review" | "bound" | "revoked";
  expected_phone: string | null;
  provided_phone: string | null;
}

export interface ChangeProposal {
  id: string;
  milestone_code: string;
  kind: "completed" | "delay" | "schedule";
  reason: string;
  status: "pending" | "approved" | "rejected";
  base_version_number: number;
}

export interface NotificationDelivery {
  id: string;
  project_id: string | null;
  user_id: string | null;
  event_type: string;
  object_type: string;
  object_id: string;
  channel: "in_app" | "wechat" | "sms";
  business_date: string;
  status: "pending" | "sent" | "failed" | "failed_fallback_sent" | "skipped";
  attempts: number;
  error_message: string | null;
  created_at: string;
}
