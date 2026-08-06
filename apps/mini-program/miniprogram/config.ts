// Replace the base URL and disable development login before a real WeChat build.
export const runtimeConfig = {
  apiBaseUrl: "http://localhost:18000/api/v1",
  useDevelopmentLogin: true,
  developmentLoginCode: "dev:mini-program-user",
};
