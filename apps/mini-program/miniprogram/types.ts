export interface ProjectSummary {
  id: string;
  code: string;
  name: string;
  status: string;
  current_version_number: number;
}

export interface Milestone {
  code: string;
  name: string;
  actual_completion: { state: string; start_date: string | null; end_date: string | null };
  plan: { state: string; start_date: string | null; end_date: string | null } | null;
  can_update: boolean;
  can_approve: boolean;
}

export interface MobileDashboard {
  project: { id: string; code: string; name: string };
  current_version_number: number;
  active_plan_name: string;
  member_name: string;
  milestones: Milestone[];
}

export interface Issue {
  id: string;
  description: string;
  impact: string;
  owner_name: string;
  severity: "low" | "medium" | "high" | "critical";
  due_date: string;
  status: string;
  revision: number;
}

export interface ChangeProposal {
  id: string;
  milestone_code: string;
  kind: "completed" | "delay";
  reason: string;
  status: string;
  base_version_number: number;
}

export interface Message {
  id: string;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
}
