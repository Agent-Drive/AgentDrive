import Link from "next/link";

const POSTS = [
  {
    date: "Jun 2025",
    title: "Why we started with ads: the case for domain-specific data",
    category: "Blog",
    kind: "blog",
  },
  {
    date: "May 2025",
    title: "Introducing the v2.0 Ads Dataset Schema",
    category: "Changelog",
    kind: "changelog",
  },
  {
    date: "Apr 2025",
    title: "Why we built our own tokenizer for ad creative",
    category: "Blog",
    kind: "blog",
  },
  {
    date: "Mar 2025",
    title: "How AI agents use structured ad corpora for better copy generation",
    category: "Blog",
    kind: "blog",
  },
  {
    date: "Feb 2025",
    title: "Agent Drive Ads: public beta now open",
    category: "Changelog",
    kind: "changelog",
  },
] as const;

export function BlogSection() {
  return (
    <section id="blog" style={{ marginTop: 0 }}>
      <div className="mb-5 flex items-baseline justify-between">
        <span className="font-mono text-[0.68rem] tracking-widest text-[var(--ink-dim)] uppercase">
          Blog
        </span>
        <Link
          href="#blog"
          className="border-b border-[var(--ink-faint)] pb-px font-mono text-[0.65rem] tracking-wide text-[var(--ink-dim)] transition-colors hover:border-[var(--ink)] hover:text-[var(--ink)]"
        >
          All posts →
        </Link>
      </div>

      <table className="w-full border-collapse">
        <tbody>
          {POSTS.map((post, i) => (
            <tr
              key={post.title}
              className={
                i === POSTS.length - 1
                  ? "border-t border-b border-[var(--ink-faint)]"
                  : "border-t border-[var(--ink-faint)]"
              }
            >
              <td className="w-[90px] py-4 pr-6 font-mono text-[0.65rem] whitespace-nowrap text-[var(--ink-dim)]">
                {post.date}
              </td>
              <td className="py-4 pr-8 text-[0.84rem] font-medium text-[var(--ink)]">
                <Link href="#blog" className="transition-opacity hover:opacity-60">
                  {post.title}
                </Link>
              </td>
              <td className="w-[100px] py-4 text-right align-middle">
                <span
                  className={`cat-badge rounded-[2px] px-2 py-1 font-mono text-[0.6rem] tracking-wide uppercase ${
                    post.kind === "changelog" ? "cat-changelog" : "cat-blog"
                  }`}
                >
                  {post.category}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
