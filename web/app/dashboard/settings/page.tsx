import { withAuth } from "@workos-inc/authkit-nextjs";

export default async function SettingsPage() {
  const { user } = await withAuth({ ensureSignedIn: true });
  const name = `${user.firstName ?? ""} ${user.lastName ?? ""}`.trim() || "—";

  return (
    <div className="mx-auto w-full max-w-md">
      <h1 className="font-geist text-lg font-medium tracking-tight text-[var(--ink)]">
        Settings
      </h1>
      <p className="mt-1 text-[0.75rem] text-[var(--ink-dim)]">Account</p>
      <dl className="mt-5 divide-y divide-[var(--border)] rounded border border-[var(--border)] bg-[var(--surface)]">
        <div className="flex items-baseline justify-between gap-4 px-3 py-2.5">
          <dt className="font-mono text-[0.6rem] text-[var(--ink-dim)]">Name</dt>
          <dd className="truncate text-[0.75rem] text-[var(--ink)]">{name}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 px-3 py-2.5">
          <dt className="font-mono text-[0.6rem] text-[var(--ink-dim)]">Email</dt>
          <dd className="truncate font-mono text-[0.7rem] text-[var(--ink)]">{user.email}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 px-3 py-2.5">
          <dt className="font-mono text-[0.6rem] text-[var(--ink-dim)]">Plan</dt>
          <dd className="font-mono text-[0.7rem] text-[var(--ink)]">Basic</dd>
        </div>
      </dl>
    </div>
  );
}
