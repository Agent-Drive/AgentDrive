export type BlogPost = {
  slug: string;
  href: string;
  date: string;
  dateLabel: string;
  title: string;
  category: string;
  kind: "blog" | "changelog";
  author: string;
  readMinutes: number;
  excerpt?: string;
};

export const FEATURED_SLUG = "why-we-started-with-ads";

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: FEATURED_SLUG,
    href: `/blog/${FEATURED_SLUG}`,
    date: "Jun 2025",
    dateLabel: "June 12, 2025",
    title: "Why we started with ads: the case for domain-specific data",
    category: "Blog",
    kind: "blog",
    author: "Sarah Chen",
    readMinutes: 8,
    excerpt:
      "Why Agent Drive started with ads: the case for domain-specific data over general-purpose models.",
  },
  {
    slug: "ads-dataset-schema-v2",
    href: "/#blog",
    date: "May 2025",
    dateLabel: "May 10, 2025",
    title: "Introducing the v2.0 Ads Dataset Schema",
    category: "Changelog",
    kind: "changelog",
    author: "David Kim",
    readMinutes: 6,
  },
  {
    slug: "ad-creative-tokenizer",
    href: "/#blog",
    date: "Apr 2025",
    dateLabel: "April 22, 2025",
    title: "Why we built our own tokenizer for ad creative",
    category: "Blog",
    kind: "blog",
    author: "Alex Rivera",
    readMinutes: 6,
  },
  {
    slug: "structured-ad-corpora",
    href: "/#blog",
    date: "Mar 2025",
    dateLabel: "March 18, 2025",
    title: "How AI agents use structured ad corpora for better copy generation",
    category: "Blog",
    kind: "blog",
    author: "Maya Patel",
    readMinutes: 5,
  },
  {
    slug: "ads-public-beta",
    href: "/#blog",
    date: "Feb 2025",
    dateLabel: "February 4, 2025",
    title: "Agent Drive Ads: public beta now open",
    category: "Changelog",
    kind: "changelog",
    author: "Jordan Lee",
    readMinutes: 3,
  },
];

export function getFeaturedPost(): BlogPost {
  const post = BLOG_POSTS.find((item) => item.slug === FEATURED_SLUG);
  if (!post) {
    throw new Error(`Missing featured post: ${FEATURED_SLUG}`);
  }
  return post;
}

export function getListingPosts(): BlogPost[] {
  return BLOG_POSTS.filter((item) => item.slug !== FEATURED_SLUG);
}
