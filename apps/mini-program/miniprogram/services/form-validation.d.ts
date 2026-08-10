export interface MilestoneUpdateInput {
  kind: "completed" | "delay";
  date: string;
  startDate: string;
  endDate: string;
  reason: string;
  requiresConfirmation: boolean;
}

export interface IssueCreateInput {
  description: string;
  impact: string;
  ownerName: string;
  dueDate: string;
}

export function validateMilestoneUpdate(input: MilestoneUpdateInput): string | null;
export function validateIssueCreate(input: IssueCreateInput): string | null;
