"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface CommandItem {
  href: string;
  label: string;
  group: string;
  icon: LucideIcon;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  items: CommandItem[];
}

export function CommandPalette({ open, onClose, items }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = query.trim() === ""
    ? items
    : items.filter((item) =>
        item.label.toLowerCase().includes(query.toLowerCase()) ||
        item.group.toLowerCase().includes(query.toLowerCase())
      );

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setQuery("");
      setActiveIndex(0);
      // Focus input after paint
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open]);

  // Keep active item visible
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-index="${activeIndex}"]`);
    if (el) {
      (el as HTMLElement).scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex]);

  const navigate = useCallback(
    (href: string) => {
      router.push(href);
      onClose();
    },
    [router, onClose]
  );

  // Keyboard handler for the modal
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((prev) =>
            filtered.length === 0 ? 0 : (prev + 1) % filtered.length
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((prev) =>
            filtered.length === 0
              ? 0
              : (prev - 1 + filtered.length) % filtered.length
          );
          break;
        case "Enter":
          e.preventDefault();
          if (filtered[activeIndex]) {
            navigate(filtered[activeIndex].href);
          }
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
        default:
          break;
      }
    },
    [filtered, activeIndex, navigate, onClose]
  );

  // Reset activeIndex when filtered results change
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveIndex(0);
  }, [query]);

  if (!open) return null;

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center pt-[15vh] px-4"
      onMouseDown={(e) => {
        // Close when clicking the backdrop (not the modal itself)
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      aria-modal="true"
      role="dialog"
      aria-label="Command palette"
    >
      {/* Dim overlay */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div
        className="relative w-full max-w-xl bg-[#0d1424] border border-[#1e293b] rounded-xl shadow-2xl overflow-hidden"
        onKeyDown={handleKeyDown}
      >
        {/* Search input row */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#1e293b]">
          <Search size={16} className="text-[#475569] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages..."
            className="flex-1 bg-transparent text-white placeholder-[#475569] text-sm outline-none"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="text-[#475569] hover:text-[#94a3b8] transition-colors"
              tabIndex={-1}
            >
              <X size={14} />
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-[#475569] border border-[#1e293b] rounded">
            ESC
          </kbd>
        </div>

        {/* Results list */}
        <div
          ref={listRef}
          className="max-h-[60vh] overflow-y-auto overscroll-contain py-2"
          role="listbox"
        >
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-[#475569]">
              No results for &ldquo;{query}&rdquo;
            </p>
          ) : (
            filtered.map((item, index) => {
              const Icon = item.icon;
              const isActive = index === activeIndex;
              return (
                <button
                  key={item.href}
                  data-index={index}
                  role="option"
                  aria-selected={isActive}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => navigate(item.href)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                    isActive
                      ? "bg-[#FFD700]/10 text-white"
                      : "text-[#94a3b8] hover:text-white hover:bg-white/5"
                  }`}
                >
                  <Icon
                    size={15}
                    className={`shrink-0 ${isActive ? "text-[#FFD700]" : "text-[#475569]"}`}
                  />
                  <span className="flex-1 text-sm truncate">{item.label}</span>
                  <span className="text-[10px] text-[#334155] uppercase tracking-wider hidden sm:block">
                    {item.group}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* Footer hint */}
        <div className="flex items-center gap-4 px-4 py-2 border-t border-[#1e293b] text-[10px] text-[#334155]">
          <span className="flex items-center gap-1">
            <kbd className="font-mono border border-[#1e293b] rounded px-1">↑</kbd>
            <kbd className="font-mono border border-[#1e293b] rounded px-1">↓</kbd>
            navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono border border-[#1e293b] rounded px-1">↵</kbd>
            open
          </span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono border border-[#1e293b] rounded px-1">ESC</kbd>
            close
          </span>
        </div>
      </div>
    </div>
  );
}
