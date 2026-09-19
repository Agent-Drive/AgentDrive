import { Geist, Geist_Mono } from "next/font/google";
import { withAuth } from "@workos-inc/authkit-nextjs";
import { OpsSidebar } from "@/components/dashboard/ops/OpsSidebar";
import { listFilesOrEmpty } from "@/lib/dashboard/api";
import "@/styles/dashboard/ops.css";

const geistSans = Geist({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-geist-sans",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-geist-mono",
});

export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = await withAuth({ ensureSignedIn: true });
  const data = await listFilesOrEmpty();
  const usedBytes = data.files.reduce((sum, file) => sum + file.file_size, 0);

  return (
    <div className={`${geistSans.variable} ${geistMono.variable} ops-dashboard`}>
      <div className="ops-grid">
        <OpsSidebar
          usedBytes={usedBytes}
          firstName={user.firstName}
          lastName={user.lastName}
          email={user.email}
        />
        <main className="panel" style={{ background: "var(--bg)" }}>
          <div className="panel-content flex flex-col pt-3">{children}</div>
        </main>
      </div>
    </div>
  );
}
