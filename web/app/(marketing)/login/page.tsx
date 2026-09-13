import { withAuth } from "@workos-inc/authkit-nextjs";
import { redirect } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const { user } = await withAuth();
  if (user) {
    redirect("/app");
  }

  return (
    <main className="mx-auto max-w-5xl px-6 pb-24 pt-10">
      <h1 className="font-display text-5xl tracking-tight">Sign in</h1>
      <p className="mt-4 max-w-md text-steel">
        Same WorkOS account as the CLI. The browser never sees your API key.
      </p>
      <Link
        href="/sign-in"
        className="mt-8 inline-block bg-ink px-4 py-2 text-sm text-paper hover:bg-cobalt"
      >
        Continue with WorkOS
      </Link>
    </main>
  );
}
