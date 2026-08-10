import assert from "node:assert/strict";
import test from "node:test";

import { visiblePage } from "../miniprogram/services/pagination.js";

test("project review pagination exposes an incremental slice", () => {
  const items = Array.from({ length: 12 }, (_, index) => index + 1);
  assert.deepEqual(visiblePage(items, 1, 5), [1, 2, 3, 4, 5]);
  assert.deepEqual(visiblePage(items, 2, 5), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(visiblePage(items, 3, 5), items);
});
