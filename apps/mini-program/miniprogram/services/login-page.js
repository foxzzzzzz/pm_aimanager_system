export const INVALID_INVITATION_MESSAGE = "邀请码已使用、已过期或已重新生成";

export function projectAccessState(projects) {
  return {
    hasProjects: projects.length > 0,
    projectCount: projects.length,
  };
}

export function invitationErrorMessage(error) {
  if (!(error instanceof Error)) return "操作失败";

  if (/invitation (?:is invalid|has expired|not found)|404/i.test(error.message)) {
    return INVALID_INVITATION_MESSAGE;
  }
  return error.message;
}
