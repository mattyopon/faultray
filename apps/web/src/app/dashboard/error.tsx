"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/useLocale";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  const locale = useLocale();

  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <AlertTriangle size={48} className="text-red-400" />
      <h2 className="text-lg font-semibold">
        {locale === "ja" ? "エラーが発生しました" : "Something went wrong"}
      </h2>
      <p className="text-sm text-[#94a3b8]">
        {process.env.NODE_ENV === "development"
          ? error.message
          : locale === "ja"
          ? "予期しないエラーが発生しました。"
          : "An unexpected error occurred."}
      </p>
      {error.digest && (
        <p className="text-xs text-[#475569] font-mono">
          {locale === "ja" ? "エラーID:" : "Error ID:"} {error.digest}
        </p>
      )}
      <Button onClick={() => unstable_retry()}>
        {locale === "ja" ? "再試行" : "Try again"}
      </Button>
    </div>
  );
}
