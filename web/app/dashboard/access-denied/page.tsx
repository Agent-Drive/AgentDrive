export default function AccessDeniedPage() {
  return (
    <>
      <h1 className="font-geist text-lg font-medium tracking-tight text-[var(--ink)]">
        Ask an admin
      </h1>
      <p className="mt-3 max-w-md text-[0.75rem] text-[var(--ink-dim)]">
        Your account is signed in, but this workspace is not auto-provisioning new tenants. Ask an
        admin to add you.
      </p>
    </>
  );
}
