export interface Project {
  id: string;
  code: string;
  name: string;
  status: string;
  current_version_number: number;
}

export interface RetrospectiveOptions {
  baselines: { version_number: number; plan_name: string }[];
  reason_categories: string[];
}

export interface RetrospectiveReason {
  milestone_code: string;
  category: string;
  confirmed_reason: string;
  evidence: string;
  fact_confirmed_by: string;
  confirmation_source: string;
  status: "pending" | "confirmed";
  recorded_by?: string;
}

export interface RetrospectiveImprovement {
  milestone_code: string | null;
  source_event_ids: string[];
  scenario: string;
  action: string;
  proposed_owner: string;
  acceptance: string;
  recorded_by?: string;
}

export interface RetrospectiveReview {
  baseline_confirmed: boolean;
  baseline_note: string;
  reason_reviews: RetrospectiveReason[];
  improvements: RetrospectiveImprovement[];
}

export interface RetrospectiveReport {
  id: string;
  project_id: string;
  report_number: number;
  revision: number;
  status: "draft" | "confirmed";
  created_at: string;
  confirmed_at: string | null;
  created_by: string;
  confirmed_by: string | null;
  supersedes_report_id: string | null;
  facts: {
    cutoff_at: string;
    date_basis: "calendar_days";
    project_version_number: number;
    baseline: { version_number: number; plan_name: string };
    warnings: string[];
    milestones: {
      code: string; name: string;
      original_plan: PlanWindow | null; latest_plan: PlanWindow | null; variance_plan: PlanWindow | null; actual_completion: PlanWindow | null;
      original_variance_days: number | null; adjusted_variance_days: number | null;
      effective_adjustment_count: number; imported_plan_rows_count: number;
      status: "completed" | "incomplete" | "not_applicable" | "removed";
      scope_change: "added" | "removed" | null;
      warnings: string[]; assignments: Record<"R" | "A" | "C" | "I", string[]>;
    }[];
    timeline: {
      id: string; source: string; kind: string; milestone_code: string | null; effective: boolean;
      occurred_at: string | null; recorded_at: string; status: string; before: unknown; after: unknown;
      reason: string | null; submitted_by: string | null; resolved_by: string | null; evidence_refs: string[];
    }[];
  };
  review: RetrospectiveReview;
}

export interface Dashboard {
  project: Project;
  current_version_number: number;
  active_plan_name: string | null;
  business_date: string;
  milestones: Record<string, PlanWindow>;
  tasks: ProjectBoardTask[];
  issues: Issue[];
  counts: {
    members: number;
    milestones: number;
    product_specs: number;
    issues_open: number;
  };
}

export interface ProjectBoardTask {
  code: string;
  name: string;
  output: string | null;
  plan: PlanWindow | null;
  assignments: Record<"R" | "A" | "C" | "I", string[]>;
  risk: "todo" | "upcoming" | "overdue" | "completed";
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
  project_id: string;
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

export interface ProjectImportCreateResult {
  project: Project;
  import: ImportRecord;
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
  accountable_names: string[];
  consulted_names: string[];
  informed_names: string[];
  risk: "todo" | "upcoming" | "overdue" | "completed";
  severity: string;
  due_date: string;
  status: string;
  revision: number;
}

export interface IssueCreateProposal {
  id: string;
  project_id: string;
  payload: Omit<Issue, "id" | "risk" | "status" | "revision">;
  status: "pending" | "approved" | "rejected";
  submitted_by_actor_id: string;
  resolution_reason: string | null;
  issue_id: string | null;
  created_at: string;
}

export interface IssueDeleteProposal {
  id: string;
  project_id: string;
  issue_id: string;
  issue_description: string;
  expected_revision: number;
  reason: string;
  status: "pending" | "approved" | "rejected";
  submitted_by_actor_id: string;
  resolution_reason: string | null;
  created_at: string;
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

export interface MemberInvitation extends MemberBinding {
  invitation_token: string;
  invitation_expires_at: string;
  mini_program_path: string;
  url_link: string | null;
  mini_program_code_data_url: string | null;
  entry_generation_error: string | null;
}

export interface ChangeProposal {
  id: string;
  milestone_code: string;
  kind: "completed" | "delay" | "schedule";
  reason: string;
  status: "pending" | "approved" | "rejected";
  base_version_number: number;
  created_at: string;
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

export interface OperationalStatus {
  status: "ok" | "alert";
  notification_failures: number;
  stale_pending: number;
  unbound_recipients: number;
  configuration_issues: string[];
}

export interface ProductSpecReview {
  row_number: number;
  major_category: string | null;
  category: string | null;
  item: string;
  configuration: string | null;
  core_information: string | null;
  selected_model: string | null;
  notes: string | null;
  check_confirmation: string | null;
  check_content: string | null;
}

export interface ProjectMemberReview {
  name: string;
  role: string;
  notes: string | null;
}

export interface MilestoneReview {
  code: string;
  name: string;
  output: string | null;
  schedule: PlanWindow;
  assignments: Record<"R" | "A" | "C" | "I", string[]>;
  risk_note: string | null;
}

export interface ProjectReview {
  current_version_number: number;
  document_version: string | null;
  active_plan_name: string | null;
  tbd_count: number;
  product_specs: ProductSpecReview[];
  members: ProjectMemberReview[];
  milestones: MilestoneReview[];
}

export interface EditableProjectMember {
  name: string;
  role: string;
  phone: string | null;
  email: string | null;
  notes: string | null;
}

export interface EditableMilestone extends Omit<MilestoneReview, "schedule"> {
  actual_completion: PlanWindow;
  variance_days: number | null;
  variance_note: string | null;
}

export interface EditableProjectData {
  current_version_number: number;
  template_id: string;
  template_version: string;
  document_version: string;
  source_sha256: string;
  project: { code: string; name: string };
  product_specs: ProductSpecReview[];
  members: EditableProjectMember[];
  milestones: EditableMilestone[];
  plan_versions: Array<{ name: string; milestones: Record<string, PlanWindow> }>;
  active_plan_name: string;
}

export interface ProjectDataOperation {
  op: "add" | "replace" | "remove";
  resource: "product_spec" | "member" | "milestone" | "plan" | "raci";
  key: string;
  value?: Record<string, unknown>;
}

export interface ProjectChangeSet {
  id: string;
  project_id: string;
  base_version_number: number;
  source: string;
  operations: ProjectDataOperation[];
  diff: DiffEntry[];
  reason: string;
  status: "pending" | "published" | "cancelled";
  submitted_by_actor_id?: string;
  published_by_actor_id?: string | null;
  created_at?: string;
  resolved_at?: string | null;
}
