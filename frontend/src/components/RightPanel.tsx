"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  CitySummary,
  ClimatePoint,
  CoolingStrategy,
  Driver,
  InterventionRanking,
} from "@/types";
import { DRIVER_COLORS } from "@/lib/colors";

interface RightPanelProps {
  cooling: CoolingStrategy[];
  drivers: Driver[];
  climate: ClimatePoint[];
  interventions?: InterventionRanking[];
  dataMode?: string;
  summary?: CitySummary | null;
  onOpenDataDetails?: () => void;
}

const INTERVENTION_LABELS: Record<string, string> = {
  cool_roof: "Cool Roof",
  urban_greening: "Urban Greening",
  blue_infrastructure: "Blue Infra",
};

const COMPLEXITY_CLASS: Record<string, string> = {
  low: "text-emerald-300",
  medium: "text-amber-300",
  high: "text-orange-300",
};

export default function RightPanel({
  cooling,
  drivers,
  climate,
  interventions = [],
  dataMode,
  summary,
  onOpenDataDetails,
}: RightPanelProps) {
  const driverData = drivers.map((d, i) => ({
    name: d.feature.replace(/\(.*\)/, "").trim().slice(0, 22),
    pct: Math.max(0, Math.min(100, d.importance_pct)),
    fill: DRIVER_COLORS[i % DRIVER_COLORS.length],
  }));
  const artifacts = summary?.artifacts_present ?? {};
  const presentCount = Object.values(artifacts).filter(Boolean).length;
  const totalCount = Object.keys(artifacts).length;
  const fetchErrors = summary?.fetch_errors ?? [];
  const dataHealthy = summary?.is_real_data === true;

  return (
    <aside className="flex w-[300px] shrink-0 flex-col gap-3 overflow-y-auto border-l border-slate-700/60 bg-[#151b28] p-3">
      <div
        className={`rounded-lg border p-3 ${
          dataHealthy
            ? "border-emerald-700/50 bg-emerald-950/20"
            : "border-red-700/50 bg-red-950/20"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-slate-100">Real Data Status</h3>
          <span
            className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${
              dataHealthy
                ? "bg-emerald-500/15 text-emerald-300"
                : "bg-red-500/15 text-red-300"
            }`}
          >
            {dataHealthy ? "Live outputs" : "Error fetching data"}
          </span>
        </div>
        <p className="mt-1 text-[10px] leading-snug text-slate-400">
          {dataHealthy
            ? "Real datasets are powering the map and model outputs."
            : fetchErrors.length > 0
              ? fetchErrors.slice(0, 2).join(" · ")
              : "One or more datasets failed to load. Re-run the pipeline with --force."}
        </p>
        <div className="mt-2 grid grid-cols-2 gap-1 text-[10px]">
          <div className="rounded bg-slate-900/50 px-2 py-1">
            <span className="block text-slate-500">Mode</span>
            <span className={`font-mono ${dataHealthy ? "text-emerald-300" : "text-red-300"}`}>
              {dataMode ?? summary?.data_mode ?? "unknown"}
            </span>
          </div>
          <div className="rounded bg-slate-900/50 px-2 py-1">
            <span className="block text-slate-500">Artifacts</span>
            <span className={`font-mono ${dataHealthy ? "text-emerald-300" : "text-red-300"}`}>
              {totalCount ? `${presentCount}/${totalCount}` : "loading"}
            </span>
          </div>
        </div>
        {onOpenDataDetails && (
          <button
            type="button"
            onClick={onOpenDataDetails}
            suppressHydrationWarning
            className="mt-2 w-full rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-200 transition-colors hover:bg-emerald-500/20"
          >
            Detail About Data
          </button>
        )}
      </div>

      {interventions.length > 0 && (
        <div className="rounded-lg border border-cyan-700/40 bg-cyan-950/15 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold text-slate-200">Ranked Interventions</h3>
            <span className="text-[9px] uppercase text-cyan-400/80">Top {interventions.length}</span>
          </div>
          <div className="max-h-52 space-y-1.5 overflow-y-auto pr-1">
            {interventions.slice(0, 12).map((row) => {
              const label = INTERVENTION_LABELS[row.intervention_type] ?? row.intervention_type;
              const complexity = (row.implementation_complexity ?? "medium").toLowerCase();
              return (
                <div
                  key={`${row.rank}-${row.intervention_type}-${row.target_row ?? row.lon}`}
                  className="rounded border border-slate-700/50 bg-slate-900/55 px-2 py-1.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-[11px] font-semibold text-white">
                        #{row.rank} · {label}
                      </p>
                      <p className="truncate text-[10px] text-slate-500">
                        {row.intervention_description ?? `${row.lat.toFixed(3)}°N, ${row.lon.toFixed(3)}°E`}
                      </p>
                    </div>
                    <span className="shrink-0 font-mono text-[11px] font-bold text-cyan-300">
                      −{row.estimated_temp_reduction_c.toFixed(2)}°C
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[9px]">
                    <span className={`font-semibold uppercase ${COMPLEXITY_CLASS[complexity] ?? "text-slate-400"}`}>
                      {complexity} effort
                    </span>
                    {row.cost_effectiveness_score != null && (
                      <span className="font-mono text-slate-500">
                        ROI {row.cost_effectiveness_score.toFixed(3)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-slate-700/60 bg-slate-800/50 p-3">
        <h3 className="mb-2 text-xs font-semibold text-slate-200">Cooling Potential by Strategy</h3>
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={cooling} layout="vertical" margin={{ left: 4, right: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 10 }} unit="°C" />
            <YAxis type="category" dataKey="strategy" width={72} tick={{ fill: "#94a3b8", fontSize: 9 }} />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #475569", fontSize: 11 }}
              formatter={(v) => [`${v ?? 0}°C cooling`, "ΔT"]}
            />
            <Bar dataKey="delta_t_c" radius={[0, 4, 4, 0]}>
              {cooling.map((_, i) => (
                <Cell key={i} fill={["#22d3ee", "#22c55e", "#3b82f6"][i % 3]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="rounded-lg border border-slate-700/60 bg-slate-800/50 p-3">
        <h3 className="mb-2 text-xs font-semibold text-slate-200">AI Hotspot Driver Explanation</h3>
        <div className="space-y-2">
          {driverData.map((d) => (
            <div key={d.name}>
              <div className="flex justify-between text-[10px] text-slate-400">
                <span className="truncate pr-2">{d.name}</span>
                <span>{d.pct}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-700">
                <div className="h-full rounded-full" style={{ width: `${d.pct}%`, background: d.fill }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-slate-700/60 bg-slate-800/50 p-3">
        <h3 className="mb-2 text-xs font-semibold text-slate-200">Climate Projection (2020 – 2050)</h3>
        <ResponsiveContainer width="100%" height={120}>
          <LineChart data={climate} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="year" tick={{ fill: "#94a3b8", fontSize: 9 }} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 9 }} domain={["auto", "auto"]} unit="°" />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #475569", fontSize: 11 }}
              formatter={(v) => [`${v ?? 0}°C`, "LST"]}
            />
            <Line type="monotone" dataKey="lst_c" stroke="#f97316" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </aside>
  );
}
