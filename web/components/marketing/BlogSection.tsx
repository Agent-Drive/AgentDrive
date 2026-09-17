import Link from "next/link";
import { BLOG_POSTS } from "@/lib/marketing/posts";

export function BlogSection() {
  return (
    <section id="blog" style={{ marginTop: 0 }}>
      <div className="mb-5 flex items-baseline justify-between">
        <span className="font-mono text-[0.68rem] tracking-widest text-[var(--ink-dim)] uppercase">
          Blog
        </span>
        <Link
          href="/blog"
          className="border-b border-[var(--ink-faint)] pb-px font-mono text-[0.65rem] tracking-wide text-[var(--ink-dim)] transition-colors hover:border-[var(--ink)] hover:text-[var(--ink)]"
        >
          All posts →
        </Link>
      </div>

      <table className="w-full border-collapse">
        <tbody>
          {BLOG_POSTS.map((post, i) => (
            <tr
              key={post.title}
              className={
                i === BLOG_POSTS.length - 1
                  ? "border-t border-b border-[var(--ink-faint)]"
                  : "border-t border-[var(--ink-faint)]"
              }
            >
              <td className="w-[90px] py-4 pr-6 font-mono text-[0.65rem] whitespace-nowrap text-[var(--ink-dim)]">
                {post.date}
              </td>
              <td className="py-4 pr-8 text-[0.84rem] font-medium text-[var(--ink)]">
                <Link href={post.href} className="transition-opacity hover:opacity-60">
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
