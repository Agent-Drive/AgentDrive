import { withAuth } from "@workos-inc/authkit-nextjs";
import { DashboardNav } from "@/components/dashboard/DashboardNav";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = await withAuth({ ensureSignedIn: true });

  return (
    <div className="min-h-svh">
      <div className="mx-auto grid min-h-svh max-w-6xl grid-cols-1 md:grid-cols-[12rem_1fr]">
        <DashboardNav email={user.email} />
        <div className="px-6 py-8">{children}</div>
      </div>
    </div>
  );
}
