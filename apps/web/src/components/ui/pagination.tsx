"use client";

// TABLE-01: 全ページのページネーション欠如を解消する共通コンポーネント
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/lib/useLocale";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Pagination({ currentPage, totalPages, onPageChange, className }: PaginationProps) {
  const locale = useLocale();
  if (totalPages <= 1) return null;

  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  // Show max 7 page buttons with ellipsis for large sets
  const visiblePages = totalPages <= 7
    ? pages
    : currentPage <= 4
      ? [...pages.slice(0, 5), -1, totalPages]
      : currentPage >= totalPages - 3
        ? [1, -1, ...pages.slice(totalPages - 5)]
        : [1, -1, currentPage - 1, currentPage, currentPage + 1, -2, totalPages];

  return (
    <div className={cn("flex items-center justify-center gap-1 mt-6", className)} role="navigation" aria-label={locale === "ja" ? "ページネーション" : "Pagination"}>
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        aria-label={locale === "ja" ? "前のページ" : "Previous page"}
        className="p-2 rounded-lg text-[#64748b] hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft size={16} />
      </button>

      {visiblePages.map((page, i) =>
        page < 0 ? (
          <span key={`ellipsis-${i}`} className="px-2 text-[#475569]">…</span>
        ) : (
          <button
            key={page}
            onClick={() => onPageChange(page)}
            aria-label={locale === "ja" ? `${page}ページ` : `Page ${page}`}
            aria-current={page === currentPage ? "page" : undefined}
            className={cn(
              "min-w-[36px] h-9 px-2 rounded-lg text-sm transition-colors",
              page === currentPage
                ? "bg-[#FFD700] text-[#0a0e1a] font-bold"
                : "text-[#64748b] hover:text-white hover:bg-white/5"
            )}
          >
            {page}
          </button>
        )
      )}

      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        aria-label={locale === "ja" ? "次のページ" : "Next page"}
        className="p-2 rounded-lg text-[#64748b] hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

/** Hook to paginate an array client-side */
export function usePagination<T>(items: T[], pageSize = 20) {
  const [page, setPage] = useState(1);
  // Sanitize pageSize: 0 would make totalPages Infinity and slice bounds NaN;
  // negative / non-finite values produce nonsensical pagination. Floor FIRST so
  // a fractional value like 0.5 doesn't pass the >0 check and then floor to 0.
  const flooredPageSize = Number.isFinite(pageSize) ? Math.floor(pageSize) : 0;
  const safePageSize = flooredPageSize >= 1 ? flooredPageSize : 20;
  const totalPages = Math.max(1, Math.ceil(items.length / safePageSize));
  // Clamp the page used for slicing (and exposed to consumers) so a shrunk
  // list (filter/delete) never leaves the user on a blank page past the end of
  // the data. Reads always go through this clamped value, so an out-of-range
  // stored `page` is self-correcting without a state-syncing effect.
  const safePage = Math.min(Math.max(1, page), totalPages);
  const paginatedItems = items.slice((safePage - 1) * safePageSize, safePage * safePageSize);

  return { page: safePage, setPage, totalPages, paginatedItems };
}

// useState must be imported for the hook
import { useState } from "react";
