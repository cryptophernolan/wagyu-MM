"use client";
import { PortfolioPanel } from "@/components/panels/PortfolioPanel";
import { PnLPanel } from "@/components/panels/PnLPanel";
import { PositionPanel } from "@/components/panels/PositionPanel";
import { PriceChart } from "@/components/charts/PriceChart";
import { PnLChart } from "@/components/charts/PnLChart";
import { BotVsHodlChart } from "@/components/charts/BotVsHodlChart";

export function OverviewTab(): React.JSX.Element {
  return (
    <div className="p-4 space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <PortfolioPanel />
        <PnLPanel />
        <PositionPanel />
      </div>
      <PriceChart />
      <div className="grid grid-cols-2 gap-4">
        <PnLChart />
        <BotVsHodlChart />
      </div>
    </div>
  );
}
