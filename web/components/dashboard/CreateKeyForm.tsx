import { createKeyAction } from "@/lib/dashboard/actions";

export function CreateKeyForm() {
  return (
    <form action={createKeyAction} className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-steel">Key name</span>
        <input
          name="name"
          type="text"
          placeholder="mcp-prod"
          className="border border-rule bg-paper px-3 py-1.5"
        />
      </label>
      <button type="submit" className="bg-ink px-3 py-1.5 text-sm text-paper hover:bg-cobalt">
        Create key
      </button>
    </form>
  );
}
