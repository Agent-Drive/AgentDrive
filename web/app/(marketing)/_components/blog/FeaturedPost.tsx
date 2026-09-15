import Link from "next/link";
import type { BlogPost } from "../../_data/posts";

export function FeaturedPost({ post }: { post: BlogPost }) {
  return (
    <section className="hero-post group block">
      <Link href={post.href} className="block">
        <div className="hero-bg opacity-80 transition-opacity duration-300 group-hover:opacity-100" />
        <div className="relative z-10 mx-auto -mt-24 max-w-4xl px-4 text-center">
          <span className="meta-tag mb-4 block">{post.category}</span>
          <h2 className="font-geist mb-4 text-4xl leading-tight font-medium tracking-tight text-[var(--ink)] transition-colors group-hover:text-[var(--accent)]">
            {post.title}
          </h2>
          {post.excerpt ? (
            <p className="font-geist mx-auto mb-6 max-w-2xl text-xl text-[var(--ink-dim)]">
              {post.excerpt}
            </p>
          ) : null}
          <div className="flex items-center justify-center gap-4 font-mono text-[0.75rem] text-[var(--ink-dim)]">
            <span>By {post.author}</span>
            <span className="text-[var(--ink-faint)]">|</span>
            <span>{post.dateLabel}</span>
          </div>
        </div>
      </Link>
    </section>
  );
}
