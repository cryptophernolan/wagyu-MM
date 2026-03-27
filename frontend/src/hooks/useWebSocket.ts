"use client";
import { useEffect, useRef, useState } from "react";
import { useBotStore } from "@/store/botStore";
import type { WsEvent } from "@/types";

const WS_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/^http/, "ws") + "/ws";

export function useWebSocket(): { connectionState: string } {
  const [connectionState, setConnectionState] = useState("DISCONNECTED");
  const processWsEvent = useBotStore((s) => s.processWsEvent);
  const setConnected = useBotStore((s) => s.setConnected);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    function connect(): void {
      if (!mountedRef.current) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      setConnectionState("CONNECTING");

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnectionState("CONNECTED");
        setConnected(true);
        backoffRef.current = 1000;
      };

      ws.onmessage = (evt) => {
        if (!mountedRef.current) return;
        try {
          const event = JSON.parse(evt.data as string) as WsEvent;
          processWsEvent(event);
        } catch {
          // ignore malformed
        }
      };

      ws.onerror = () => {
        // handled in onclose
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnectionState("DISCONNECTED");
        setConnected(false);
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, 30000);
        setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
    };
  }, [processWsEvent, setConnected]);

  return { connectionState };
}
