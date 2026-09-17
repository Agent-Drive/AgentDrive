const SECTIONS = [
  { href: "#the-generalization-trap", label: "The generalization trap" },
  { href: "#why-marketing-copy-fails", label: "Why marketing copy fails" },
  { href: "#building-the-corpus", label: "Building the corpus" },
] as const;

export function ArticleToc() {
  return (
    <aside className="left-sidebar">
      <div className="sticky top-32 flex flex-col gap-6">
        <div>
          <div className="mb-5 border-b border-[var(--ink-faint)] pb-3">
            <span className="block font-mono text-[0.7rem] font-medium text-[var(--ink-dim)]">
              In this article
            </span>
          </div>
          <ul className="flex flex-col gap-3 font-mono text-[0.75rem] text-[var(--ink-dim)]">
            {SECTIONS.map((section) => (
              <li key={section.href} className="group flex items-start gap-2">
                <span className="mt-0.5 text-[var(--accent)] opacity-40 transition-opacity group-hover:opacity-100">
                  —
                </span>
                <a href={section.href} className="transition-colors hover:text-[var(--ink)]">
                  {section.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </aside>
  );
}
