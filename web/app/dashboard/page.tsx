import { listFiles } from "@/lib/dashboard/api";
import { FileTable } from "@/components/dashboard/FileTable";

export default async function DashboardHomePage() {
  const data = await listFiles();

  return (
    <main>
      <h1 className="font-display text-4xl tracking-tight">Files</h1>
      <p className="mt-2 text-sm text-steel">{data.total} stored</p>
      <div className="mt-8">
        <FileTable files={data.files} />
      </div>
    </main>
  );
}
