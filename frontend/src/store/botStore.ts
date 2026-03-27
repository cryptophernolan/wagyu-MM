"use client";
import { create } from "zustand";
import type { BotStatus, Fill, Order, WsEvent } from "@/types";

interface BotStore {
  status: BotStatus | null;
  recentFills: Fill[];
  openOrders: Order[];
  alerts: string[];
  connected: boolean;
  setStatus: (status: BotStatus) => void;
  addFill: (fill: Fill) => void;
  setOrders: (orders: Order[]) => void;
  addAlert: (msg: string) => void;
  setConnected: (v: boolean) => void;
  processWsEvent: (event: WsEvent) => void;
}

export const useBotStore = create<BotStore>((set, get) => ({
  status: null,
  recentFills: [],
  openOrders: [],
  alerts: [],
  connected: false,

  setStatus: (status) => set({ status }),
  addFill: (fill) =>
    set((s) => ({ recentFills: [fill, ...s.recentFills].slice(0, 100) })),
  setOrders: (orders) => set({ openOrders: orders }),
  addAlert: (msg) =>
    set((s) => ({ alerts: [msg, ...s.alerts].slice(0, 50) })),
  setConnected: (v) => set({ connected: v }),

  processWsEvent: (event) => {
    const store = get();
    switch (event.type) {
      case "state_update":
        set({ status: event.data });
        break;
      case "fill_event":
        store.addAlert(`Fill: ${event.data.side.toUpperCase()} ${event.data.size} @ $${event.data.price}`);
        break;
      case "alert_event":
        store.addAlert(event.data.message);
        break;
      default:
        break;
    }
  },
}));
