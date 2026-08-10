export interface MilestonePrefillState {
  code: string;
  kind: "completed" | "delay";
  startDate: string;
  endDate: string;
  reason: string;
}

export interface MilestonePrefillResult {
  milestone_code: string | null;
  kind: "delay" | null;
  start_date: string | null;
  end_date: string | null;
  reason: string;
  requires_confirmation: boolean;
}

export function mergeMilestonePrefill(
  current: MilestonePrefillState,
  result: MilestonePrefillResult,
): MilestonePrefillState & { prefillApplied: true; requiresConfirmation: boolean };
