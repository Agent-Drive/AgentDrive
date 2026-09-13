import { Hero } from "./_components/Hero";
import { InstallSnippet } from "./_components/InstallSnippet";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-5xl px-6 pb-24 pt-10">
      <Hero />
      <InstallSnippet />
    </main>
  );
}
