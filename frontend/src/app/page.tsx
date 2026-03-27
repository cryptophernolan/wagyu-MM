"use client";
import { useState } from "react";
import { Header, type Tab } from "@/components/layout/Header";
import { StatusBar } from "@/components/layout/StatusBar";
import { StatsStrip } from "@/components/layout/StatsStrip";
import { OverviewTab } from "@/components/tabs/OverviewTab";
import { HealthTab } from "@/components/tabs/HealthTab";
import { FillsTab } from "@/components/tabs/FillsTab";
import { OrdersTab } from "@/components/tabs/OrdersTab";
import { ReportTab } from "@/components/tabs/ReportTab";
import { useWebSocket } from "@/hooks/useWebSocket";

export default function DashboardPage(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const { connectionState } = useWebSocket();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <StatusBar />
      <StatsStrip />
      <main>
        {activeTab === "Overview" && <OverviewTab />}
        {activeTab === "Health" && <HealthTab />}
        {activeTab === "Fills" && <FillsTab />}
        {activeTab === "Orders" && <OrdersTab />}
        {activeTab === "Report" && <ReportTab />}
      </main>
      {connectionState !== "CONNECTED" && (
        <div className="fixed bottom-4 right-4 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-xs text-zinc-400">
          WS: {connectionState}
        </div>
      )}
    </div>
  );
}
