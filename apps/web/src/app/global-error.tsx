"use client";

import { useEffect } from "react";

export default function GlobalError({
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
    <html lang="en">
      <body style={{ margin: 0, background: "#0a0e1a", fontFamily: "sans-serif" }}>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div style={{ textAlign: "center", maxWidth: 480, padding: "0 16px" }}>
            <p
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: "#FFD700",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                marginBottom: 16,
              }}
            >
              FaultRay
            </p>
            <h1
              style={{
                fontSize: 32,
                fontWeight: 700,
                color: "#ef4444",
                marginBottom: 16,
              }}
            >
              Critical error
            </h1>
            <p style={{ color: "#94a3b8", marginBottom: 8, fontSize: 14 }}>
              {error.message ?? "An unexpected error occurred."}
            </p>
            {error.digest && (
              <p
                style={{
                  color: "#475569",
                  fontSize: 11,
                  fontFamily: "monospace",
                  marginBottom: 32,
                }}
              >
                Error ID: {error.digest}
              </p>
            )}
            <button
              onClick={unstable_retry}
              style={{
                padding: "12px 28px",
                background: "#FFD700",
                color: "#0a0e1a",
                borderRadius: 8,
                fontWeight: 700,
                fontSize: 14,
                border: "none",
                cursor: "pointer",
              }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
