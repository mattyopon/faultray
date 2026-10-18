// MICRO-01: グローバルトースト通知フック
// 使い方: const { showToast, ToastContainer } = useToast();
"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { ToastVariant } from "@/components/ui/toast";

interface ToastState {
  id: number;
  message: string;
  variant: ToastVariant;
}

export function useToast() {
  const [toasts, setToasts] = useState<ToastState[]>([]);
  // Per-hook id counter (not module-global) so ids can't collide across
  // independent toast lists or be reset/duplicated by HMR.
  const nextIdRef = useRef(0);
  // Track pending auto-dismiss timers so they can be cancelled on manual
  // dismiss and cleared on unmount (otherwise a fired timer calls setState on
  // an unmounted component, and dismissed toasts leave orphaned timers).
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const clearTimer = useCallback((id: number) => {
    const t = timersRef.current.get(id);
    if (t !== undefined) {
      clearTimeout(t);
      timersRef.current.delete(id);
    }
  }, []);

  const dismiss = useCallback((id: number) => {
    clearTimer(id);
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, [clearTimer]);

  const showToast = useCallback((message: string, variant: ToastVariant = "success", durationMs = 5000) => {
    const id = ++nextIdRef.current;
    setToasts((prev) => [...prev, { id, message, variant }]);
    const timer = setTimeout(() => {
      timersRef.current.delete(id);
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, durationMs);
    timersRef.current.set(id, timer);
  }, []);

  // Cancel any outstanding timers when the consuming component unmounts.
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  return { showToast, toasts, dismiss };
}
