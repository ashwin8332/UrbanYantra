"use client";

import Link from "next/link";
import { Leaf, Satellite, Shield, Thermometer, Zap, Coins } from "lucide-react";
import type { CitySummary } from "@/types";

/* ── Heat status thresholds ─────────────────────────────────────────────── */
function lstStatus(lst: number) {
  if (lst >= 42) return { emoji: "🔴", label: "Extreme Heat", color: "text-red-400",    bar: "bg-red-500"    };
  if (lst >= 39) return { emoji: "🟠", label: "Severe Heat",  color: "text-orange-400", bar: "bg-orange-500" };
  if (lst >= 36) return { emoji: "🟡", label: "High Heat",    color: "text-yellow-400", bar: "bg-yellow-400" };
  if (lst >= 33) return { emoji: "🟡", label: "Warm",         color: "text-lime-400",   bar: "bg-lime-400"   };
  return              { emoji: "🟢", label: "Cool",           color: "text-green-400",  bar: "bg-green-400"  };
}
function resLabel(r: number) {
  if (r >= 70) return { label: "Good",           color: "text-green-400"  };
  if (r >= 45) return { label: "Fair",            color: "text-yellow-400" };
  return              { label: "Needs attention", color: "text-red-400"    };
}

interface HeaderProps {
  summary: CitySummary | null;
  scenarioMetrics?: {
    co2: number;
    investment: number;
    lst: number;
    utci: number;
  };
}

function MetricCard({
  icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: React.ReactNode;
  highlight?: string;
}) {
  return (
    <div className={`flex min-w-[148px] flex-1 items-start gap-2 rounded-lg border px-3 py-2 ${highlight ?? "border-slate-700/60 bg-slate-800/80"}`}>
      <div className="mt-0.5 text-cyan-400">{icon}</div>
      <div className="min-w-0">
        <div className="truncate text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
        <div className="text-sm font-bold text-white">{value}</div>
        {sub && <div className="mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

export default function Header({ summary, scenarioMetrics }: HeaderProps) {
  const m      = summary?.metrics;
  const lst    = scenarioMetrics?.lst    ?? m?.avg_city_lst_c           ?? 0;
  const utci   = scenarioMetrics?.utci   ?? m?.avg_heat_stress_utci_c   ?? 0;
  const res    = m?.resilience_index     ?? 0;
  const co2    = scenarioMetrics?.co2    ?? m?.co2_sequestration_tons_yr ?? 0;
  const invest = scenarioMetrics?.investment ?? m?.total_investment_m_usd ?? 0;

  const status  = lstStatus(lst);
  const resInfo = resLabel(res);
  const isSimulated = !!scenarioMetrics;

  return (
    <header className="border-b border-slate-700/60 bg-[#121826] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">

        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white overflow-hidden p-0.5">
            <img src="/logo.png" alt="UrbanYantra Logo" className="h-full w-full object-contain" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white">UrbanYantra</h1>
              <span className="rounded bg-cyan-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-cyan-300">ISRO-Grade</span>
              {isSimulated && (
                <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-emerald-300 animate-pulse">
                  SIMULATED
                </span>
              )}
            </div>
            <p className="text-[11px] uppercase tracking-wider text-slate-400">
              Urban Heat Mitigation &amp; Physics-Informed AI Platform
            </p>
          </div>
        </div>

        {/* Metrics */}
        <div className="flex flex-1 flex-wrap justify-end gap-2">
          {/* LST */}
          <MetricCard
            icon={<Thermometer size={18} />}
            label="Surface Temperature"
            value={`${lst.toFixed(1)}°C`}
            highlight={lst >= 39 ? "border-orange-700/60 bg-orange-950/30" : undefined}
            sub={
              <span className={`text-[10px] font-semibold ${status.color}`}>
                {status.emoji} {status.label}
              </span>
            }
          />

          {/* Heat stress */}
          <MetricCard
            icon={<Shield size={18} />}
            label="Heat Stress on People"
            value={`${utci.toFixed(1)}°C`}
            sub={
              <span className="text-[10px] text-slate-500">
                {utci >= 32 ? "⚠️ Uncomfortable outdoors" : "Tolerable conditions"}
              </span>
            }
          />

          {/* Resilience */}
          <MetricCard
            icon={<Zap size={18} />}
            label="City Resilience"
            value={`${res}/100`}
            sub={
              <div className="space-y-0.5">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-700">
                  <div className={`h-full rounded-full transition-all ${resInfo.color.replace("text-", "bg-")}`} style={{ width: `${res}%` }} />
                </div>
                <span className={`text-[10px] font-semibold ${resInfo.color}`}>{resInfo.label}</span>
              </div>
            }
          />

          {/* CO₂ */}
          <MetricCard
            icon={<Leaf size={18} />}
            label="CO₂ Saved"
            value={`${co2.toFixed(1)} t/yr`}
            sub={
              <span className="text-[10px] text-slate-500">
                {co2 > 0 ? `≈ ${Math.round(co2 / 21)} trees planted` : "Run simulator →"}
              </span>
            }
          />

          {/* Investment */}
          <MetricCard
            icon={<Coins size={18} />}
            label="Est. Investment"
            value={`$${invest.toFixed(2)}M`}
            sub={
              <span className="text-[10px] text-slate-500">
                {invest > 0 ? "Scenario cost estimate" : "Set sliders to plan"}
              </span>
            }
          />

          {/* Thermal Analytics Action */}
          <Link
            href="/thermal-analytics"
            className="flex min-w-[180px] items-center gap-2.5 rounded-lg border border-cyan-500/40 bg-gradient-to-r from-cyan-600/20 to-orange-500/15 px-4 py-2.5 transition-all hover:from-cyan-600/30 hover:to-orange-500/25 hover:border-cyan-400/60 hover:shadow-lg hover:shadow-cyan-500/10 group"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500/30 to-orange-500/20">
              <Satellite size={16} className="text-cyan-300" />
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-bold uppercase tracking-wide text-cyan-300 group-hover:text-cyan-200">
                Thermal Satellite Image Analytics
              </div>
              <div className="text-[10px] text-slate-400">AI-powered heat intelligence →</div>
            </div>
            <span className="ml-auto text-lg text-cyan-400 group-hover:text-cyan-300">+</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
