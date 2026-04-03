"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_EVENTS = [
  {
    id: "CAL-001",
    date: "2026-04-03",
    title: "Database Index Rebuild",
    type: "maintenance",
    startTime: "02:00 UTC",
    endTime: "04:00 UTC",
    duration: "2h",
    team: "Database Team",
  },
  {
    id: "CAL-002",
    date: "2026-04-07",
    title: "API v3.0 Deployment",
    type: "deployment",
    startTime: "10:00 UTC",
    endTime: "11:00 UTC",
    duration: "1h",
    team: "Platform Team",
  },
  {
    id: "CAL-003",
    date: "2026-04-10",
    title: "Infrastructure Blackout — Audit Week",
    type: "blackout",
    startTime: "00:00 UTC",
    endTime: "23:59 UTC",
    duration: "All day",
    team: "SRE / Compliance",
  },
  {
    id: "CAL-004",
    date: "2026-04-14",
    title: "FaultRay Chaos Simulation — AZ Failure",
    type: "simulation",
    startTime: "14:00 UTC",
    endTime: "16:00 UTC",
    duration: "2h",
    team: "SRE",
  },
  {
    id: "CAL-005",
    date: "2026-04-21",
    title: "CDN Provider Migration",
    type: "maintenance",
    startTime: "22:00 UTC",
    endTime: "02:00 UTC+1",
    duration: "4h",
    team: "Infrastructure",
  },
  {
    id: "CAL-006",
    date: "2026-04-28",
    title: "FaultRay Chaos Simulation — DB Crash",
    type: "simulation",
    startTime: "14:00 UTC",
    endTime: "15:30 UTC",
    duration: "1.5h",
    team: "SRE",
  },
];

const TYPE_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  maintenance: { bg: "bg-blue-500/20", text: "text-blue-400", dot: "#3b82f6" },
  blackout: { bg: "bg-red-500/20", text: "text-red-400", dot: "#ef4444" },
  deployment: { bg: "bg-green-500/20", text: "text-green-400", dot: "#10b981" },
  simulation: { bg: "bg-[#FFD700]/20", text: "text-[#FFD700]", dot: "#FFD700" },
};

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number) {
  return new Date(year, month, 1).getDay();
}

export default function CalendarPage() {
  const locale = useLocale();
  const t = appDict.calendar[locale] ?? appDict.calendar.en;

  const today = new Date(2026, 3, 1); // April 2026 (month is 0-indexed)
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const daysInMonth = getDaysInMonth(viewYear, viewMonth);
  const firstDay = getFirstDayOfMonth(viewYear, viewMonth);

  const monthLabel = new Date(viewYear, viewMonth, 1).toLocaleString("en", { month: "long", year: "numeric" });

  const eventsForDate = (dateStr: string) =>
    DEMO_EVENTS.filter((e) => e.date === dateStr);

  const selectedEvents = selectedDate ? eventsForDate(selectedDate) : [];

  const prevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear((y) => y - 1); }
    else setViewMonth((m) => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear((y) => y + 1); }
    else setViewMonth((m) => m + 1);
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <CalendarDays size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 mb-6">
        {Object.entries(TYPE_COLORS).map(([type, colors]) => (
          <div key={type} className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.dot }} />
            <span className="text-xs text-[#94a3b8] capitalize">
              {t[type as keyof typeof t] ?? type}
            </span>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        {/* Calendar grid */}
        <Card className="md:col-span-2">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <button onClick={prevMonth} className="p-1.5 text-[#64748b] hover:text-white transition-colors">
              <ChevronLeft size={18} />
            </button>
            <p className="font-bold">{monthLabel}</p>
            <button onClick={nextMonth} className="p-1.5 text-[#64748b] hover:text-white transition-colors">
              <ChevronRight size={18} />
            </button>
          </div>

          {/* Day labels */}
          <div className="grid grid-cols-7 mb-2">
            {["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map((d) => (
              <div key={d} className="text-center text-xs text-[#475569] py-1">{d}</div>
            ))}
          </div>

          {/* Days */}
          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: firstDay }).map((_, i) => (
              <div key={`empty-${i}`} />
            ))}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const dateStr = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
              const dayEvents = eventsForDate(dateStr);
              const isToday = dateStr === "2026-04-01";
              const isSelected = dateStr === selectedDate;

              return (
                <button
                  key={day}
                  onClick={() => setSelectedDate(isSelected ? null : dateStr)}
                  className={`relative rounded-lg p-1 min-h-[52px] text-left transition-colors ${
                    isSelected
                      ? "bg-[#FFD700]/10 border border-[#FFD700]/50"
                      : isToday
                      ? "bg-white/5 border border-[#1e293b]"
                      : "hover:bg-white/3 border border-transparent"
                  }`}
                >
                  <span className={`text-xs font-mono ${isToday ? "text-[#FFD700] font-bold" : "text-[#94a3b8]"}`}>
                    {day}
                  </span>
                  <div className="mt-1 space-y-0.5">
                    {dayEvents.slice(0, 2).map((ev) => (
                      <div
                        key={ev.id}
                        className="w-full h-1.5 rounded-full"
                        style={{ backgroundColor: TYPE_COLORS[ev.type]?.dot ?? "#64748b" }}
                      />
                    ))}
                    {dayEvents.length > 2 && (
                      <p className="text-[10px] text-[#64748b]">+{dayEvents.length - 2}</p>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </Card>

        {/* Event details panel */}
        <div>
          <Card>
            <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.eventDetails}</p>
            {!selectedDate ? (
              <p className="text-sm text-[#64748b]">{t.clickForDetails}</p>
            ) : selectedEvents.length === 0 ? (
              <p className="text-sm text-[#64748b]">{t.noEvents}</p>
            ) : (
              <div className="space-y-4">
                {selectedEvents.map((ev) => {
                  const colors = TYPE_COLORS[ev.type] ?? { bg: "bg-white/5", text: "text-white", dot: "#64748b" };
                  return (
                    <div key={ev.id} className={`rounded-lg p-3 ${colors.bg}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant="default" className={colors.text}>
                          {t[ev.type as keyof typeof t] ?? ev.type}
                        </Badge>
                      </div>
                      <p className="font-semibold text-sm mb-2">{ev.title}</p>
                      <div className="space-y-1 text-xs text-[#94a3b8]">
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">{t.startTime}</span>
                          <span>{ev.startTime}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">{t.endTime}</span>
                          <span>{ev.endTime}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">{t.duration}</span>
                          <span>{ev.duration}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">{t.team}</span>
                          <span>{ev.team}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* Upcoming events list */}
          <Card className="mt-4">
            <p className="text-sm font-semibold text-[#FFD700] mb-3">{locale === "ja" ? "今後の予定" : "Upcoming"}</p>
            <div className="space-y-2">
              {DEMO_EVENTS.sort((a, b) => a.date.localeCompare(b.date)).map((ev) => {
                const colors = TYPE_COLORS[ev.type] ?? { dot: "#64748b" };
                return (
                  <div key={ev.id} className="flex items-center gap-2 text-sm">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: colors.dot }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs truncate">{ev.title}</p>
                      <p className="text-[10px] text-[#64748b]">{ev.date}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
