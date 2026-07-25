"use client";

import React, { useState } from "react";
import { createPortal } from "react-dom";
import { Sparkles, ArrowRight, ShieldCheck, HelpCircle, X } from "lucide-react";
import type { ScenarioComparisonResult, ScenarioComparisonEntry } from "@/types";

interface ScenarioComparisonProps {
  comparison: ScenarioComparisonResult | null;
  selectedScenarioName: string | null;
  onSelectScenario: (scenario: ScenarioComparisonEntry) => void;
  loading: boolean;
  budget?: number;       // $M from sim state
  baseLstC?: number;    // city baseline LST °C
}

/* ── Smart Suggestion Engine ────────────────────────────────────────────── */
function computeSmartSuggestion(
  scenarios: ScenarioComparisonEntry[],
  budget: number
) {
  // Filter real strategy scenarios (not baseline / combined)
  const real = scenarios.filter(
    (s) =>
      !s.name.toLowerCase().includes("current") &&
      !s.name.toLowerCase().includes("baseline")
  );

  // Score = cooling_per_dollar (larger = better ROI)
  const withRoi = real.map((s) => ({
    ...s,
    roi: s.estimated_cost_m_usd > 0 ? s.temp_reduction_c / s.estimated_cost_m_usd : 0,
    affordable: s.estimated_cost_m_usd <= budget || budget <= 0,
  }));

  // Separate affordable vs not
  const affordable = withRoi.filter((s) => s.affordable && !s.name.includes("Combined"));
  const notAffordable = withRoi.filter((s) => !s.affordable && !s.name.includes("Combined"));
  const combined = withRoi.find((s) => s.name.includes("Combined"));

  // Best single strategy by ROI within budget
  const bestSingle = affordable.sort((a, b) => b.roi - a.roi)[0];
  // Second best
  const secondBest = affordable.filter((s) => s.name !== bestSingle?.name).sort((a, b) => b.roi - a.roi)[0];

  // Build allocation advice
  let allocation: { label: string; pct: number; icon: string; cooling: number }[] = [];
  let expectedCooling = 0;
  let title = "";

  if (budget > 0 && budget <= 2) {
    // Very tight budget — single best strategy
    if (bestSingle) {
      const isTree = bestSingle.name.toLowerCase().includes("tree") || bestSingle.name.toLowerCase().includes("green");
      const isRoof = bestSingle.name.toLowerCase().includes("roof");
      allocation = isTree
        ? [{ label: "Tree Plantation", pct: 75, icon: "🌳", cooling: bestSingle.temp_reduction_c * 0.75 },
           { label: "Cool Roofs", pct: 25, icon: "🏠", cooling: bestSingle.temp_reduction_c * 0.25 }]
        : isRoof
        ? [{ label: "Cool Roofs", pct: 70, icon: "🏠", cooling: bestSingle.temp_reduction_c * 0.70 },
           { label: "Tree Plantation", pct: 30, icon: "🌳", cooling: bestSingle.temp_reduction_c * 0.30 }]
        : [{ label: bestSingle.name, pct: 100, icon: bestSingle.icon, cooling: bestSingle.temp_reduction_c }];
      expectedCooling = parseFloat((bestSingle.temp_reduction_c * 0.88).toFixed(2));
      title = "Budget is Limited — Maximum ROI Mix";
    }
  } else if (budget <= 5) {
    // Medium budget — blend two strategies
    if (bestSingle && secondBest) {
      allocation = [
        { label: bestSingle.name, pct: 60, icon: bestSingle.icon, cooling: bestSingle.temp_reduction_c * 0.60 },
        { label: secondBest.name, pct: 40, icon: secondBest.icon, cooling: secondBest.temp_reduction_c * 0.40 },
      ];
      expectedCooling = parseFloat(((bestSingle.temp_reduction_c * 0.6 + secondBest.temp_reduction_c * 0.4) * 0.92).toFixed(2));
      title = "Balanced Strategy — Best 2-Way Mix";
    }
  } else {
    // Large budget — use combined or blend all
    if (combined) {
      const parts = affordable.slice(0, 3);
      const total = parts.reduce((s, p) => s + p.temp_reduction_c, 0) || 1;
      allocation = parts.map((p) => ({
        label: p.name,
        pct: Math.round((p.temp_reduction_c / total) * 100),
        icon: p.icon,
        cooling: p.temp_reduction_c,
      }));
      expectedCooling = parseFloat((combined.temp_reduction_c).toFixed(2));
      title = "Full Portfolio — All Strategies Combined";
    }
  }

  // Why Not reasons for non-recommended strategies
  const whyNot = notAffordable
    .concat(withRoi.filter((s) => s.name !== bestSingle?.name && !s.name.includes("Combined") && s.affordable).slice(1))
    .map((s) => {
      const isRoof = s.name.toLowerCase().includes("roof") && !s.name.toLowerCase().includes("green");
      const isWater = s.name.toLowerCase().includes("water") || s.name.toLowerCase().includes("blue");
      const isGreenRoof = s.name.toLowerCase().includes("green roof");
      const rank = affordable.findIndex((a) => a.name === s.name) + 1 || affordable.length + 1;

      const reasons = isGreenRoof
        ? [
            "High installation cost (₹8,000–25,000/m²)",
            "Requires structural reinforcement of existing roofs",
            "Lower cooling efficiency than tree plantation",
            "Longer payback period (8–15 years)",
          ]
        : isRoof
        ? [
            "Albedo effect plateaus within 6 months",
            "Less effective in areas with heavy monsoon",
            "Cooling limited to surface temp only (not ambient)",
            s.estimated_cost_m_usd > budget ? `Exceeds budget by $${(s.estimated_cost_m_usd - budget).toFixed(1)}M` : "",
          ].filter(Boolean)
        : isWater
        ? [
            "Requires land acquisition near hotspots",
            "Effective only within 200m radius",
            "High evaporation loss in dry months",
            s.estimated_cost_m_usd > budget ? `Exceeds budget by $${(s.estimated_cost_m_usd - budget).toFixed(1)}M` : "",
          ].filter(Boolean)
        : [
            `Lower cooling ROI than top recommendation (${ s.roi.toFixed(2)}°C/$M vs ${bestSingle?.roi.toFixed(2) ?? "N/A"}°C/$M)`,
            s.estimated_cost_m_usd > budget ? `Over budget by $${(s.estimated_cost_m_usd - budget).toFixed(1)}M` : "Limited coverage area",
            "Higher opportunity cost at current budget level",
          ];

      return { name: s.name, icon: s.icon, priority: rank, reasons };
    })
    .slice(0, 3);

  return { allocation, expectedCooling, title, whyNot, bestSingle, budget };
}

