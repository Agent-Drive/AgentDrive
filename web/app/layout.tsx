import type { Metadata } from "next";
import { Quattrocento, Source_Code_Pro, Work_Sans } from "next/font/google";
import { AuthKitProvider } from "@workos-inc/authkit-nextjs/components";
import "./globals.css";

const workSans = Work_Sans({
  variable: "--font-work-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const sourceCode = Source_Code_Pro({
  variable: "--font-source-code",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const quattrocento = Quattrocento({
  variable: "--font-quattrocento",
  subsets: ["latin"],
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "Agent Drive",
  description: "File intelligence for AI agents",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${workSans.variable} ${sourceCode.variable} ${quattrocento.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-paper text-ink">
        <AuthKitProvider>{children}</AuthKitProvider>
      </body>
    </html>
  );
}
