import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col justify-center px-6">
      <p className="font-mono text-sm text-steel">404</p>
      <h1 className="mt-2 font-display text-4xl">Page not found</h1>
      <p className="mt-3 text-steel">That URL is not part of Agent Drive.</p>
      <Link href="/" className="mt-6 text-cobalt underline-offset-4 hover:underline">
        Back to home
      </Link>
    </main>
  );
}
