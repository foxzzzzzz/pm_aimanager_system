export const mergeMilestonePrefill = (current, result) => ({
  code: result.milestone_code || current.code,
  kind: result.kind || current.kind,
  startDate: result.start_date || current.startDate,
  endDate: result.end_date || current.endDate,
  reason: result.reason || current.reason,
  prefillApplied: true,
  requiresConfirmation: result.requires_confirmation !== false,
});
