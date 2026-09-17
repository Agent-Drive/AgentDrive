"use client";

import { useState } from "react";
import type { BlogPost } from "@/lib/marketing/posts";
import { PostRow } from "./PostRow";

const INITIAL_VISIBLE = 2;

export function PostList({ posts }: { posts: BlogPost[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? posts : posts.slice(0, INITIAL_VISIBLE);
  const canExpand = !expanded && posts.length > INITIAL_VISIBLE;

  return (
    <section className="mx-auto w-full max-w-[1000px]">
      {visible.map((post) => (
        <PostRow key={post.slug} post={post} />
      ))}
      {canExpand ? (
        <div className="mt-8">
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="w-full cursor-pointer rounded-lg border border-[var(--ink-faint)] py-4 font-mono text-[0.75rem] text-[var(--ink-dim)] transition-colors hover:border-[var(--ink-dim)] hover:text-[var(--ink)]"
          >
            View more ↓
          </button>
        </div>
      ) : null}
    </section>
  );
}
