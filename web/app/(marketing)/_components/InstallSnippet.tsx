const INSTALL = "curl -fsSL https://api.agentdrive.so/install.sh | sh";

export function InstallSnippet() {
  return (
    <section className="mt-20 max-w-3xl">
      <h2 className="font-display text-3xl">Install MCP</h2>
      <p className="mt-3 max-w-xl text-steel">
        Agents talk to Agent Drive through MCP. The dashboard is for looking at what
        they stored — not for ingest.
      </p>
      <pre className="mt-6 overflow-x-auto border border-rule bg-ink px-4 py-3 font-mono text-sm text-paper">
        <code>{INSTALL}</code>
      </pre>
    </section>
  );
}
