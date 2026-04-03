"use client";

// UICOMP-07: Tooltip補助コンポーネント
import { useState, useRef, useEffect, useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
  delay?: number;
}

/**
 * アクセシブルなTooltipコンポーネント。
 * - マウスホバー + フォーカスでトリガー
 * - Escapeキーで閉じる
 * - aria-describedby でスクリーンリーダー対応
 */
export function Tooltip({ content, children, side = "top", className, delay = 300 }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reactId = useId();
  const id = `tooltip-${reactId.replace(/:/g, "")}`;

  function show() {
    timerRef.current = setTimeout(() => setVisible(true), delay);
  }

  function hide() {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
  }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setVisible(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const positionClass = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  }[side];

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {/* Wrap children with aria-describedby only when content is a string */}
      <span aria-describedby={typeof content === "string" ? id : undefined}>
        {children}
      </span>

      {visible && (
        <span
          id={id}
          role="tooltip"
          className={cn(
            "absolute z-[300] pointer-events-none whitespace-nowrap",
            "px-2.5 py-1.5 rounded-lg text-xs font-medium",
            "bg-[#1e293b] text-[#e2e8f0] border border-[#334155]",
            "shadow-lg",
            positionClass,
            className
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}
