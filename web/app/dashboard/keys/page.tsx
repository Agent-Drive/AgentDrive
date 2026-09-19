import { listApiKeys } from "@/lib/dashboard/api";
import { readAndClearNewKey } from "@/lib/dashboard/actions";
import { CreateKeyForm } from "@/components/dashboard/CreateKeyForm";
import { KeyList } from "@/components/dashboard/KeyList";

export default async function KeysPage() {
  const [data, newKey] = await Promise.all([listApiKeys(), readAndClearNewKey()]);

  return (
    <>
      <h1 className="font-geist text-lg font-medium tracking-tight text-[var(--ink)]">API keys</h1>
      <p className="mt-1 max-w-xl text-[0.75rem] text-[var(--ink-dim)]">
        Optional. MCP install already creates a key. The raw value is shown once.
      </p>
      {newKey ? (
        <p className="mt-4 rounded border border-[var(--accent)] px-3 py-2 font-mono text-[0.65rem] break-all text-[var(--ink)]">
          {newKey}
        </p>
      ) : null}
      <div className="mt-5">
        <CreateKeyForm />
      </div>
      <div className="mt-5 flex-grow overflow-auto rounded border border-[var(--border)] bg-[var(--surface)]">
        <KeyList keys={data.api_keys} />
      </div>
    </>
  );
}
