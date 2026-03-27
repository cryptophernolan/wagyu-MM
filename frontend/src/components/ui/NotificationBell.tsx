"use client";
import { Bell } from "lucide-react";
import { useBotStore } from "@/store/botStore";

interface Props {
  onNavigate: () => void;
}

export function NotificationBell({ onNavigate }: Props): React.JSX.Element {
  const alerts = useBotStore((s) => s.alerts);
  const unread = alerts.length;

  return (
    <button onClick={onNavigate} className="relative p-2 text-zinc-400 hover:text-zinc-200 transition-colors">
      <Bell size={18} />
      {unread > 0 && (
        <span className="absolute top-0.5 right-0.5 bg-red-500 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center font-bold">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </button>
  );
}
