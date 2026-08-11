const SEARCH_FIELDS = [
  "item",
  "major_category",
  "category",
  "configuration",
  "core_information",
  "selected_model",
  "notes",
];

export function filterProductSpecs(specs, keyword) {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return specs;

  return specs.filter((spec) => SEARCH_FIELDS.some((field) =>
    String(spec[field] ?? "").toLowerCase().includes(normalizedKeyword),
  ));
}
