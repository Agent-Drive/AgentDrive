import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { BlogIndex } from "../_components/blog/BlogIndex";
import "../_styles/blog.css";

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

export const metadata: Metadata = {
  title: "Blog — Agent Drive",
  description: "Thoughts, updates, and strategies on domain-specific data and AI agents.",
};

export default function BlogPage() {
  return (
    <div className={`${geistSans.variable} ${geistMono.variable} marketing-blog font-geist`}>
      <BlogIndex />
    </div>
  );
}
