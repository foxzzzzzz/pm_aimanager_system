export const visiblePage = (items, page, pageSize) =>
  items.slice(0, Math.max(1, page) * pageSize);
