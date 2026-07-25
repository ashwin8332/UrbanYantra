"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { WardCollection, WardProperties } from "@/types";

/* ── Color ramp helpers (duplicated from HeatMap to avoid coupling) ───────── */
type Rgb = [number, number, number];
type ColorStop = { at: number; rgb: Rgb };

const LST_RAMP: ColorStop[] = [
  { at: 0,    rgb: [41, 121, 255] },
  { at: 0.35, rgb: [0, 200, 83] },
  { at: 0.6,  rgb: [255, 214, 0] },
  { at: 0.8,  rgb: [255, 145, 0] },
  { at: 1,    rgb: [255, 23, 68] },
];

function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }

function rampRgb(t: number, stops: ColorStop[]): Rgb {
  const c = Math.max(0, Math.min(1, t));
  let lo = stops[0], hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (c >= stops[i].at && c <= stops[i + 1].at) { lo = stops[i]; hi = stops[i + 1]; break; }
  }
  const span = hi.at - lo.at || 1;
  const f = (c - lo.at) / span;
  return [Math.round(lerp(lo.rgb[0], hi.rgb[0], f)), Math.round(lerp(lo.rgb[1], hi.rgb[1], f)), Math.round(lerp(lo.rgb[2], hi.rgb[2], f))];
}

function lstToColor(lst: number, vmin: number, vmax: number, alpha = 200): string {
  const t = vmax > vmin ? Math.max(0, Math.min(1, (lst - vmin) / (vmax - vmin))) : 0.5;
  const [r, g, b] = rampRgb(t, LST_RAMP);
  return `rgba(${r},${g},${b},${alpha / 255})`;
}

/* ── SVG mini-map renderer ─────────────────────────────────────────────────── */
interface MiniMapProps {
  wards: WardCollection;
  simValues: Record<string, number>; // ward_id -> simulated LST (or baseline if empty)
  useSimulated: boolean;
  vmin: number;
  vmax: number;
  bbox: number[]; // [minLon, minLat, maxLon, maxLat]
  width: number;
  height: number;
}

