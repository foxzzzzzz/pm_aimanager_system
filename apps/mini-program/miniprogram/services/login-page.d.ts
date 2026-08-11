export const INVALID_INVITATION_MESSAGE: string;

export function projectAccessState(projects: unknown[]): {
  hasProjects: boolean;
  projectCount: number;
};

export function invitationErrorMessage(error: unknown): string;
