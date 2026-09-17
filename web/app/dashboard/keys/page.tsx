import { listApiKeys } from "@/lib/dashboard/api";
import { readAndClearNewKey } from "@/lib/dashboard/actions";
import { CreateKeyForm } from "@/components/dashboard/CreateKeyForm";
import { KeyList } from "@/components/dashboard/KeyList";

export default async function KeysPage() {
  const [data, newKey] = await Promise.all([listApiKeys(), readAndClearNewKey()]);

  return (
    <main>
      <h1 className="font-display text-4xl tracking-tight">API keys</h1>
      <p className="mt-2 max-w-xl text-sm text-steel">
        Keys are for MCP and the CLI. The raw value is shown once.
      </p>
      {newKey ? (
        <p className="mt-6 border border-cobalt px-4 py-3 font-mono text-sm break-all">
          {newKey}
        </p>
      ) : null}
      <div className="mt-8">
        <CreateKeyForm />
      </div>
      <div className="mt-8">
        <KeyList keys={data.api_keys} />
      </div>
    </main>
  );
}
