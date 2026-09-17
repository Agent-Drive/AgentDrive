"use client";

export default function FilesError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main>
      <h1 className="font-display text-3xl">Could not load files</h1>
      <p className="mt-3 text-steel">The files request failed.</p>
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
