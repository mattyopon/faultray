"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Bot, Send, Loader2, User } from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  actions?: Array<{ label: string; href: string }>;
}

const SUGGESTIONS = [
  "How can I improve my resilience score?",
  "What is FaultRay?",
  "Explain the availability model",
  "How should I configure replicas?",
  "What is a circuit breaker pattern?",
  "How does failover work?",
];

export default function AdvisorPage() {
  const locale = useLocale();
  const ta = locale === "ja" ? appDict.advisor.ja : appDict.advisor.en;
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: ta.greeting,
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text?: string) => {
    const message = text || input;
    if (!message.trim() || loading) return;

    const userMsg: Message = { role: "user", content: message };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.chat(message);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          sources: res.sources,
          actions: res.suggested_actions,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: ta.fallback,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="max-w-[900px] mx-auto px-6 py-10 flex flex-col" style={{ height: "calc(100vh - 64px)" }}>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Bot size={24} className="text-[#FFD700]" />
          {ta.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {ta.subtitle}
        </p>
      </div>

      {/* Chat Messages */}
      <Card className="flex-1 overflow-y-auto mb-4 p-4">
        <div className="space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
              {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-lg bg-[#FFD700]/10 flex items-center justify-center shrink-0">
                  <Bot size={16} className="text-[#FFD700]" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-xl p-4 ${
                  msg.role === "user"
                    ? "bg-[#FFD700]/10 text-[#e2e8f0]"
                    : "bg-white/[0.03] border border-[#1e293b]"
                }`}
              >
                <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                {msg.actions && msg.actions.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-[#1e293b]">
                    {msg.actions.map((action) => (
                      <Link key={action.href} href={action.href}>
                        <Button variant="secondary" size="sm">
                          {action.label}
                        </Button>
                      </Link>
                    ))}
                  </div>
                )}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 text-xs text-[#64748b]">
                    Sources: {msg.sources.join(", ")}
                  </div>
                )}
              </div>
              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0">
                  <User size={16} className="text-blue-400" />
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-[#FFD700]/10 flex items-center justify-center shrink-0">
                <Bot size={16} className="text-[#FFD700]" />
              </div>
              <div className="bg-white/[0.03] border border-[#1e293b] rounded-xl p-4">
                <Loader2 size={16} className="animate-spin text-[#FFD700]" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </Card>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              className="px-3 py-1.5 rounded-full text-xs border border-[#1e293b] text-[#94a3b8] hover:border-[#FFD700]/30 hover:text-[#FFD700] transition-all"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage();
        }}
        className="flex gap-3"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={ta.placeholder}
          className="flex-1 px-4 py-3 bg-[#0d1117] border border-[#1e293b] rounded-xl text-sm text-[#e2e8f0] placeholder-[#3a4558] focus:border-[#FFD700]/50 focus:outline-none"
          disabled={loading}
        />
        <Button type="submit" disabled={!input.trim() || loading}>
          <Send size={16} />
        </Button>
      </form>
    </div>
  );
}
