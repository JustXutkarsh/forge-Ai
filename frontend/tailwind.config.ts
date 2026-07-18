import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--canvas))",
        panel: "hsl(var(--panel))",
        "panel-raised": "hsl(var(--panel-raised))",
        ink: "hsl(var(--ink))",
        muted: "hsl(var(--muted))",
        line: "hsl(var(--line))",
        accent: "hsl(var(--accent))",
        "accent-strong": "hsl(var(--accent-strong))",
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        danger: "hsl(var(--danger))",
      },
      boxShadow: {
        panel: "0 18px 50px rgba(0,0,0,.18)",
        glow: "0 0 0 1px rgba(249,115,22,.12), 0 12px 40px rgba(249,115,22,.08)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
