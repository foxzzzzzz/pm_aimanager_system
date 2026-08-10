import type { Milestone } from "../types";

export function labelPlanState(value: string): string;
export function labelSeverity(value: string): string;
export function labelMessageType(value: string): string;
export function formatDate(value: string | null | undefined): string;
export function formatDateTime(
  value: string | null | undefined,
  timezoneOffsetMinutes: number,
): string;
export function presentPlan(plan: Milestone["plan"]): string;
