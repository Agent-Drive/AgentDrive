"use client";

export default function DashboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main>
      <h1 className="font-display text-4xl">Dashboard failed</h1>
      <p className="mt-3 text-steel">The request did not complete. Try again.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 border border-ink px-3 py-1.5 text-sm"
      >
        Try again
      </button>
    </main>
  );
}
