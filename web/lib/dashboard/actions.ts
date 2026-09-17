"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createApiKey, revokeApiKey } from "./api";

const NEW_KEY_COOKIE = "ad_new_key";

export async function createKeyAction(formData: FormData) {
  const name = String(formData.get("name") ?? "").trim() || null;
  const created = await createApiKey(name);
  const jar = await cookies();
  jar.set(NEW_KEY_COOKIE, created.key, {
    httpOnly: true,
    sameSite: "lax",
    maxAge: 60,
    path: "/dashboard/keys",
  });
  redirect("/dashboard/keys");
}

export async function revokeKeyAction(formData: FormData) {
  const id = String(formData.get("id") ?? "");
  if (!id) {
    throw new Error("Missing key id");
  }
  await revokeApiKey(id);
  redirect("/dashboard/keys");
}

export async function readAndClearNewKey(): Promise<string | null> {
  const jar = await cookies();
  const value = jar.get(NEW_KEY_COOKIE)?.value ?? null;
  if (value) {
    jar.delete({ name: NEW_KEY_COOKIE, path: "/dashboard/keys" });
  }
  return value;
}