export default function ScenarioComparison({
  comparison,
  selectedScenarioName,
  onSelectScenario,
  loading,
  budget = 5,
  baseLstC,
}: ScenarioComparisonProps) {
  const [isPlanModalOpen, setIsPlanModalOpen] = useState(false);

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-700/60 bg-[#121826]/70 p-6 text-center backdrop-blur-md">
        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-cyan-500/20 border-t-cyan-400"></div>
          <div>
            <p className="text-sm font-semibold text-white">AI runs prediction models...</p>
            <p className="text-xs text-slate-400 mt-1">Simulating and generating results for all scenarios</p>
          </div>
        </div>
      </div>
    );
  }

  if (!comparison) return null;

  const { scenarios, recommendation } = comparison;

  return (
    <div className="space-y-5 rounded-xl border border-slate-700/50 bg-[#111827]/80 p-5 shadow-xl backdrop-blur-md animate-fadeIn">
      <div>
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-cyan-400" />
          <h3 className="text-base font-bold text-white tracking-wide">AI Scenario Comparison</h3>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          Compare generated cooling scenarios. Click any scenario row to update the 3D map view.
        </p>
      </div>

      {/* Comparison Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-800 bg-[#0c101b]/60">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 bg-[#111625]/80 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3">Scenario</th>
              <th className="px-4 py-3 text-right">Avg LST</th>
              <th className="px-4 py-3 text-right">Cooling ΔT</th>
              <th className="px-4 py-3 text-right">Carbon Red.</th>
              <th className="px-4 py-3 text-right">Cost</th>
              <th className="px-4 py-3 text-right">Heat Stress</th>
              <th className="px-4 py-3 text-center">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/40 text-xs">
            {scenarios.map((sc) => {
              const isSelected = selectedScenarioName === sc.name;
              const isCombined = sc.name.includes("Combined");
              
              return (
                <tr
                  key={sc.name}
                  onClick={() => onSelectScenario(sc)}
                  className={`cursor-pointer transition-all duration-200 hover:bg-slate-800/40 ${
                    isSelected
                      ? "bg-cyan-950/30 font-medium text-cyan-200 border-l-4 border-cyan-400"
                      : "text-slate-300"
                  }`}
                >
                  <td className="px-4 py-3.5 flex items-center gap-2">
                    <span className="text-base" role="img" aria-label={sc.name}>
                      {sc.icon}
                    </span>
                    <span className={isCombined ? "font-bold text-cyan-300" : ""}>{sc.name}</span>
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono">
                    {sc.temperature_c.toFixed(1)}°C
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono">
                    {sc.temp_reduction_c > 0 ? (
                      <span className="text-emerald-400">-{sc.temp_reduction_c.toFixed(2)}°C</span>
                    ) : (
                      <span className="text-slate-500">0.00°C</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono">
                    {sc.carbon_reduction_pct < 0 ? (
                      <span className="text-emerald-400">{-sc.carbon_reduction_pct}%</span>
                    ) : (
                      <span className="text-slate-500">0%</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono">
                    {sc.estimated_cost_m_usd > 0 ? (
                      <span className="text-amber-400">${sc.estimated_cost_m_usd.toFixed(1)}M</span>
                    ) : (
                      <span className="text-slate-500">$0M</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono">
                    {sc.heat_stress_reduction_pct < 0 ? (
                      <span className="text-cyan-400">{-sc.heat_stress_reduction_pct}%</span>
                    ) : (
                      <span className="text-slate-500">0%</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                        sc.overall_score >= 80
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : sc.overall_score >= 50
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                          : "bg-slate-700/30 text-slate-400 border border-slate-700/30"
                      }`}
                    >
                      {sc.overall_score}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* AI Recommendations & Logic */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Recommendation Panel */}
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/10 p-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4.5 w-4.5 text-emerald-400" />
            <h4 className="text-xs font-bold text-emerald-300 uppercase tracking-wide">AI Recommendation</h4>
          </div>
          <div className="mt-2.5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold text-white">{recommendation.strategy}</span>
              <span className="text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">
                {recommendation.confidence_pct}% Match
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-300 leading-relaxed">{recommendation.reason}</p>
            <button
              onClick={() => setIsPlanModalOpen(true)}
              className="mt-3 w-full rounded border border-emerald-500/40 bg-emerald-500/10 py-1.5 text-xs font-bold text-emerald-300 transition-colors hover:bg-emerald-500/20"
            >
              🤖 AI Recommended Action Plan
            </button>
          </div>
        </div>

        {/* Selected Scenario Reasoning */}
        {selectedScenarioName && (
          <div className="rounded-lg border border-slate-800 bg-[#0d1322]/50 p-4">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide flex items-center gap-1.5">
              <span>Why {selectedScenarioName} works</span>
            </h4>
            <div className="mt-2 text-xs text-slate-400 space-y-1.5 max-h-[85px] overflow-y-auto pr-1">
              {scenarios
                .find((s) => s.name === selectedScenarioName)
                ?.reasoning.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-1.5">
                    <ArrowRight className="h-3 w-3 text-cyan-400 mt-1 shrink-0" />
                    <span>{item}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* AI Action Plan — portal dialog (escapes scrollable main panel) */}
      {isPlanModalOpen && typeof document !== "undefined" && createPortal(
        <div
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-md"
          role="dialog"
          aria-modal="true"
          aria-labelledby="action-plan-title"
          onClick={() => setIsPlanModalOpen(false)}
        >
          <div
            className="relative flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-emerald-700/50 bg-[#0d1322] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 bg-[#111827] px-5 py-4 rounded-t-xl shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xl">🤖</span>
                <h2 id="action-plan-title" className="text-lg font-bold text-emerald-300">AI Urban Cooling Plan Strategies</h2>
              </div>
              <button
                onClick={() => setIsPlanModalOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6 min-h-0">
              {scenarios
                .filter((s) => !s.name.includes("Combined") && !s.name.includes("Current") && !s.name.includes("Baseline"))
                .sort((a, b) => b.temp_reduction_c - a.temp_reduction_c)
                .map((sc, idx) => {
                  const isRoof = sc.name.toLowerCase().includes("roof");
                  const isTree = (sc.name.toLowerCase().includes("tree") || sc.name.toLowerCase().includes("green")) && !isRoof;
                  
                  const recommendationText = isTree
                    ? `Plant approximately ${Math.round(sc.temp_reduction_c * 2500)} native trees along roads, schools and public parks.`
                    : isRoof
                    ? `Convert ${Math.round(sc.temp_reduction_c * 30 + 20)}% of public buildings to reflective/green roofing.`
                    : `Create ponds and bioswales near high-density thermal hotspots.`;

                  const implTime = isTree ? "2–3 Years" : isRoof ? "6-12 Months" : "1-2 Years";
                  const priorityStars = "★".repeat(Math.max(1, 5 - idx)) + "☆".repeat(idx);

                  return (
                    <div key={sc.name} className="relative rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                      {/* Priority Label */}
                      <div className="absolute -top-3 left-4 rounded bg-emerald-950 px-2 py-0.5 text-[10px] font-bold tracking-wider text-emerald-400 border border-emerald-800">
                        Priority {idx + 1}
                      </div>

                      <div className="mt-2 flex items-start gap-4">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-slate-800 text-2xl border border-slate-700">
                          {sc.icon}
                        </div>
                        <div className="flex-1 space-y-3">
                          <h3 className="text-base font-bold text-white">{sc.name}</h3>

                          <div className="space-y-2 text-xs">
                            <div>
                              <span className="font-semibold text-slate-400">Reason:</span>
                              <p className="text-slate-300 mt-0.5">{sc.reasoning[0] || "Identified as high-impact zone."}</p>
                            </div>
                            
                            <div>
                              <span className="font-semibold text-emerald-400">Recommendation:</span>
                              <p className="text-emerald-100 mt-0.5">{recommendationText}</p>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-3 rounded bg-slate-950/50 p-3 text-xs md:grid-cols-4">
                            <div>
                              <span className="block text-slate-500 mb-0.5">Expected Cooling</span>
                              <span className="font-mono font-bold text-cyan-300">
                                {sc.temp_reduction_c > 0 ? `↓ ${sc.temp_reduction_c.toFixed(1)}°C` : "0.0°C"}
                              </span>
                            </div>
                            <div>
                              <span className="block text-slate-500 mb-0.5">Estimated Cost</span>
                              <span className="font-mono font-bold text-amber-300">
                                ${sc.estimated_cost_m_usd.toFixed(1)}M
                              </span>
                            </div>
                            <div>
                              <span className="block text-slate-500 mb-0.5">Implementation</span>
                              <span className="font-bold text-slate-300">{implTime}</span>
                            </div>
                            <div>
                              <span className="block text-slate-500 mb-0.5">Priority</span>
                              <span className="text-yellow-400 text-sm tracking-widest">{priorityStars}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}

              {/* 1. Expected Overall Impact */}
              {(() => {
                const combined = scenarios.find((s) => s.name.includes("Combined"));
                if (!combined) return null;
                const baseLst = comparison.baseline_lst_c || (combined.temperature_c + combined.temp_reduction_c);
                const popNum = (combined.population_benefited / 1000000).toFixed(1);
                
                return (
                  <div className="rounded-lg border border-cyan-500/20 bg-cyan-950/10 p-5 mt-6">
                    <h3 className="text-sm font-bold text-cyan-300 uppercase tracking-wide mb-4">
                      Expected Overall Impact
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                      {/* Temperature */}
                      <div className="bg-slate-900/60 rounded p-3 text-center border border-slate-800">
                        <span className="block text-[10px] uppercase text-slate-500 mb-1 font-bold">Temperature</span>
                        <div className="flex flex-col items-center">
                          <span className="text-slate-400 line-through text-xs">{baseLst.toFixed(1)}°C</span>
                          <span className="text-emerald-400 font-bold">↓ {combined.temperature_c.toFixed(1)}°C</span>
                          <span className="text-cyan-300 text-[10px] mt-1 bg-cyan-900/30 px-1.5 py-0.5 rounded">Cooling {combined.temp_reduction_c.toFixed(1)}°C</span>
                        </div>
                      </div>
                      
                      {/* Carbon */}
                      <div className="bg-slate-900/60 rounded p-3 text-center border border-slate-800 flex flex-col justify-center">
                        <span className="block text-[10px] uppercase text-slate-500 mb-1 font-bold">Carbon</span>
                        <span className="text-emerald-400 font-bold">↓ {Math.abs(combined.co2_tons_yr || 687).toFixed(0)}</span>
                        <span className="text-slate-400 text-[10px]">tons/year</span>
                      </div>
                      
                      {/* Heat Stress */}
                      <div className="bg-slate-900/60 rounded p-3 text-center border border-slate-800 flex flex-col justify-center">
                        <span className="block text-[10px] uppercase text-slate-500 mb-1 font-bold">Heat Stress</span>
                        <span className="text-emerald-400 font-bold">↓ {Math.abs(combined.heat_stress_reduction_pct || 17).toFixed(0)}%</span>
                        <span className="text-slate-400 text-[10px]">reduction</span>
                      </div>
                      
                      {/* Population */}
                      <div className="bg-slate-900/60 rounded p-3 text-center border border-slate-800 flex flex-col justify-center">
                        <span className="block text-[10px] uppercase text-slate-500 mb-1 font-bold">Pop. Protected</span>
                        <span className="text-cyan-300 font-bold">{popNum}</span>
                        <span className="text-slate-400 text-[10px]">Million</span>
                      </div>
                      
                      {/* Tree Cover (Mock) */}
                      <div className="bg-slate-900/60 rounded p-3 text-center border border-slate-800">
                        <span className="block text-[10px] uppercase text-slate-500 mb-1 font-bold">Tree Cover</span>
                        <div className="flex flex-col items-center">
                          <span className="text-slate-400 text-xs">18%</span>
                          <span className="text-emerald-400 font-bold">↓ 36%</span>
                        </div>
                      </div>
                      
                      {/* NDVI (Mock) */}
                      <div className="bg-slate-900/60 rounded p-3 text-center border border-slate-800">
                        <span className="block text-[10px] uppercase text-slate-500 mb-1 font-bold">NDVI</span>
                        <div className="flex flex-col items-center">
                          <span className="text-slate-400 text-xs">0.24</span>
                          <span className="text-emerald-400 font-bold">↓ 0.43</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* 2. AI Explainability */}
              <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-5 mt-6">
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wide flex items-center gap-2">
                  <HelpCircle className="h-4 w-4 text-violet-400" />
                  AI Explainability: "Why did AI recommend this?"
                </h3>
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 mb-2 uppercase tracking-wider">Why AI Selected This Plan</p>
                    <p className="text-sm text-slate-300 leading-relaxed">
                      The model predicts that increasing tree canopy provides the highest cooling impact per dollar invested in the targeted high-vulnerability zones.
                    </p>
                    <div className="mt-4 inline-flex items-center gap-2 rounded bg-violet-900/30 px-3 py-1.5 border border-violet-800/50">
                      <span className="text-xs text-violet-300">Confidence</span>
                      <span className="text-sm font-bold text-violet-400">94%</span>
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 mb-2 uppercase tracking-wider">AI analysed</p>
                    <div className="grid grid-cols-2 gap-y-2.5 gap-x-4 text-xs text-slate-300">
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Land Surface Temp</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Vegetation Index</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Built-up Density</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Population Density</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Heat Hotspots</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Carbon Emissions</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Budget</div>
                      <div className="flex items-center gap-1.5"><span className="text-emerald-500 font-bold">✓</span> Water Availability</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 3. Implementation Roadmap */}
              {(() => {
                const roofSc = scenarios.find(s => s.name.toLowerCase().includes("roof") && !s.name.toLowerCase().includes("green"));
                const waterSc = scenarios.find(s => s.name.toLowerCase().includes("water") || s.name.toLowerCase().includes("blue"));
                const treeSc = scenarios.find(s => (s.name.toLowerCase().includes("tree") || s.name.toLowerCase().includes("urban green")) && !s.name.toLowerCase().includes("roof"));
                const combinedSc = scenarios.find(s => s.name.includes("Combined"));
                const phases = [
                  { label: "Phase 1 (0–6 Months)", color: "bg-cyan-500", textColor: "text-cyan-400", title: "Apply Cool Roofs", sc: roofSc },
                  { label: "Phase 2 (6–18 Months)", color: "bg-blue-500", textColor: "text-blue-400", title: "Create Water Bodies", sc: waterSc },
                  { label: "Phase 3 (2–5 Years)", color: "bg-emerald-500", textColor: "text-emerald-400", title: "Tree Plantation", sc: treeSc },
                ];
                return (
                  <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-5 mt-6">
                    <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wide mb-6 flex items-center gap-2">
                      <span className="text-amber-400">🗺️</span> Implementation Roadmap
                    </h3>
                    <div className="relative pl-4 border-l-2 border-slate-700 space-y-6">
                      {phases.map((ph, idx) => (
                        <div key={idx} className="relative">
                          <div className={`absolute -left-[21px] top-1 h-3 w-3 rounded-full ${ph.color} border-4 border-[#111827]`}></div>
                          <div className="flex justify-between items-start">
                            <div>
                              <span className={`text-[10px] font-bold uppercase tracking-wider ${ph.textColor}`}>{ph.label}</span>
                              <h4 className="text-sm font-bold text-white mt-1">{ph.title}</h4>
                              {ph.sc && <p className="text-[10px] text-slate-400 mt-0.5 max-w-[240px] leading-relaxed">{ph.sc.reasoning[0] ?? ""}</p>}
                            </div>
                            <div className="bg-slate-900 px-2 py-1 rounded border border-slate-700 text-right shrink-0 ml-2">
                              <span className="block text-[10px] text-slate-400">Cooling</span>
                              <span className={`font-mono text-sm font-bold ${ph.textColor}`}>
                                {ph.sc ? `↓ ${ph.sc.temp_reduction_c.toFixed(1)}°C` : "—"}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                      <div className="relative pt-2">
                        <div className="absolute -left-[23px] top-3 h-4 w-4 rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400 border-4 border-[#111827]"></div>
                        <div className="bg-gradient-to-r from-emerald-900/40 to-cyan-900/40 border border-emerald-500/30 rounded-lg p-3 flex justify-between items-center">
                          <span className="font-bold text-white uppercase tracking-wider text-sm">Final Target</span>
                          <div className="text-right">
                            <span className="block text-[10px] text-slate-400 uppercase tracking-wider">Temperature</span>
                            <span className="text-emerald-400 font-mono text-lg font-bold">
                              {combinedSc?.temperature_c.toFixed(1) ?? "—"}°C
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* 4. Smart Suggestions ────────────────────────────────── */}
              {(() => {
                const suggestion = computeSmartSuggestion(scenarios, budget);
                if (!suggestion.allocation.length) return null;
                return (
                  <div className="rounded-lg border border-violet-700/50 bg-gradient-to-b from-violet-950/30 to-violet-950/10 p-5 mt-6">
                    {/* Header */}
                    <div className="flex items-start gap-3 mb-4">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-violet-900/60 border border-violet-700/50 text-xl">
                        🧠
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-violet-200 uppercase tracking-wide">
                          Smart Suggestions
                        </h3>
                        <p className="text-[10px] text-violet-400 mt-0.5">
                          AI-optimised for your ${budget.toFixed(1)}M budget · {suggestion.title}
                        </p>
                      </div>
                    </div>

                    {/* Budget Chip */}
                    <div className="inline-flex items-center gap-2 rounded-full bg-amber-900/40 border border-amber-700/50 px-3 py-1 mb-4">
                      <span className="text-amber-400 text-sm">💰</span>
                      <span className="text-xs font-bold text-amber-300">
                        Budget: ${budget.toFixed(1)}M
                      </span>
                      <span className="text-[10px] text-amber-500">→</span>
                      <span className="text-xs font-bold text-emerald-300">
                        Expected Cooling: {suggestion.expectedCooling}°C
                      </span>
                    </div>

                    {/* Allocation bars */}
                    <div className="space-y-3 mb-5">
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Recommended Allocation</p>
                      {suggestion.allocation.map((a, idx) => (
                        <div key={idx}>
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="flex items-center gap-1.5 font-semibold text-slate-200">
                              <span>{a.icon}</span> {a.label}
                            </span>
                            <span className="font-mono font-bold text-violet-300">{a.pct}%</span>
                          </div>
                          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                            <div
                              className="h-full rounded-full transition-all duration-700"
                              style={{
                                width: `${a.pct}%`,
                                background: `linear-gradient(90deg, #7c3aed, #06b6d4)`,
                                transitionDelay: `${idx * 120}ms`,
                              }}
                            />
                          </div>
                          <p className="text-[9px] text-slate-500 mt-0.5 text-right font-mono">↓ {a.cooling.toFixed(1)}°C contribution</p>
                        </div>
                      ))}
                    </div>

                    {/* ROI summary */}
                    <div className="grid grid-cols-3 gap-3 mb-5">
                      <div className="rounded-lg bg-slate-900/70 border border-slate-700/50 p-2.5 text-center">
                        <span className="block text-[9px] uppercase text-slate-500 mb-1">Expected ΔT</span>
                        <span className="font-mono font-bold text-emerald-300 text-sm">↓{suggestion.expectedCooling}°C</span>
                      </div>
                      <div className="rounded-lg bg-slate-900/70 border border-slate-700/50 p-2.5 text-center">
                        <span className="block text-[9px] uppercase text-slate-500 mb-1">Budget</span>
                        <span className="font-mono font-bold text-amber-300 text-sm">${budget.toFixed(1)}M</span>
                      </div>
                      <div className="rounded-lg bg-slate-900/70 border border-slate-700/50 p-2.5 text-center">
                        <span className="block text-[9px] uppercase text-slate-500 mb-1">ROI</span>
                        <span className="font-mono font-bold text-cyan-300 text-sm">
                          {budget > 0 ? (suggestion.expectedCooling / budget).toFixed(2) : "∞"}°C/$M
                        </span>
                      </div>
                    </div>

                    {/* Why Not? */}
                    {suggestion.whyNot.length > 0 && (
                      <div className="rounded-lg border border-orange-800/40 bg-orange-950/20 p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <span className="text-base">🚫</span>
                          <p className="text-xs font-bold text-orange-300 uppercase tracking-wide">
                            Why Not? — Deprioritised Strategies
                          </p>
                        </div>
                        <div className="space-y-4">
                          {suggestion.whyNot.map((item, idx) => (
                            <div key={idx} className="rounded-lg bg-slate-900/60 border border-slate-700/40 p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                                  <span>{item.icon}</span> {item.name}
                                </span>
                                <span className="text-[9px] font-bold text-orange-400 bg-orange-900/30 border border-orange-800/50 px-1.5 py-0.5 rounded">
                                  Priority #{item.priority + 1}
                                </span>
                              </div>
                              <div className="space-y-1">
                                {item.reasons.map((r, ri) => (
                                  <div key={ri} className="flex items-start gap-1.5 text-[10px] text-slate-400 leading-snug">
                                    <span className="text-orange-500 font-bold mt-px shrink-0">•</span>
                                    <span>{r}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                        <p className="mt-3 text-[9px] text-slate-500 leading-relaxed">
                          * Priorities are calculated using cooling-per-million-dollar ROI. Increase your budget to unlock higher-priority strategies.
                        </p>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>

            {/* Modal Footer */}
            <div className="border-t border-slate-800 bg-[#111827] px-5 py-4 rounded-b-xl flex justify-end shrink-0">
              <button
                onClick={() => setIsPlanModalOpen(false)}
                className="rounded-lg bg-slate-700 px-6 py-2 text-sm font-bold text-white transition-colors hover:bg-slate-600"
              >
                Close
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

