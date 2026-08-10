export function createRequester({ baseUrl, getToken, requestKey, transport }) {
  return (path, method = "GET", data) => {
    const accessToken = getToken();
    return new Promise((resolve, reject) => {
      transport({
        url: `${baseUrl}${path}`,
        method,
        data,
        header: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          ...(method !== "GET" ? { "X-Idempotency-Key": requestKey() } : {}),
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
        fail: reject,
      });
    });
  };
}
