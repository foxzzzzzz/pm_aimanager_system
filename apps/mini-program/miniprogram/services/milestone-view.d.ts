import type { Milestone } from "../types";

export type MilestoneFilterKey = "todo" | "upcoming" | "overdue" | "completed" | "all";

export interface MilestoneFilter {
  key: MilestoneFilterKey;
  label: string;
  count: number;
}

export function filterMilestones(
  milestones: Milestone[],
  key: MilestoneFilterKey,
  today: string,
  upcomingDays?: number,
): Milestone[];

export function buildMilestoneFilters(
  milestones: Milestone[],
  today: string,
  upcomingDays?: number,
): MilestoneFilter[];
