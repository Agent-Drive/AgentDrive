import Link from "next/link";
import { signOut } from "@workos-inc/authkit-nextjs";

export function DashboardNav({ email }: { email: string | null }) {
  return (
    <aside className="border-r border-rule px-6 py-8">
      <nav className="flex flex-col gap-3 text-sm">
        <Link href="/app/files" className="hover:text-cobalt">
          Files
        </Link>
        <Link href="/app/keys" className="hover:text-cobalt">
          API keys
        </Link>
      </nav>
      <div className="mt-12 text-xs text-steel">
        <p className="truncate">{email}</p>
        <form
          action={async () => {
            "use server";
            await signOut({ returnTo: "http://localhost:3000/" });
          }}
        >
          <button type="submit" className="mt-2 hover:text-ink">
            Sign out
          </button>
        </form>
      </div>
    </aside>
  );
}
