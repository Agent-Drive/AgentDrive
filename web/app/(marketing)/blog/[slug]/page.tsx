import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { notFound } from "next/navigation";
import { MagazineArticle } from "../../_components/blog/MagazineArticle";
import { FEATURED_SLUG } from "../../_data/posts";
import "../../_styles/blog.css";

const geistSans = Geist({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-geist-sans",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-geist-mono",
});

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
    <div className={`${geistSans.variable} ${geistMono.variable} marketing-blog font-geist`}>
      <MagazineArticle />
    </div>
  );
}
