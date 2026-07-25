"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Bot, Download, Send, Sparkles, User, X } from "lucide-react";
import { sendChat, downloadReport } from "@/lib/api";

interface AIChatProps {
  cityKey: string;
  cityName: string;
}

interface Message {
  id: string;
  sender: "user" | "ai";
  text: string;
}

const QUICK_PROMPTS = [
  { label: "Explain hotspots", prompt: "Explain the urban heat hotspots in this city. Which zones have the highest Land Surface Temperature and why? Give specific data and zones." },
  { label: "Top interventions", prompt: "What are the top 3 cooling interventions for this city ranked by impact? Provide expected temperature reduction, cost, and implementation timeline for each." },
  { label: "Climate projection", prompt: "What is the climate projection for this city over the next 20-30 years? How will urban heat island effects change by 2050?" },
  { label: "Planning recommendations", prompt: "Give me urban planning recommendations for reducing heat stress in this city. Focus on actionable strategies for city administrators." },
];


/* ── Render markdown-like formatting ────────────────────────────────────── */
function FormattedText({ text }: { text: string }) {
  const parts = text.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`|\n)/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (part === "\n") return <br key={i} />;
        if (part.startsWith("**") && part.endsWith("**"))
          return <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
        if (part.startsWith("*") && part.endsWith("*"))
          return <em key={i} className="italic text-slate-300">{part.slice(1, -1)}</em>;
        if (part.startsWith("`") && part.endsWith("`"))
          return <code key={i} className="rounded bg-slate-700/60 px-1 py-0.5 text-[10px] font-mono text-cyan-300">{part.slice(1, -1)}</code>;
        if (part.startsWith("• ") || part.startsWith("- "))
          return <span key={i} className="block pl-2 before:content-['•_'] before:text-violet-400">{part.slice(2)}</span>;
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

export default function AIChat({ cityKey, cityName }: AIChatProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "ai",
      text: `Hello! I'm the UrbanYantra AI Assistant for **${cityName}**.\n\nI can help with:\n• Heat hotspot analysis & LST data\n• SHAP driver explanations\n• Cooling intervention ROI\n• Urban planning recommendations\n• Generate PDF reports for stakeholders\n\nAsk me anything or try the quick prompts below!`,
    },
  ]);

  const bottomRef = useRef<HTMLDivElement>(null);

  /* scroll to latest message */
  useEffect(() => {
    if (isOpen) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isOpen]);

  /* reset conversation when city changes */
  useEffect(() => {
    setMessages([
      {
        id: "welcome",
        sender: "ai",
        text: `Hello! I'm the UrbanYantra AI Assistant for **${cityName}**.\n\nI can help with:\n• Heat hotspot analysis & LST data\n• SHAP driver explanations\n• Cooling intervention ROI\n• Urban planning recommendations\n• Generate PDF reports for stakeholders\n\nAsk me anything or try the quick prompts below!`,
      },
    ]);
  }, [cityKey, cityName]);

  /* Build conversation history for LLM context */
  const buildHistory = useCallback(() => {
    return messages
      .filter((m) => m.id !== "welcome")
      .slice(-10)
      .map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));
  }, [messages]);

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, sender: "user", text },
    ]);

    if (/generate\s+(pdf\s+)?report|download\s+(pdf\s+)?report/i.test(text)) {
      await handleDownloadReport();
      return;
    }

    setLoading(true);

    try {
      const history = buildHistory();
      const { reply } = await sendChat(cityKey, text, history);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, sender: "ai", text: reply },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: "ai",
          text: "⚠️ Backend unavailable. Make sure the API is running:\n`uvicorn backend.app.main:app --reload --port 8000`",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReport = async () => {
    setReportLoading(true);
    try {
      await downloadReport(cityKey);
      setMessages((prev) => [
        ...prev,
        {
          id: `report-${Date.now()}`,
          sender: "ai",
          text: `✅ **Report downloaded!**\n\nYour comprehensive PDF report for **${cityName}** has been saved. It includes:\n• Executive summary & key metrics\n• Ward-level heat analysis\n• AI model performance\n• Cooling intervention strategies\n• Urban planning recommendations`,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `report-err-${Date.now()}`,
          sender: "ai",
          text: "⚠️ Failed to generate report. Please ensure the API is running.",
        },
      ]);
    } finally {
      setReportLoading(false);
    }
  };

  /* ── Floating button ──────────────────────────────────────────────────── */
  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label="Open AI chat"
        className="fixed bottom-6 right-6 z-[9999] flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-pink-500 to-violet-600 text-white shadow-lg shadow-pink-500/30 transition-transform hover:scale-105"
      >
        <Sparkles size={20} />
      </button>
    );
  }

  /* ── Chat window ──────────────────────────────────────────────────────── */
  return (
    <div className="fixed bottom-6 right-6 z-[9999] flex w-80 sm:w-96 h-[540px] flex-col overflow-hidden rounded-2xl border border-slate-700 bg-[#111827] shadow-2xl">

      {/* header */}
      <div className="flex items-center justify-between border-b border-slate-700/60 bg-slate-900/80 px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-violet-400" />
          <div>
            <p className="text-sm font-semibold text-white">UrbanYantra AI</p>
            <p className="text-[10px] text-slate-400">LLM-Powered Analytics Agent</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleDownloadReport}
            disabled={reportLoading}
            title="Download PDF Report"
            className="rounded p-1.5 text-slate-400 hover:bg-slate-700/60 hover:text-emerald-400 transition-colors disabled:opacity-40"
          >
            <Download size={16} className={reportLoading ? "animate-bounce" : ""} />
          </button>
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="rounded p-1 text-slate-400 hover:text-white"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* messages */}
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm shadow ${msg.sender === "user"
                  ? "rounded-tr-sm bg-violet-600/40 text-white border border-violet-500/30"
                  : "rounded-tl-sm bg-slate-800 text-slate-200 border border-slate-700"
                }`}
            >
              {/* sender label */}
              <div className="mb-1 flex items-center gap-1.5 opacity-60">
                {msg.sender === "user"
                  ? <User size={11} />
                  : <Bot size={11} className="text-violet-400" />}
                <span className="text-[10px] font-semibold uppercase">
                  {msg.sender === "user" ? "You" : "AI Assistant"}
                </span>
              </div>
              <div className="leading-relaxed">
                <FormattedText text={msg.text} />
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-xl rounded-tl-sm border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-slate-400">
              <span className="inline-flex gap-1">
                <span className="animate-bounce [animation-delay:-0.3s]">·</span>
                <span className="animate-bounce [animation-delay:-0.15s]">·</span>
                <span className="animate-bounce">·</span>
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* quick prompts */}
      <div className="flex flex-wrap gap-1.5 border-t border-slate-700/40 bg-slate-900/40 px-3 py-2">
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => handleSend(item.prompt)}
            disabled={loading}
            className="rounded-full border border-slate-600/60 bg-slate-800/70 px-2.5 py-1 text-[10px] text-slate-300 transition-colors hover:border-violet-500/50 hover:bg-violet-600/20 hover:text-white disabled:opacity-40"
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* input */}
      <div className="border-t border-slate-700/60 bg-slate-900/60 p-3">
        <form
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about LST, ROI, planning, or say 'generate report'…"
            disabled={loading}
            className="flex-1 rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs text-white placeholder-slate-500 outline-none focus:border-violet-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="rounded-lg bg-violet-600 p-2 text-white transition-colors hover:bg-violet-500 disabled:opacity-40"
          >
            <Send size={15} />
          </button>
        </form>
      </div>
    </div>
  );
}
