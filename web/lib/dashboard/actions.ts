"use server";

import { signOut } from "@workos-inc/authkit-nextjs";
import { searchFiles } from "./api";
import type { SearchHit } from "./types";

export async function signOutAction() {
  await signOut({ returnTo: "/" });
}

export async function searchCorpusAction(query: string): Promise<SearchHit[] | null> {
  const trimmed = query.trim();
  if (!trimmed) return [];
  try {
    const data = await searchFiles(trimmed);
    return data.results;
  } catch {
    return null;
  }
}
