import { ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-black shadow-[0_8px_24px_rgba(249,115,22,.18)] hover:bg-accent-strong",
  secondary: "border border-line bg-panel-raised text-ink hover:border-white/20 hover:bg-white/[.07]",
  ghost: "text-muted hover:bg-white/[.06] hover:text-ink",
  danger: "border border-danger/20 bg-danger/10 text-danger hover:bg-danger/15",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }>(
  ({ className, variant = "secondary", size = "md", ...props }, ref) => (
    <button ref={ref} className={cn("inline-flex items-center justify-center gap-2 rounded-lg font-medium transition duration-200 disabled:cursor-not-allowed disabled:opacity-50", size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm", variants[variant], className)} {...props} />
  ),
);
Button.displayName = "Button";
