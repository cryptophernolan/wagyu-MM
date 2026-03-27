"use client";
import { NotificationBell } from "@/components/ui/NotificationBell";

const TABS = ["Overview", "Health", "Fills", "Orders", "Report"] as const;
type Tab = (typeof TABS)[number];

interface Props {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
}

export function Header({ activeTab, onTabChange }: Props): React.JSX.Element {
  return (
    <div className="bg-zinc-900 border-b border-zinc-800 px-6 py-3">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-100">Wagyu MM Dashboard</h1>
          <p className="text-xs text-zinc-500">XMR1/USDC · Avellaneda-Stoikov</p>
        </div>
        <div className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => onTabChange(tab)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "text-zinc-100 border-b-2 border-orange-500"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab}
            </button>
          ))}
          <NotificationBell onNavigate={() => onTabChange("Health")} />
        </div>
      </div>
    </div>
  );
}

export type { Tab };
