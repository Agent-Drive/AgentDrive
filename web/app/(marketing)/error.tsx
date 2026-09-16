"use client";

export default function MarketingError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="min-h-svh bg-[#090B10] px-6 py-16 text-[#F0F4F8]">
      <h1 className="text-4xl tracking-tight">This page failed</h1>
      <p className="mt-3 text-[rgba(240,244,248,0.5)]">Reload or go back to the homepage.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 border border-[rgba(240,244,248,0.1)] px-3 py-1.5 text-sm"
      >
        Try again
      </button>
    </main>
  );
}
