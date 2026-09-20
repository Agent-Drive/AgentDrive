import "server-only";

import { signOut, withAuth } from "@workos-inc/authkit-nextjs";
import { notFound, redirect } from "next/navigation";
import type {
  DownloadUrlResponse,
  DriveFile,
  FileListResponse,
  SearchResponse,
} from "./types";

const API_URL = process.env.AGENTDRIVE_API_URL ?? "http://localhost:8080";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { accessToken } = await withAuth({ ensureSignedIn: true });
  if (!accessToken) {
    redirect("/auth/sign-in");
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
    await signOut({ returnTo: "/auth/sign-in" });
  }

  if (res.status === 403) {
    redirect("/dashboard/access-denied");
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

export async function listFilesOrEmpty(): Promise<FileListResponse> {
  const { accessToken } = await withAuth({ ensureSignedIn: true });
  if (!accessToken) {
    redirect("/auth/sign-in");
  }

  const res = await fetch(`${API_URL}/v1/files`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  if (res.status === 401) {
    await signOut({ returnTo: "/auth/sign-in" });
  }

  if (!res.ok) {
    return { files: [], total: 0 };
  }

  return res.json() as Promise<FileListResponse>;
}

export function searchFiles(query: string, topK = 8) {
  return apiFetch<SearchResponse>("/v1/search", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export function getFile(fileId: string) {
  return apiFetch<DriveFile>(`/v1/files/${fileId}`);
}

export async function getFileDownloadUrl(fileId: string): Promise<DownloadUrlResponse | null> {
  const { accessToken } = await withAuth({ ensureSignedIn: true });
  if (!accessToken) {
    redirect("/auth/sign-in");
  }

  const res = await fetch(`${API_URL}/v1/files/${fileId}/download-url`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  if (res.status === 401) {
    await signOut({ returnTo: "/auth/sign-in" });
  }

  if (!res.ok) {
    return null;
  }

  return res.json() as Promise<DownloadUrlResponse>;
}
