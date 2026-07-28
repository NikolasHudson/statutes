// Typed-ish client for /api/edms/*, plus the API-key fallback.
//
// Two credentials are accepted by the server and therefore by this module:
// the OAuth bearer token (the normal path — see auth.js) and a pasted API key
// (the options-page fallback for a machine where the OAuth popup misbehaves).
// The bearer path is tried first; the key is only used when there is no
// session, so pasting a key does not silently override a real sign-in.

import { backendUrl } from "./config.js";
import { getAccessToken, invalidateAccessToken } from "./auth.js";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function apiKey() {
  const stored = await chrome.storage.local.get({ edmsApiKey: "" });
  return (stored.edmsApiKey || "").trim();
}

async function authHeaders() {
  const token = await getAccessToken();
  if (token) return { Authorization: `Bearer ${token}` };
  const key = await apiKey();
  if (key) return { "X-API-Key": key };
  return null;
}

/**
 * Authed call to the app API. Retries once on 401 with a fresh token, because
 * an access token can expire between the check and the request.
 */
export async function apiFetch(path, init = {}, { retry = true } = {}) {
  const headers = await authHeaders();
  if (!headers) throw new ApiError(401, "Sign in to Hudson EDMSpro first.");
  const base = await backendUrl();
  const resp = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...headers, ...(init.headers || {}) },
  });
  if (resp.status === 401 && retry && headers.Authorization) {
    invalidateAccessToken();
    return apiFetch(path, init, { retry: false });
  }
  const text = await resp.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!resp.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body ? String(body.detail) : resp.statusText;
    throw new ApiError(resp.status, detail);
  }
  return body;
}

// --- endpoints -------------------------------------------------------------

export const getSettings = () => apiFetch("/api/edms/settings");

export const getSafety = () => apiFetch("/api/edms/safety");

// --- parked for v2 ---------------------------------------------------------
// Nothing below is called in v1: the save flow that used it is gone and the
// server 404s these paths unless EDMS_CLOUD_ENABLED is on. Kept so v2 is a
// re-wire rather than a rewrite.

export const routeFiling = (meta) =>
  apiFetch("/api/edms/route", { method: "POST", body: JSON.stringify(meta) });

export const completeSync = (syncId, payload) =>
  apiFetch(`/api/edms/sync/${syncId}/complete`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const failSync = (syncId, error) =>
  apiFetch(`/api/edms/sync/${syncId}/fail`, {
    method: "POST",
    body: JSON.stringify({ error: String(error || "").slice(0, 1000) }),
  });

export const listSyncs = (params = {}) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const query = q.toString();
  return apiFetch(`/api/edms/syncs${query ? `?${query}` : ""}`);
};

export const getCaseFolder = (caseNumber) =>
  apiFetch(`/api/edms/case-folders/${encodeURIComponent(caseNumber)}`);

export const putCaseFolder = (caseNumber, payload) =>
  apiFetch(`/api/edms/case-folders/${encodeURIComponent(caseNumber)}`, {
    method: "PUT",
    body: JSON.stringify(payload || {}),
  });

export const deleteCaseFolder = (caseNumber) =>
  apiFetch(`/api/edms/case-folders/${encodeURIComponent(caseNumber)}`, { method: "DELETE" });

export const listFolders = (parentId = "root") =>
  apiFetch(`/api/edms/integrations/onedrive/folders?parent_id=${encodeURIComponent(parentId)}`);

export const createFolder = (parentId, name) =>
  apiFetch("/api/edms/integrations/onedrive/folders", {
    method: "POST",
    body: JSON.stringify({ parent_id: parentId || "root", name }),
  });

/**
 * Contribute an opted-in filing. The body is the raw PDF and the metadata
 * rides in the query string — the server streams the body straight to storage,
 * so a multipart envelope would only buy a buffering step neither side wants.
 */
export async function contribute(blob, meta) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(meta)) {
    if (v) q.set(k, String(v));
  }
  return apiFetch(`/api/edms/crowdsource?${q.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/pdf" },
    body: blob,
  });
}
