export const INVALID_INVITATION_MESSAGE: string;

export function projectAccessState(projects: unknown[]): {
  hasProjects: boolean;
  projectCount: number;
  projectAccessChecked: boolean;
  projectAccessError: boolean;
};

export function projectAccessErrorState(): {
  hasProjects: boolean;
  projectCount: number;
  projectAccessChecked: boolean;
  projectAccessError: boolean;
};

export function invitationErrorMessage(error: unknown): string;
export function mobileSessionErrorMessage(error: unknown): string | null;
