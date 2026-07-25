"use client";

import { useEffect, useState } from "react";

interface TimelineStep {
  label: string;
  months: number;
  factor: number; // fraction of total cooling achieved by this time
  description: string;
}

const STEPS: TimelineStep[] = [
  { label: "Month 0",   months: 0,   factor: 0.00, description: "Baseline — interventions just installed" },
  { label: "6 Months",  months: 6,   factor: 0.22, description: "Young trees & cool roofs begin reducing heat" },
  { label: "1 Year",    months: 12,  factor: 0.42, description: "Vegetation establishes, albedo effects stabilise" },
  { label: "3 Years",   months: 36,  factor: 0.72, description: "Tree canopy matures, maximum shading begins" },
  { label: "10 Years",  months: 120, factor: 1.00, description: "Full ecosystem cooling — urban forest effect" },
];

function tempColor(delta: number, maxDelta: number): string {
  const t = maxDelta > 0 ? delta / maxDelta : 0;
  if (t < 0.2) return "#f97316"; // orange — barely started
  if (t < 0.5) return "#eab308"; // yellow
  if (t < 0.75) return "#84cc16"; // lime
  return "#22c55e"; // green — fully cooled
}

function ScoreDot({ color, pulsing }: { color: string; pulsing?: boolean }) {
  return (
    <span
      className="relative inline-flex h-3 w-3 shrink-0 rounded-full"
      style={{ background: color }}
    >
      {pulsing && (
        <span
          className="absolute -inset-1 animate-ping rounded-full opacity-30"
          style={{ background: color }}
        />
      )}
    </span>
  );
}

interface AITimelineProps {
  baselineTemp: number;  // °C before sim
  totalDelta: number;    // total °C reduction from the simulation
  /** Called when user clicks a step — passes that step's cooling factor (0..1) */
  onStepClick?: (factor: number, label: string) => void;
  /** Index of the currently active step (controlled from outside) */
  activeStepIndex?: number;
}

export default function AITimeline({ baselineTemp, totalDelta, onStepClick, activeStepIndex }: AITimelineProps) {
  const [visible, setVisible] = useState<number[]>([]);

  // Stagger steps into view
  useEffect(() => {
    setVisible([]);
    const timers = STEPS.map((_, i) =>
      setTimeout(() => setVisible((v) => [...v, i]), i * 220)
    );
    return () => timers.forEach(clearTimeout);
  }, [baselineTemp, totalDelta]);

  const hasSimData = totalDelta > 0;

  return (
    <div className="rounded-xl border border-indigo-700/40 bg-indigo-950/20 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="text-base">🕒</span>
        <div>
          <p className="text-xs font-bold text-slate-100">AI Cooling Timeline</p>
          <p className="text-[10px] text-slate-400">
            {hasSimData
              ? "Click a milestone to preview the map at that point in time"
              : "Trees don't cool immediately — here's the science"}
          </p>
        </div>
      </div>

      {/* Steps */}
      <div className="relative">
        {/* Vertical connector line */}
        <div className="absolute left-[5px] top-3 bottom-3 w-px bg-gradient-to-b from-orange-500 via-yellow-400 to-emerald-400 opacity-40" />

        <div className="space-y-2 pl-5">
          {STEPS.map((step, i) => {
            const show = visible.includes(i);
            const temp = baselineTemp - totalDelta * step.factor;
            const color = tempColor(totalDelta * step.factor, totalDelta);
            const isLast = i === STEPS.length - 1;
            const isActive = activeStepIndex === i;
            const isClickable = hasSimData && onStepClick;

            return (
              <div
                key={step.label}
                className="relative transition-all duration-500"
                style={{
                  opacity: show ? 1 : 0,
                  transform: show ? "translateX(0)" : "translateX(-10px)",
                }}
              >
                {/* Dot on the line */}
                <span className="absolute -left-5 top-1">
                  <ScoreDot color={color} pulsing={isLast && show} />
                </span>

                <div
                  onClick={() => isClickable && onStepClick(step.factor, step.label)}
                  className={`rounded-lg border px-3 py-2 transition-all duration-200 ${
                    isActive
                      ? "border-cyan-400/70 bg-cyan-950/50 ring-1 ring-cyan-500/40 shadow-[0_0_12px_rgba(6,182,212,0.2)]"
                      : isLast
                      ? "border-emerald-500/40 bg-emerald-950/30"
                      : "border-slate-700/50 bg-slate-800/50"
                  } ${isClickable ? "cursor-pointer hover:border-cyan-500/50 hover:bg-slate-800/70 hover:scale-[1.01]" : ""}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color }}>
                          {step.label}
                        </span>
                        {isActive && (
                          <span className="rounded bg-cyan-500/20 px-1 py-0.5 text-[8px] font-bold uppercase tracking-wide text-cyan-300 border border-cyan-500/30">
                            Viewing
                          </span>
                        )}
                        {isClickable && !isActive && i > 0 && (
                          <span className="text-[8px] font-semibold text-cyan-300 bg-cyan-950/50 border border-cyan-800/40 px-1 py-0.5 rounded leading-none tracking-wide">
                            tap to preview
                          </span>
                        )}
                      </div>
                      {show && (
                        <p className="mt-0.5 text-[10px] leading-relaxed text-slate-300 whitespace-normal break-words">
                          {step.description}
                        </p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <span className="font-mono text-sm font-bold text-white">
                        {temp.toFixed(1)}°C
                      </span>
                      {i > 0 && (
                        <p className="text-[9px] font-mono" style={{ color }}>
                          −{(totalDelta * step.factor).toFixed(1)}°C
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Progress bar */}
                  {show && (
                    <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-700/60">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${step.factor * 100}%`,
                          background: `linear-gradient(90deg, #f97316, ${color})`,
                          transitionDelay: `${i * 100}ms`,
                        }}
                      />
                    </div>
                  )}
                </div>

                {/* Arrow connector */}
                {i < STEPS.length - 1 && show && (
                  <div className="flex justify-center py-0.5">
                    <span className="text-[10px] animate-bounce text-slate-600">↓</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer note */}
      {hasSimData ? (
        <p className="mt-3 rounded-lg bg-cyan-900/30 border border-cyan-800/40 px-3 py-2 text-[10px] leading-relaxed text-cyan-200">
          🗺️ Click any milestone above to update the 3D map and see how the city cools over time. Click <strong>Reset all sliders</strong> to return to the current baseline.
        </p>
      ) : (
        <p className="mt-3 rounded-lg bg-slate-900/65 px-3 py-2 text-[10px] leading-relaxed text-slate-400">
          📚 Based on urban forestry research: young trees cool by ~0.3–0.5°C/yr until canopy maturity at ~5–10 years.
          Cool roof albedo effects are immediate but plateau within months.
        </p>
      )}
    </div>
  );
}
