import type { Metadata } from "next";
import { BlogIndex } from "@/components/marketing/BlogIndex";
import "@/styles/blog.css";

export const metadata: Metadata = {
  title: "Blog — Agent Drive",
  description: "Thoughts, updates, and strategies on domain-specific data and AI agents.",
};

export default function BlogPage() {
  return (
    <div className="marketing-blog">
      <BlogIndex />
    </div>
  );
}
