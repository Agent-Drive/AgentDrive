import { getSignInUrl } from "@workos-inc/authkit-nextjs";
import { redirect } from "next/navigation";

export const GET = async () => {
  const signInUrl = await getSignInUrl({ returnTo: "/app" });
  return redirect(signInUrl);
};
