"use client";

import { useState, useEffect, useRef } from "react";
import { Wrench, ChevronDown, ChevronUp, Info } from "lucide-react";
import type { SimulationState } from "@/types";
import AITimeline from "@/components/AITimeline";

interface ScenarioResult {
  co2: number;
  investment: number;
  lst: number;
  utci: number;
}

interface CoolingSimulatorProps {
  wards: string[];
  state: SimulationState;
  onChange: (patch: Partial<SimulationState>) => void;
  onRun: () => void;
  onReset: () => void;
  running?: boolean;
  scenarioResult?: ScenarioResult | null;
  baselineLst?: number;
  // Extra rich data from ScenarioComparisonEntry
  carbonReductionPct?: number;
  heatStressReductionPct?: number;
  populationBenefited?: number;
  overallScore?: number;
  activeStepIndex?: number;
  onStepClick?: (factor: number, label: string) => void;
}

/* ── Inline tooltip ──────────────────────────────────────────────────────── */
function InfoTip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative ml-1 inline-block align-middle">
      <Info
        size={11}
        className="cursor-help text-slate-500 hover:text-slate-300 transition-colors"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
      />
      {show && (
        <div className="absolute left-4 top-0 z-50 w-52 rounded-lg border border-slate-600 bg-slate-900 p-2.5 text-[10px] leading-relaxed text-slate-300 shadow-2xl">
          {text}
        </div>
      )}
    </span>
  );
}

/* ── Slider row ──────────────────────────────────────────────────────────── */
function SliderRow({
  icon, label, tooltip, value, onChange, unit = "%", max = 100,
}: {
  icon: string; label: string; tooltip: string;
  value: number; onChange: (v: number) => void; unit?: string; max?: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center font-medium text-slate-200">
          <span className="mr-1.5 text-sm">{icon}</span>
          {label}
          <InfoTip text={tooltip} />
        </span>
        <span className="font-mono text-cyan-300">{value}{unit}</span>
      </div>
      <input
        type="range" min={0} max={max} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-400"
      />
      <div className="flex justify-between text-[10px] text-slate-600">
        <span>None</span><span>Full coverage</span>
      </div>
    </div>
  );
}

