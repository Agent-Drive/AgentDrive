export default function AccessDeniedPage() {
  return (
    <main>
      <h1 className="font-display text-4xl tracking-tight">Ask an admin</h1>
      <p className="mt-4 max-w-md text-steel">
        Your account is signed in, but this workspace is not auto-provisioning new
        tenants. Ask an admin to add you.
      </p>
    </main>
  );
}
