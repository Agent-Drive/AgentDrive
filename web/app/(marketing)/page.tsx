import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Landing } from "./_components/home/Landing";
import "./_styles/home.css";

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
  title: "Agent Drive — The ad intelligence layer",
  description: "Agent Drive builds datasets for humans and agents.",
};

export default function HomePage() {
  return (
    <div className={`${geistSans.variable} ${geistMono.variable} marketing-home font-geist`}>
      <Landing />
    </div>
  );
}