/* ── Animated count-up number ───────────────────────────────────────────── */
function CountUp({ to, decimals = 0, suffix = "" }: { to: number; decimals?: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  const frame = useRef<number>(0);
  useEffect(() => {
    const start = performance.now();
    const dur = 900;
    const tick = (now: number) => {
      const t = Math.min((now - start) / dur, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(to * eased);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [to]);
  return <>{val.toFixed(decimals)}{suffix}</>;
}

/* ── Circular score dial ─────────────────────────────────────────────────── */
function ScoreDial({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const color = clamped >= 80 ? "#22c55e" : clamped >= 60 ? "#84cc16" : clamped >= 40 ? "#eab308" : "#f97316";
  const bg = `conic-gradient(${color} ${clamped}%, #1e293b ${clamped}%)`;
  return (
    <div className="flex flex-col items-center justify-center">
      <div
        className="relative flex h-16 w-16 items-center justify-center rounded-full"
        style={{ background: bg, padding: 3 }}
      >
        <div className="flex h-full w-full items-center justify-center rounded-full bg-[#111827]">
          <span className="font-mono text-base font-black" style={{ color }}>
            <CountUp to={clamped} decimals={0} />
          </span>
        </div>
      </div>
      <span className="mt-1 text-[9px] font-semibold uppercase tracking-wider text-slate-400">Overall</span>
      <span className="text-[9px] text-slate-500">/100</span>
    </div>
  );
}

/* ── Metric pill ─────────────────────────────────────────────────────────── */
function MetricPill({
  icon, label, value, sub, color,
}: { icon: string; label: string; value: React.ReactNode; sub?: string; color: string }) {
  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-800/60 p-2.5 flex flex-col gap-0.5">
      <div className="flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider" style={{ color }}>
        <span>{icon}</span>
        <span className="truncate">{label}</span>
      </div>
      <div className="font-mono text-sm font-bold text-white leading-tight">{value}</div>
      {sub && <div className="text-[9px] text-slate-500 truncate">{sub}</div>}
    </div>
  );
}

/* ── Impact Summary Card (replaces old ResultCard) ───────────────────────── */
function ImpactSummaryCard({
  result, baseline,
  carbonReductionPct = 0,
  heatStressReductionPct = 0,
  populationBenefited = 0,
  overallScore = 0,
}: {
  result: ScenarioResult;
  baseline: number;
  carbonReductionPct?: number;
  heatStressReductionPct?: number;
  populationBenefited?: number;
  overallScore?: number;
}) {
  const delta = parseFloat((baseline - result.lst).toFixed(2));
  const score = overallScore || Math.round(Math.min(100, Math.max(0,
    (delta / 5) * 40 +
    (Math.min(carbonReductionPct, 50) / 50) * 20 +
    (Math.min(heatStressReductionPct, 60) / 60) * 20 +
    (Math.min(populationBenefited, 200000) / 200000) * 20
  )));
  const coolingIndex = Math.round(Math.min(100, (delta / 6) * 100));
  const pop = populationBenefited || Math.round(delta * 25000);
  const carbonPct = carbonReductionPct || parseFloat(((result.co2 / 120) * 100).toFixed(1));
  const hsPct = heatStressReductionPct || parseFloat(((baseline - result.utci) / baseline * 100 * 3).toFixed(1));

  const borderClass = score >= 70
    ? "border-emerald-600/50 shadow-emerald-500/10"
    : "border-cyan-700/40 shadow-cyan-500/10";

  return (
    <div className={`rounded-xl border p-3 shadow-lg ${borderClass} bg-gradient-to-b from-slate-900/90 to-slate-950/90`}>
      {/* Title row */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <p className="text-xs font-bold text-emerald-300">✅ Simulation Summary</p>
          <p className="text-[10px] text-slate-500">AI-powered intervention analysis</p>
        </div>
        <ScoreDial score={score} />
      </div>

      {/* Before → After temp strip */}
      <div className="mb-3 flex items-center justify-between rounded-lg bg-slate-800/70 px-3 py-2 gap-2">
        <div className="text-center">
          <p className="text-[9px] text-slate-500">Before</p>
          <p className="font-mono text-sm font-bold text-orange-400">{baseline.toFixed(1)}°C</p>
        </div>
        <div className="flex-1 flex flex-col items-center">
          <div className="h-px w-full bg-gradient-to-r from-orange-500 to-emerald-400" />
          <span className="mt-0.5 text-[9px] text-emerald-400 font-bold">−{delta.toFixed(2)}°C</span>
        </div>
        <div className="text-center">
          <p className="text-[9px] text-slate-500">After</p>
          <p className="font-mono text-sm font-bold text-cyan-300">{result.lst.toFixed(1)}°C</p>
        </div>
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-2 gap-1.5">
        <MetricPill
          icon="🌡️" label="Temperature" color="#f97316"
          value={<><CountUp to={delta} decimals={1} suffix="°C" /></>}
          sub="surface cooling"
        />
        <MetricPill
          icon="🌱" label="Carbon" color="#22c55e"
          value={<>↓<CountUp to={carbonPct} decimals={0} suffix="%" /></>}
          sub={`${result.co2.toFixed(1)} t/yr removed`}
        />
        <MetricPill
          icon="🥵" label="Heat Stress" color="#eab308"
          value={<>↓<CountUp to={Math.abs(hsPct)} decimals={0} suffix="%" /></>}
          sub="UTCI reduction"
        />
        <MetricPill
          icon="👥" label="Protected" color="#38bdf8"
          value={
            pop >= 1000
              ? <><CountUp to={pop / 1000} decimals={1} suffix="k" /></>
              : <><CountUp to={pop} decimals={0} /></>
          }
          sub="people benefited"
        />
        <MetricPill
          icon="❄️" label="Cooling Index" color="#818cf8"
          value={<>+<CountUp to={coolingIndex} decimals={0} suffix="%" /></>}
          sub="vs no intervention"
        />
        <MetricPill
          icon="💰" label="Investment" color="#94a3b8"
          value={<>${result.investment.toFixed(1)}M</>}
          sub="estimated cost"
        />
      </div>

      {/* Interpretation banner */}
      <p className={`mt-2 rounded-lg p-2 text-[10px] leading-relaxed ${
        delta >= 2.0 ? "bg-emerald-900/30 text-emerald-200"
        : delta >= 1.0 ? "bg-cyan-900/30 text-cyan-200"
        : "bg-slate-800 text-slate-400"}`}
      >
        {delta >= 2.0
          ? "🌟 Excellent! This plan would make the city significantly cooler and more liveable."
          : delta >= 1.0
          ? "✅ Good impact. Residents will notice improvements during peak summer."
          : delta >= 0.3
          ? "💡 Moderate — increase tree planting or cool-roof coverage to maximise impact."
          : "⚠️ Minimal effect. Combine multiple strategies and increase coverage."}
      </p>
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────────────────── */
export default function CoolingSimulator({
  wards, state, onChange, onRun, onReset, running,
  scenarioResult, baselineLst = 0,
  carbonReductionPct = 0,
  heatStressReductionPct = 0,
  populationBenefited = 0,
  overallScore = 0,
  activeStepIndex,
  onStepClick,
}: CoolingSimulatorProps) {
  const [advOpen, setAdvOpen] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);

  const liveEst = (
    (state.coolRoofs * 0.021) +
    (state.urbanGreening * 0.016) +
    (state.blueInfra * 0.03) +
    (state.greenRoofs * 0.012)
  );
  const hasChanges = state.coolRoofs > 0 || state.urbanGreening > 0 || state.blueInfra > 0 || state.greenRoofs > 0;
  const totalDelta = scenarioResult && baselineLst > 0
    ? parseFloat((baselineLst - scenarioResult.lst).toFixed(2))
    : 0;

  return (
    <aside className="flex w-[280px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-slate-700/60 bg-[#111827] p-4">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm font-bold text-white">
          <Wrench size={15} className="text-cyan-400" />
          Cooling Simulator
        </div>
        <p className="mt-1 text-[10px] leading-relaxed text-slate-400">
          Move the sliders to plan interventions, then hit <strong className="text-slate-200">Simulate</strong> to see the effect on the map.
        </p>
      </div>

      {/* Area selector */}
      <div>
        <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Target Area
        </label>
        <select
          value={state.targetWard}
          onChange={(e) => onChange({ targetWard: e.target.value })}
          className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500 transition-colors"
          suppressHydrationWarning
        >
          {wards.map((w) => (
            <option key={w} value={w}>
              {w === "Full City" ? "🏙️ Whole City" : `📍 ${w}`}
            </option>
          ))}
        </select>
      </div>

      {/* Live estimate banner */}
      {hasChanges && !scenarioResult && (
        <div className="rounded-lg border border-cyan-800/50 bg-cyan-950/30 px-3 py-2 text-[11px]">
          <span className="text-slate-400">Estimated cooling: </span>
          <span className="font-mono font-bold text-cyan-300">~{liveEst.toFixed(1)}°C</span>
          <span className="ml-1 text-slate-500">(rough estimate — hit Simulate for AI result)</span>
        </div>
      )}

      {/* Main sliders */}
      <div className="space-y-4">
        <SliderRow
          icon="🏠" label="Cool Roofs"
          tooltip="Paint rooftops white or install reflective coatings so they reflect sunlight instead of absorbing heat. Very cost-effective in dense urban areas. Even 30% coverage makes a measurable difference."
          value={state.coolRoofs} onChange={(v) => onChange({ coolRoofs: v })}
        />
        <SliderRow
          icon="🌳" label="Plant Trees"
          tooltip="Increase the share of tree canopy cover. Trees provide shade, release moisture, and can cool local temperatures by 1–3°C. Each mature tree can cool air equivalent to 10 room-sized air conditioners."
          value={state.urbanGreening} onChange={(v) => onChange({ urbanGreening: v })}
        />
        <SliderRow
          icon="💧" label="Water Features"
          tooltip="Add ponds, wetlands, or permeable surfaces. Water evaporation removes heat from the air — a natural air conditioner. Especially effective near high-density residential areas."
          value={state.blueInfra} onChange={(v) => onChange({ blueInfra: v })} max={50}
        />
      </div>

      {/* Advanced (collapsible) */}
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30">
        <button
          type="button"
          suppressHydrationWarning
          onClick={() => setAdvOpen((o) => !o)}
          className="flex w-full items-center justify-between px-3 py-2 text-left"
        >
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Advanced Options
          </span>
          {advOpen ? <ChevronUp size={12} className="text-slate-500" /> : <ChevronDown size={12} className="text-slate-500" />}
        </button>
        {advOpen && (
          <div className="space-y-4 px-3 pb-3">
            <SliderRow
              icon="🌿" label="Green Roofs"
              tooltip="Install plants and soil on flat rooftops. Heavier and more expensive than cool roofs, but also insulates the building from heat in summer and cold in winter."
              value={state.greenRoofs} onChange={(v) => onChange({ greenRoofs: v })}
            />
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center font-medium text-slate-200">
                  💰 Budget
                  <InfoTip text="Maximum budget in million USD available for interventions. The AI will optimise the cooling effect within this financial constraint." />
                </span>
                <span className="font-mono text-cyan-300">${state.budget.toFixed(1)}M</span>
              </div>
              <input
                type="range" min={0} max={20} step={0.5} value={state.budget}
                onChange={(e) => onChange({ budget: Number(e.target.value) })}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-400"
              />
              <div className="flex justify-between text-[10px] text-slate-600">
                <span>$0M</span><span>$20M</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Run button */}
      <button
        type="button"
        onClick={onRun}
        disabled={running}
        suppressHydrationWarning
        className="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-teal-500 py-3 text-sm font-bold text-slate-900 shadow-lg shadow-cyan-500/20 transition hover:brightness-110 active:scale-95 disabled:opacity-60"
      >
        {running ? "⏳ Simulating…" : "▶ Simulate Cooling Impact"}
      </button>

      {/* Impact Summary Card */}
      {scenarioResult && baselineLst > 0 && (
        <ImpactSummaryCard
          result={scenarioResult}
          baseline={baselineLst}
          carbonReductionPct={carbonReductionPct}
          heatStressReductionPct={heatStressReductionPct}
          populationBenefited={populationBenefited}
          overallScore={overallScore}
        />
      )}

      {/* AI Timeline toggle */}
      {scenarioResult && baselineLst > 0 && totalDelta > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowTimeline((s) => !s)}
            className="flex items-center justify-between w-full rounded-lg border border-indigo-700/40 bg-indigo-950/20 px-3 py-2 text-left transition hover:bg-indigo-950/30"
          >
            <span className="flex items-center gap-2 text-[11px] font-semibold text-indigo-300">
              🕒 AI Cooling Timeline
            </span>
            {showTimeline
              ? <ChevronUp size={12} className="text-indigo-400" />
              : <ChevronDown size={12} className="text-indigo-400" />}
          </button>
          {showTimeline && (
            <AITimeline
              baselineTemp={baselineLst}
              totalDelta={totalDelta}
              activeStepIndex={activeStepIndex}
              onStepClick={onStepClick}
            />
          )}
        </>
      )}

      <button
        type="button"
        onClick={onReset}
        suppressHydrationWarning
        className="text-center text-xs text-slate-500 underline underline-offset-2 hover:text-slate-300 transition-colors"
      >
        Reset all sliders
      </button>
    </aside>
  );
}
