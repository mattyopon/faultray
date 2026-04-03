"use client";

import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, XCircle, Info } from "lucide-react";

// ERRMSG-05: Toast with proper visual hierarchy — success/warning/error are visually distinct

export type ToastVariant = "success" | "warning" | "error" | "info";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastProps {
  message: string;
  variant?: ToastVariant;
  className?: string;
  // NOTIFY-05: アクション付きトースト（Undo/Retry等）
  action?: ToastAction;
  onDismiss?: () => void;
}

const variantConfig: Record<ToastVariant, {
  bg: string;
  border: string;
  text: string;
  Icon: React.ElementType;
  role: "status" | "alert";
}> = {
  success: {
    bg: "bg-emerald-600",
    border: "border-emerald-500",
    text: "text-white",
    Icon: CheckCircle2,
    role: "status",
  },
  warning: {
    bg: "bg-amber-500",
    border: "border-amber-400",
    text: "text-[#0a0e1a]",
    Icon: AlertTriangle,
    role: "status",
  },
  error: {
    bg: "bg-red-600",
    border: "border-red-500",
    text: "text-white",
    Icon: XCircle,
    role: "alert",
  },
  info: {
    bg: "bg-blue-600",
    border: "border-blue-500",
    text: "text-white",
    Icon: Info,
    role: "status",
  },
};

export function Toast({ message, variant = "success", className, action, onDismiss }: ToastProps) {
  const cfg = variantConfig[variant];
  return (
    <div
      role={cfg.role}
      aria-live={cfg.role === "alert" ? "assertive" : "polite"}
      className={cn(
        // NOTIFY-06: モバイルでは bottom-4 left-4 right-4（full-width）でトーストが切れないように
        // デスクトップでは right-4 top-4 に固定
        "fixed z-[100] flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium shadow-lg border",
        "bottom-4 left-4 right-4 sm:bottom-auto sm:top-4 sm:left-auto sm:right-4 sm:max-w-sm",
        cfg.bg,
        cfg.border,
        cfg.text,
        className
      )}
    >
      <cfg.Icon size={15} className="shrink-0" aria-hidden="true" />
      <span className="flex-1">{message}</span>
      {/* NOTIFY-05: アクション付きトースト */}
      {action && (
        <button
          onClick={action.onClick}
          className="ml-2 text-xs font-bold underline underline-offset-2 hover:opacity-75 transition-opacity whitespace-nowrap"
        >
          {action.label}
        </button>
      )}
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className="ml-2 hover:opacity-75 transition-opacity leading-none text-base"
        >
          &times;
        </button>
      )}
    </div>
  );
}
