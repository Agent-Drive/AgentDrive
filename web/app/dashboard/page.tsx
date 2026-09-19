import { listFiles } from "@/lib/dashboard/api";
import { OverviewMain } from "@/components/dashboard/ops/OverviewMain";

export default async function DashboardHomePage() {
  const data = await listFiles();

  return <OverviewMain files={data.files} />;
}
