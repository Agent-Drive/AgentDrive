import Link from "next/link";
import { AgentDriveMark } from "@/app/(marketing)/_components/home/AgentDriveMark";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-2 text-ink no-underline">
      <AgentDriveMark className="h-6 w-6 text-ink" />
      <span className="font-display text-xl tracking-tight">Agent Drive</span>
    </Link>
  );
}
