export function createRequester({ baseUrl, getToken, requestKey, retryAttempts = 0, transport }) {
  return (path, method = "GET", data) => {
    const accessToken = getToken();
    const idempotencyKey = method !== "GET" ? requestKey() : "";
    return new Promise((resolve, reject) => {
      let retriesRemaining = retryAttempts;
      const send = () => transport({
        url: `${baseUrl}${path}`,
        method,
        data,
        header: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          ...(idempotencyKey ? { "X-Idempotency-Key": idempotencyKey } : {}),
        },
        success: (response) => {
          if (response.statusCode >= 200 && response.statusCode < 300) {
            resolve(response.data);
            return;
          }
          const detail = response.data && response.data.detail;
          const message = typeof detail === "string"
            ? detail
            : detail && typeof detail === "object" && typeof detail.message === "string"
              ? detail.message
              : `请求失败：${response.statusCode}`;
          reject(new Error(message));
        },
        fail: (reason) => {
          if (retriesRemaining > 0) {
            retriesRemaining -= 1;
            send();
            return;
          }
          reject(reason);
        },
      });
      send();
    });
  };
}
