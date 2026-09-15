"use client";

import { MarketingChrome } from "./_components/MarketingChrome";

export default function MarketingError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <MarketingChrome>
      <main className="mx-auto max-w-5xl px-6 py-16">
        <h1 className="font-display text-4xl">This page failed</h1>
        <p className="mt-3 text-steel">Reload or go back to the homepage.</p>
        <button
          type="button"
          onClick={reset}
          className="mt-6 border border-ink px-3 py-1.5 text-sm"
        >
          Try again
        </button>
      </main>
    </MarketingChrome>
  );
}
