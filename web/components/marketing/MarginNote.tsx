export function MarginNote({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <aside className="margin-note">
      {title ? (
        <strong className="mb-1 block font-medium text-[var(--ink)]">{title}</strong>
      ) : null}
      {children}
    </aside>
  );
}
