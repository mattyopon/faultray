// SUSPENSE-01: グローバル loading.tsx — 全ルートのSuspense fallback
export default function GlobalLoading() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-8 h-8 border-2 border-[#FFD700] border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-[#64748b]">Loading…</p>
      </div>
    </div>
  );
}
