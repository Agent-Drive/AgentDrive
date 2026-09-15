import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { MosaicPage } from "./_components/mosaic/MosaicPage";
import "./_components/mosaic/mosaic.css";

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
  title: "Mosaic — The ad intelligence layer",
  description: "Mosaic builds datasets for humans and agents.",
};

export default function HomePage() {
  return (
    <div className={`${geistSans.variable} ${geistMono.variable} mosaic-home font-geist`}>
      <MosaicPage />
    </div>
  );
}
