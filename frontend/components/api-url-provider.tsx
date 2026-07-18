"use client";

import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { DEFAULT_API_URL } from "@/lib/api";

const STORAGE_KEY = "forge-api-url";
const ApiUrlContext = createContext<{ apiUrl: string; setApiUrl: (value: string) => void } | null>(null);

export function ApiUrlProvider({ children }: { children: ReactNode }) {
  const [apiUrl, setApiUrlState] = useState(DEFAULT_API_URL);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) setApiUrlState(stored);
  }, []);

  const value = useMemo(() => ({
    apiUrl,
    setApiUrl: (value: string) => {
      const next = value.trim().replace(/\/+$/, "") || DEFAULT_API_URL;
      setApiUrlState(next);
      window.localStorage.setItem(STORAGE_KEY, next);
    },
  }), [apiUrl]);

  return <ApiUrlContext.Provider value={value}>{children}</ApiUrlContext.Provider>;
}

export function useApiUrl() {
  const value = useContext(ApiUrlContext);
  if (!value) throw new Error("useApiUrl must be used inside ApiUrlProvider");
  return value;
}
