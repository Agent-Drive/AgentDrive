import type { ApiKey } from "@/lib/dashboard/types";
import { formatWhen } from "@/lib/dashboard/format";
import { revokeKeyAction } from "@/lib/dashboard/actions";

export function KeyList({ keys }: { keys: ApiKey[] }) {
  if (keys.length === 0) {
    return (
      <p className="px-3 py-8 text-center font-mono text-[0.65rem] text-[var(--ink-dim)]">
        No API keys yet.
      </p>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Prefix</th>
          <th>Last used</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {keys.map((key) => (
          <tr key={key.id}>
            <td>{key.name ?? "—"}</td>
            <td>sk-ad-{key.key_prefix}…</td>
            <td>{key.last_used ? formatWhen(key.last_used) : "Never"}</td>
            <td className="text-right">
              {key.revoked_at ? (
                <span className="status-badge status-err">revoked</span>
              ) : (
                <form action={revokeKeyAction}>
                  <input type="hidden" name="id" value={key.id} />
                  <button type="submit" className="font-mono text-[0.6rem] text-[var(--danger)]">
                    Revoke
                  </button>
                </form>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
