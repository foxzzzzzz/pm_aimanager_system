const SEARCH_FIELDS = [
  "item",
  "major_category",
  "category",
  "configuration",
  "core_information",
  "selected_model",
  "notes",
];

const normalize = (value) => String(value ?? "").toLowerCase();

const filterByFields = (items, keyword, fields) => {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return items;
  return items.filter((item) => fields.some((field) =>
    normalize(item[field]).includes(normalizedKeyword),
  ));
};

export function filterProductSpecs(specs, keyword) {
  return filterByFields(specs, keyword, SEARCH_FIELDS);
}

export function filterProjectMembers(members, keyword) {
  return filterByFields(members, keyword, ["name", "role", "notes"]);
}

export function filterRaciRows(rows, keyword) {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return rows;
  return rows.filter((row) => [row.code, row.name, row.output, ...row.roles.map((role) => role.names)]
    .some((value) => normalize(value).includes(normalizedKeyword)));
}

export function hasLongSpecContent(spec, maxLength) {
  return `${spec.detail ?? ""}${spec.notes ?? ""}`.length > maxLength;
}
