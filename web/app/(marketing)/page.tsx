import type { Metadata } from "next";
import { Landing } from "./_components/home/Landing";
import "./_styles/home.css";

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
