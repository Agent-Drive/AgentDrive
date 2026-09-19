import { createKeyAction } from "@/lib/dashboard/actions";

export function CreateKeyForm() {
  return (
    <form action={createKeyAction} className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1">
        <span className="font-mono text-[0.6rem] tracking-wide text-[var(--ink-dim)] uppercase">
          Key name
        </span>
        <input name="name" type="text" placeholder="mcp-prod" className="ops-input" />
      </label>
      <button type="submit" className="ops-button">
        Create key
      </button>
    </form>
  );
}