function MiniMap({ wards, simValues, useSimulated, vmin, vmax, bbox, width, height }: MiniMapProps) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const lonSpan = maxLon - minLon;
  const latSpan = maxLat - minLat;

  function project(lon: number, lat: number): [number, number] {
    const x = ((lon - minLon) / lonSpan) * width;
    const y = ((maxLat - lat) / latSpan) * height;
    return [x, y];
  }

  function ringToPath(coords: number[][]): string {
    return coords.map((pt, i) => {
      const [x, y] = project(pt[0], pt[1]);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ") + " Z";
  }

  return (
    <svg width={width} height={height} className="block">
      {wards.features.map((feat, idx) => {
        const p = feat.properties as WardProperties;
        const lst = useSimulated
          ? (simValues[p.ward_id] ?? p.avg_lst_c)
          : p.avg_lst_c;
        const fill = lstToColor(lst, vmin, vmax);
        const ring = feat.geometry.coordinates[0];
        return (
          <path
            key={p.ward_id ?? idx}
            d={ringToPath(ring)}
            fill={fill}
            stroke="rgba(15,20,25,0.5)"
            strokeWidth="0.5"
          />
        );
      })}
    </svg>
  );
}

/* ── Before/After component ─────────────────────────────────────────────────── */
interface BeforeAfterMapProps {
  wards: WardCollection;
  wardSimulations: Record<string, number>;
  baselineLst: number;
  simulatedLst: number;
  bbox: number[];
}

export default function BeforeAfterMap({
  wards,
  wardSimulations,
  baselineLst,
  simulatedLst,
  bbox,
}: BeforeAfterMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sliderPct, setSliderPct] = useState(50);
  const [dragging, setDragging] = useState(false);
  const [containerW, setContainerW] = useState(600);
  const [containerH, setContainerH] = useState(320);

  // Compute shared vmin/vmax across both views
  const allLst = wards.features.map((f) => f.properties.avg_lst_c);
  const simLst = wards.features.map((f) => wardSimulations[f.properties.ward_id] ?? f.properties.avg_lst_c);
  const allVals = [...allLst, ...simLst];
  const vmin = Math.min(...allVals) - 0.5;
  const vmax = Math.max(...allVals) + 0.5;

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const e = entries[0];
      setContainerW(Math.floor(e.contentRect.width));
      setContainerH(Math.floor(e.contentRect.height));
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const updateSlider = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = Math.max(5, Math.min(95, ((clientX - rect.left) / rect.width) * 100));
    setSliderPct(pct);
  }, []);

  const onMouseDown = (e: React.MouseEvent) => { setDragging(true); updateSlider(e.clientX); };
  const onMouseMove = useCallback((e: MouseEvent) => { if (dragging) updateSlider(e.clientX); }, [dragging, updateSlider]);
  const onMouseUp   = useCallback(() => setDragging(false), []);
  const onTouchMove = useCallback((e: TouchEvent) => { if (dragging) updateSlider(e.touches[0].clientX); }, [dragging, updateSlider]);

  useEffect(() => {
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("touchmove", onTouchMove);
    window.addEventListener("touchend", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onMouseUp);
    };
  }, [onMouseMove, onMouseUp, onTouchMove]);

  const delta = parseFloat((baselineLst - simulatedLst).toFixed(2));

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/80 overflow-hidden">
      {/* Header badges */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700/50">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-orange-500/20 border border-orange-500/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-orange-300">
            🔥 Before
          </span>
          <span className="text-[10px] text-slate-500">Current Heat Map</span>
        </div>
        <div className="text-center">
          <span className="text-[10px] font-bold text-emerald-300">↓ {delta}°C reduction</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-500">After Simulation</span>
          <span className="rounded-md bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
            🌿 After
          </span>
        </div>
      </div>

      {/* Split map */}
      <div
        ref={containerRef}
        className="relative overflow-hidden"
        style={{ height: 300, cursor: dragging ? "col-resize" : "ew-resize" }}
        onMouseDown={onMouseDown}
        onTouchStart={(e) => { setDragging(true); updateSlider(e.touches[0].clientX); }}
      >
        {/* AFTER map (full width, underneath) */}
        <div className="absolute inset-0 select-none">
          <MiniMap
            wards={wards}
            simValues={wardSimulations}
            useSimulated={true}
            vmin={vmin}
            vmax={vmax}
            bbox={bbox}
            width={containerW}
            height={containerH}
          />
        </div>

        {/* BEFORE map (clipped to left side) */}
        <div
          className="absolute inset-0 select-none overflow-hidden"
          style={{ clipPath: `inset(0 ${100 - sliderPct}% 0 0)` }}
        >
          <MiniMap
            wards={wards}
            simValues={{}}
            useSimulated={false}
            vmin={vmin}
            vmax={vmax}
            bbox={bbox}
            width={containerW}
            height={containerH}
          />
        </div>

        {/* Divider handle */}
        <div
          className="absolute top-0 bottom-0 z-10 flex items-center justify-center"
          style={{ left: `${sliderPct}%`, transform: "translateX(-50%)" }}
        >
          <div className="h-full w-0.5 bg-white/70 shadow-[0_0_8px_rgba(255,255,255,0.5)]" />
          <div
            className="absolute flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-slate-900 shadow-xl"
            style={{ cursor: "col-resize" }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M4 2L1 7L4 12" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M10 2L13 7L10 12" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        </div>

        {/* Corner labels */}
        <div className="pointer-events-none absolute left-2 top-2 z-20">
          <span className="rounded bg-orange-900/70 px-1.5 py-0.5 text-[9px] font-bold text-orange-300 backdrop-blur-sm">
            BEFORE · {baselineLst.toFixed(1)}°C
          </span>
        </div>
        <div className="pointer-events-none absolute right-2 top-2 z-20">
          <span className="rounded bg-emerald-900/70 px-1.5 py-0.5 text-[9px] font-bold text-emerald-300 backdrop-blur-sm">
            AFTER · {simulatedLst.toFixed(1)}°C
          </span>
        </div>

        {/* Instruction hint */}
        <div className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2 z-20">
          <span className="rounded-full bg-slate-900/80 px-2.5 py-1 text-[9px] text-slate-400 backdrop-blur-sm border border-slate-700/50">
            ← drag to compare →
          </span>
        </div>
      </div>

      {/* Color scale legend */}
      <div className="flex items-center gap-2 px-4 py-2 border-t border-slate-700/40">
        <span className="text-[9px] text-slate-500 shrink-0">Cool</span>
        <div
          className="h-2 flex-1 rounded-full"
          style={{ background: "linear-gradient(90deg, rgb(41,121,255), rgb(0,200,83), rgb(255,214,0), rgb(255,145,0), rgb(255,23,68))" }}
        />
        <span className="text-[9px] text-slate-500 shrink-0">Hot</span>
        <span className="text-[9px] text-slate-600 ml-2">{vmin.toFixed(0)}–{vmax.toFixed(0)}°C</span>
      </div>
    </div>
  );
}
