import type { ApiKey } from "@/lib/dashboard/types";
import { formatWhen } from "@/lib/dashboard/format";
import { revokeKeyAction } from "@/lib/dashboard/actions";

export function KeyList({ keys }: { keys: ApiKey[] }) {
  if (keys.length === 0) {
    return <p className="border border-rule px-4 py-8 text-steel">No API keys yet.</p>;
  }

  return (
    <div className="overflow-x-auto border-t border-rule">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-rule text-steel">
            <th className="py-2 pr-4 font-medium">Name</th>
            <th className="py-2 pr-4 font-medium">Prefix</th>
            <th className="py-2 pr-4 font-medium">Last used</th>
            <th className="py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => (
            <tr key={key.id} className="border-b border-rule">
              <td className="py-3 pr-4">{key.name ?? "—"}</td>
              <td className="py-3 pr-4 font-mono text-xs">sk-ad-{key.key_prefix}…</td>
              <td className="py-3 pr-4 text-steel">
                {key.last_used ? formatWhen(key.last_used) : "Never"}
              </td>
              <td className="py-3 text-right">
                {key.revoked_at ? (
                  <span className="text-xs text-failed">revoked</span>
                ) : (
                  <form action={revokeKeyAction}>
                    <input type="hidden" name="id" value={key.id} />
                    <button type="submit" className="text-xs text-failed hover:underline">
                      Revoke
                    </button>
                  </form>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
