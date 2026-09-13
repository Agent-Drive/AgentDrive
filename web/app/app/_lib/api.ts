import "server-only";

import { signOut, withAuth } from "@workos-inc/authkit-nextjs";
import { notFound, redirect } from "next/navigation";
import type {
  ApiKeyCreateResponse,
  ApiKeyListResponse,
  DriveFile,
  FileListResponse,
} from "./types";

const API_URL = process.env.AGENTDRIVE_API_URL ?? "http://localhost:8080";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { accessToken } = await withAuth({ ensureSignedIn: true });
  if (!accessToken) {
    redirect("/login");
  }

  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (res.status === 401) {
    await signOut({ returnTo: "/login" });
  }

  if (res.status === 403) {
    redirect("/app/access-denied");
  }

  if (res.status === 404) {
    notFound();
  }

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    throw new Error(`API ${res.status} on ${path}`);
  }

  return res.json() as Promise<T>;
}

export function listFiles() {
  return apiFetch<FileListResponse>("/v1/files");
}

export function getFile(fileId: string) {
  return apiFetch<DriveFile>(`/v1/files/${fileId}`);
}

export function listApiKeys() {
  return apiFetch<ApiKeyListResponse>("/v1/api-keys");
}

export function createApiKey(name: string | null) {
  return apiFetch<ApiKeyCreateResponse>("/v1/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function revokeApiKey(keyId: string) {
  return apiFetch<void>(`/v1/api-keys/${keyId}`, { method: "DELETE" });
}
