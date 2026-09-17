import Link from "next/link";
import type { BlogPost } from "@/lib/marketing/posts";

export function PostRow({ post }: { post: BlogPost }) {
  return (
    <Link
      href={post.href}
      className="group grid grid-cols-1 items-center gap-4 border-b border-[var(--ink-faint)] px-2 py-5 transition-opacity hover:opacity-80 md:grid-cols-[180px_1fr_160px_60px]"
    >
      <div className="font-mono text-[0.75rem] text-[var(--ink-dim)]">
        <span>{post.dateLabel}</span>
        <span className="mx-1.5 text-[var(--ink-faint)]">·</span>
        <span className="meta-tag">{post.category}</span>
      </div>
      <h3 className="font-geist text-lg font-medium tracking-tight text-[var(--ink)] transition-colors group-hover:text-[var(--accent)]">
        {post.title}
      </h3>
      <span className="font-mono text-[0.75rem] text-[var(--ink-dim)] md:text-right">
        {post.author}
      </span>
      <span className="font-mono text-[0.75rem] text-[var(--ink-dim)] md:text-right">
        {post.readMinutes}m
      </span>
    </Link>
  );
}
