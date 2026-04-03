// MICRO-01: グローバルトースト通知フック
// 使い方: const { showToast, ToastContainer } = useToast();
"use client";

import { useState, useCallback } from "react";
import type { ToastVariant } from "@/components/ui/toast";

interface ToastState {
  id: number;
  message: string;
  variant: ToastVariant;
}

let _id = 0;

export function useToast() {
  const [toasts, setToasts] = useState<ToastState[]>([]);

  const showToast = useCallback((message: string, variant: ToastVariant = "success", durationMs = 3000) => {
    const id = ++_id;
    setToasts((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, durationMs);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { showToast, toasts, dismiss };
}
