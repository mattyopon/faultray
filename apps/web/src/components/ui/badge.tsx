import { cn } from "@/lib/utils";
import { type HTMLAttributes } from "react";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "green" | "red" | "yellow" | "gold";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full",
        {
          "bg-black/10 text-[var(--text-secondary)]": variant === "default",
          "bg-emerald-500/10 text-emerald-400": variant === "green",
          "bg-red-500/10 text-red-400": variant === "red",
          "bg-yellow-500/10 text-yellow-400": variant === "yellow",
          "bg-[var(--gold)]/10 text-[var(--gold)]": variant === "gold",
        },
        className
      )}
      {...props}
    />
  );
}
