"use client";

export default function RootError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col justify-center px-6">
      <h1 className="font-display text-4xl">Something broke</h1>
      <p className="mt-3 text-steel">The page failed to load. Try again.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 w-fit border border-ink px-3 py-1.5 text-sm"
      >
        Try again
      </button>
    </main>
  );
}
