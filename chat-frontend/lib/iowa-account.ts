// Typed API helpers for /api/auth/* (profile + password) and
// /api/account/api-keys (list / create / revoke). Same shapes as the
// existing Vite frontend's api.ts — keep them in sync.

import type { AuthUser } from "@/components/auth-gate";

export type APIKey = {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
};

export type CreatedAPIKey = APIKey & { raw_key: string };

export type PublicConfig = {
  mcp_host: string | null;
  source: "explicit" | "codespaces" | "unset";
};

export class AccountError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    ...init,
  });
  const text = await r.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!r.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : null) ?? r.statusText;
    throw new AccountError(r.status, detail);
  }
  return body as T;
}

// ---- profile + password -------------------------------------------------

export const updateProfile = (data: { full_name?: string; email?: string }) =>
  request<AuthUser>("/api/auth/me", {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const changePassword = (data: {
  current_password: string;
  new_password: string;
}) =>
  request<{ status: string }>("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify(data),
  });

// ---- API keys -----------------------------------------------------------

export const listKeys = () => request<APIKey[]>("/api/account/api-keys");

export const createKey = (name: string) =>
  request<CreatedAPIKey>("/api/account/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const revokeKey = (id: number) =>
  request<{ status: string; id: number }>(
    `/api/account/api-keys/${id}`,
    { method: "DELETE" },
  );

// ---- public config ------------------------------------------------------

export const fetchPublicConfig = () =>
  request<PublicConfig>("/api/config");

// ---- formatting helpers -------------------------------------------------

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
