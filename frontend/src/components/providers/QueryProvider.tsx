"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 2000 } } }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
