import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { MagazineArticle } from "../../_components/blog/MagazineArticle";
import { FEATURED_SLUG } from "../../_data/posts";
import "../../_styles/blog.css";

export function generateStaticParams() {
  return [{ slug: FEATURED_SLUG }];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  if (slug !== FEATURED_SLUG) {
    return { title: "Page not found — Agent Drive" };
  }

  return {
    title: "Why we started with ads — Agent Drive",
    description:
      "Why Agent Drive started with ads: the case for domain-specific data over general-purpose models.",
  };
}

export default async function BlogArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  if (slug !== FEATURED_SLUG) {
    notFound();
  }

  return (
    <div className="marketing-blog">
      <MagazineArticle />
    </div>
  );
}
