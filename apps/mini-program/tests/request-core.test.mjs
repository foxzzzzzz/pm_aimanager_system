import assert from "node:assert/strict";
import test from "node:test";

import { createRequester } from "../miniprogram/services/request-core.mjs";

test("requester attaches mobile bearer and idempotency headers", async () => {
  let captured;
  const request = createRequester({
    baseUrl: "https://api.example/api/v1",
    getToken: () => "mobile-token",
    requestKey: () => "request-key",
    transport: (options) => {
      captured = options;
      options.success({ statusCode: 200, data: { ok: true } });
    },
  });

  assert.deepEqual(await request("/mobile/issues/1", "PATCH", { status: "处理中" }), { ok: true });
  assert.equal(captured.header.Authorization, "Bearer mobile-token");
  assert.equal(captured.header["X-Idempotency-Key"], "request-key");
  assert.equal(captured.method, "PATCH");
});

test("requester exposes the backend error detail", async () => {
  const request = createRequester({
    baseUrl: "https://api.example/api/v1",
    getToken: () => "",
    requestKey: () => "unused",
    transport: (options) => options.success({ statusCode: 409, data: { detail: "版本冲突" } }),
  });

  await assert.rejects(request("/mobile/messages"), /版本冲突/);
});

test("requester exposes structured conflict messages", async () => {
  const request = createRequester({
    baseUrl: "https://api.example/api/v1",
    getToken: () => "",
    requestKey: () => "unused",
    transport: (options) => options.success({
      statusCode: 409,
      data: { detail: { message: "项目版本已变化", current_version_number: 3 } },
    }),
  });

  await assert.rejects(request("/mobile/projects/1"), /项目版本已变化/);
});
