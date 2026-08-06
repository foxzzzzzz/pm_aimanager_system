export type RequestMethod = "GET" | "POST" | "PATCH";
export function createRequester(options: {
  baseUrl: string;
  getToken: () => string;
  requestKey: () => string;
  transport: (options: WechatMiniprogram.RequestOption) => void;
}): <T>(path: string, method?: RequestMethod, data?: WechatMiniprogram.IAnyObject) => Promise<T>;
