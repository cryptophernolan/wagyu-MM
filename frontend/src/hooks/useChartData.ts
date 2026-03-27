"use client";
import { useQuery } from "@tanstack/react-query";
import { fetchPriceChart, fetchPnLHistory, fetchBotVsHodl } from "@/lib/api";
import type { PricePoint, PnLPoint, BotVsHodlPoint } from "@/types";

export function usePriceChart(timeframe: string): { data: PricePoint[]; loading: boolean; error: boolean } {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["priceChart", timeframe],
    queryFn: () => fetchPriceChart(timeframe),
    refetchInterval: 5000,
  });
  return { data: data?.points ?? [], loading: isLoading, error: isError };
}

export function usePnLHistory(timeframe: string): { data: PnLPoint[]; loading: boolean; error: boolean } {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["pnlHistory", timeframe],
    queryFn: () => fetchPnLHistory(timeframe),
    refetchInterval: 5000,
  });
  return { data: data?.points ?? [], loading: isLoading, error: isError };
}

export function useBotVsHodlData(timeframe: string): { data: BotVsHodlPoint[]; loading: boolean; error: boolean } {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["botVsHodl", timeframe],
    queryFn: () => fetchBotVsHodl(timeframe),
    refetchInterval: 10000,
  });
  return { data: data?.points ?? [], loading: isLoading, error: isError };
}
