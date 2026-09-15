import { MarketingChrome } from "../_components/MarketingChrome";
import { PricingTable } from "../_components/PricingTable";

export default function PricingPage() {
  return (
    <MarketingChrome>
      <main className="mx-auto max-w-5xl px-6 pb-24 pt-10">
        <PricingTable />
      </main>
    </MarketingChrome>
  );
}
