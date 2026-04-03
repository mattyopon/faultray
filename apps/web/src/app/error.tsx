"use client";

import { useEffect } from "react";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <p className="text-xs font-semibold text-[#FFD700] uppercase tracking-widest mb-4">
          FaultRay
        </p>
        <h1 className="text-4xl font-bold text-red-500 mb-4">
          Something went wrong
        </h1>
        <p className="text-[#94a3b8] mb-2 text-sm break-words">
          {error.message ?? "An unexpected error occurred."}
        </p>
        {error.digest && (
          <p className="text-[#475569] text-xs mb-8 font-mono">
            Error ID: {error.digest}
          </p>
        )}
        <button
          onClick={unstable_retry}
          className="inline-block px-6 py-3 bg-[#FFD700] text-black rounded-lg font-semibold hover:bg-yellow-400 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
