"use client";

export default function DashboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <>
      <h1 className="font-geist text-lg font-medium text-[var(--ink)]">Dashboard failed</h1>
      <p className="mt-2 text-[0.75rem] text-[var(--ink-dim)]">
        The request did not complete. Try again.
      </p>
      <button type="button" onClick={reset} className="ops-button mt-5">
        Try again
      </button>
    </>
  );
}
