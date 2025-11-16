const DEFAULT_HTTP_BASE = "http://localhost:8000/api";
const DEFAULT_WS_BASE = "ws://localhost:8000/api";

export const API_HTTP_BASE =
  import.meta.env.VITE_API_HTTP_BASE?.replace(/\/$/, "") ?? DEFAULT_HTTP_BASE;
export const API_WS_BASE =
  import.meta.env.VITE_API_WS_BASE?.replace(/\/$/, "") ?? DEFAULT_WS_BASE;
