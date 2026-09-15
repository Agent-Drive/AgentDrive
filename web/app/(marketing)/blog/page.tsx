import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { MagazineArticle } from "../_components/blog/MagazineArticle";
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
  title: "Why we started with ads — Agent Drive",
  description:
    "Why Agent Drive started with ads: the case for domain-specific data over general-purpose models.",
};

export default function BlogPage() {
  return (
    <div className={`${geistSans.variable} ${geistMono.variable} marketing-blog font-geist`}>
      <MagazineArticle />
    </div>
  );
}
