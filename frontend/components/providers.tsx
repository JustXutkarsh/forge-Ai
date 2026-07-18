"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode, useState } from "react";

import { ApiUrlProvider } from "./api-url-provider";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false },
    },
  }));

  return (
    <QueryClientProvider client={queryClient}>
      <ApiUrlProvider>{children}</ApiUrlProvider>
    </QueryClientProvider>
  );
}
