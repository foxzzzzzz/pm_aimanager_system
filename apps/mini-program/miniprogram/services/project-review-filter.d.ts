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
