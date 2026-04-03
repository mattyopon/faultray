"use client";

import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  /** UICOMP-01: loading state — shows spinner aria-busy and disables interaction */
  loading?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading = false, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        // UICOMP-01: aria-busy for loading state, aria-disabled for disabled state
        aria-busy={loading || undefined}
        aria-disabled={disabled || loading || undefined}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all duration-200 whitespace-nowrap disabled:opacity-50 disabled:pointer-events-none",
          {
            "bg-[#FFD700] text-[#0a0e1a] hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] hover:-translate-y-0.5":
              variant === "primary",
            "bg-transparent text-white border border-[#1e293b] hover:border-[#64748b] hover:bg-white/[0.03] hover:-translate-y-0.5":
              variant === "secondary",
            "bg-transparent text-[#94a3b8] hover:text-white hover:bg-white/[0.05]":
              variant === "ghost",
            "bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20":
              variant === "danger",
          },
          {
            // MOBILE-01: min-h-[44px] on all sizes to meet WCAG 2.5.5 touch target (44×44px)
            "px-3 py-1.5 text-sm min-h-[44px]": size === "sm",
            "px-6 py-3 text-[0.9375rem] min-h-[44px]": size === "md",
            "px-8 py-4 text-base min-h-[44px]": size === "lg",
          },
          className
        )}
        {...props}
      >
        {loading ? (
          <>
            <svg
              className="animate-spin h-4 w-4 shrink-0"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span>{children}</span>
          </>
        ) : (
          children
        )}
      </button>
    );
  }
);

Button.displayName = "Button";

export { Button };
