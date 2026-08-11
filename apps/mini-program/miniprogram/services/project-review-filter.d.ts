interface ProductSpecSearchable {
  item?: unknown;
  major_category?: unknown;
  category?: unknown;
  configuration?: unknown;
  core_information?: unknown;
  selected_model?: unknown;
  notes?: unknown;
}

export function filterProductSpecs<T extends ProductSpecSearchable>(
  specs: T[],
  keyword: string,
): T[];

interface ProjectMemberSearchable {
  name?: unknown;
  role?: unknown;
  notes?: unknown;
}

export function filterProjectMembers<T extends ProjectMemberSearchable>(
  members: T[],
  keyword: string,
): T[];

interface RaciSearchable {
  code?: unknown;
  name?: unknown;
  output?: unknown;
  roles: Array<{ names?: unknown }>;
}

export function filterRaciRows<T extends RaciSearchable>(rows: T[], keyword: string): T[];

export function hasLongSpecContent(
  spec: { detail?: unknown; notes?: unknown },
  maxLength: number,
): boolean;
