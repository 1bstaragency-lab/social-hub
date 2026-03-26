import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// ── Accounts ─────────────────────────────────────────────────────────────────
export const accountsApi = {
  list: (params) => api.get("/accounts/", { params }),
  get: (id) => api.get(`/accounts/${id}`),
  create: (data) => api.post("/accounts/", data),
  update: (id, data) => api.patch(`/accounts/${id}`, data),
  delete: (id) => api.delete(`/accounts/${id}`),
  healthCheck: (id) => api.post(`/accounts/${id}/health-check`),
  healthCheckAll: () => api.post("/accounts/health-check/all"),
  updateCredentials: (id, creds) =>
    api.post(`/accounts/${id}/credentials`, creds),
};

// ── SoundCloud Browser Auth ──────────────────────────────────────────────────
export const soundcloudAuthApi = {
  login: (email, password) =>
    api.post("/soundcloud/login", { email, password }),
  validate: (accountId) =>
    api.post("/soundcloud/validate", { account_id: accountId }),
  relogin: (accountId) =>
    api.post("/soundcloud/relogin", { account_id: accountId }),
};

// ── Campaigns ────────────────────────────────────────────────────────────────
export const campaignsApi = {
  list: (params) => api.get("/campaigns/", { params }),
  get: (id) => api.get(`/campaigns/${id}`),
  create: (data) => api.post("/campaigns/", data),
  update: (id, data) => api.patch(`/campaigns/${id}`, data),
  delete: (id) => api.delete(`/campaigns/${id}`),
};

// ── Posts ───────────────────────────────────────────────────────────────────
export const postsApi = {
  list: (params) => api.get("/posts/", { params }),
  get: (id) => api.get(`/posts/${id}`),
  create: (data) => api.post("/posts/", data),
  crossPost: (payloads) => api.post("/posts/cross-post", payloads),
  update: (id, data) => api.patch(`/posts/${id}`, data),
  delete: (id) => api.delete(`/posts/${id}`),
  publishNow: (id) => api.post(`/posts/${id}/publish-now`),
};

// ── Engagement ──────────────────────────────────────────────────────────────
export const engagementApi = {
  action: (data) => api.post("/engagement/action", data),
  bulk: (data) => api.post("/engagement/bulk", data),
  taskStatus: (taskId) => api.get(`/engagement/task/${taskId}`),
};

// ── Analytics ───────────────────────────────────────────────────────────────
export const analyticsApi = {
  dashboard: (params) => api.get("/analytics/dashboard", { params }),
  growth: (accountId, params) =>
    api.get(`/analytics/accounts/${accountId}/growth`, { params }),
  snapshots: (accountId, params) =>
    api.get(`/analytics/accounts/${accountId}/snapshots`, { params }),
};
