import type { Metadata } from "next";
import { Landing } from "@/components/marketing/Landing";
import "@/styles/marketing/home.css";

export const metadata: Metadata = {
  title: "Agent Drive — The ad intelligence layer",
  description: "Agent Drive builds datasets for humans and agents.",
};

export default function HomePage() {
  return (
    <div className="marketing-home">
      <Landing />
    </div>
  );
}
