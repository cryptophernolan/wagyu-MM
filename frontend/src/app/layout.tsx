import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/providers/QueryProvider";

export const metadata: Metadata = {
  title: "Wagyu MM Dashboard",
  description: "XMR1/USDC Market Maker Monitor",
};

export default function RootLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
