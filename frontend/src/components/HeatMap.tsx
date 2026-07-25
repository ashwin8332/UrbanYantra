"use client";

import { useMemo, useState, useCallback, useEffect } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer, IconLayer } from "@deck.gl/layers";
import type { PickingInfo, MapViewState } from "@deck.gl/core";
import type { FeatureCollection, Polygon } from "geojson";
import Map, { Source, Layer as MapLayerGL } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { getThermalOverlayMeta, thermalOverlayUrl } from "@/lib/api";
import type {
  HeatmapMeta,
  HotspotFeature,
  HotspotCollection,
  MapLayer,
  PointPrediction,
  SamplePointCollection,
  ThermalOverlayMeta,
  WardCollection,
  WardProperties,
} from "@/types";

/* ── Basemaps ──────────────────────────────────────────────────────────── */
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

const SATELLITE_MAP_STYLE = {
  version: 8 as const,
  sources: {
    esri: {
      type: "raster" as const,
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "© Esri, Earthstar Geographics",
      maxzoom: 19,
    },
  },
  layers: [{ id: "esri-satellite", type: "raster" as const, source: "esri" }],
};

/* Jet ramp stops for thermal legend (Kelvin scale) */
const THERMAL_JET_STOPS: ColorStop[] = [
  { at: 0,    rgb: [0, 0, 143] },
  { at: 0.17, rgb: [0, 0, 255] },
  { at: 0.33, rgb: [0, 255, 255] },
  { at: 0.5,  rgb: [0, 255, 0] },
  { at: 0.67, rgb: [255, 255, 0] },
  { at: 0.83, rgb: [255, 127, 0] },
  { at: 1,    rgb: [255, 0, 0] },
];

type Rgb = [number, number, number];
type ColorStop = { at: number; rgb: Rgb };

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function rampRgb(t: number, stops: ColorStop[]): Rgb {
  const clamped = Math.max(0, Math.min(1, t));
  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (clamped >= stops[i].at && clamped <= stops[i + 1].at) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const span = hi.at - lo.at || 1;
  const f = (clamped - lo.at) / span;
  return [
    Math.round(lerp(lo.rgb[0], hi.rgb[0], f)),
    Math.round(lerp(lo.rgb[1], hi.rgb[1], f)),
    Math.round(lerp(lo.rgb[2], hi.rgb[2], f)),
  ];
}

function normalize(value: number, vmin: number, vmax: number): number {
  if (!Number.isFinite(value)) return 0;
  if (vmax <= vmin) return 0.5;
  return Math.max(0, Math.min(1, (value - vmin) / (vmax - vmin)));
}

const LAYER_RAMPS: Record<MapLayer, ColorStop[]> = {
  lst: [
    { at: 0,    rgb: [41, 121, 255] },
    { at: 0.35, rgb: [0, 200, 83] },
    { at: 0.6,  rgb: [255, 214, 0] },
    { at: 0.8,  rgb: [255, 145, 0] },
    { at: 1,    rgb: [255, 23, 68] },
  ],
  thermal: [
    { at: 0,    rgb: [0, 0, 143] },
    { at: 0.2,  rgb: [59, 130, 246] },
    { at: 0.4,  rgb: [6, 182, 212] },
    { at: 0.55, rgb: [16, 185, 129] },
    { at: 0.7,  rgb: [245, 158, 11] },
    { at: 0.85, rgb: [255, 100, 0] },
    { at: 1,    rgb: [239, 68, 68] },
  ],
  utci: [
    { at: 0,    rgb: [0, 200, 83] },
    { at: 0.45, rgb: [255, 214, 0] },
    { at: 0.7,  rgb: [255, 145, 0] },
    { at: 1,    rgb: [255, 23, 68] },
  ],
  ndvi: [
    { at: 0,    rgb: [180, 90, 40] },
    { at: 0.35, rgb: [210, 180, 60] },
    { at: 0.65, rgb: [130, 200, 80] },
    { at: 1,    rgb: [0, 150, 60] },
  ],
  svf: [
    { at: 0,    rgb: [230, 220, 245] },
    { at: 0.35, rgb: [180, 140, 210] },
    { at: 0.65, rgb: [128, 50, 180] },
    { at: 1,    rgb: [75, 0, 130] },
  ],
  ghsl_built: [
    { at: 0,    rgb: [255, 245, 235] },
    { at: 0.25, rgb: [253, 174, 97] },
    { at: 0.55, rgb: [230, 85, 13] },
    { at: 0.8,  rgb: [178, 24, 43] },
    { at: 1,    rgb: [103, 0, 31] },
  ],
  ghsl_population: [
    { at: 0,    rgb: [255, 255, 204] },
    { at: 0.3,  rgb: [254, 217, 118] },
    { at: 0.55, rgb: [252, 141, 89] },
    { at: 0.75, rgb: [227, 74, 51] },
    { at: 1,    rgb: [128, 0, 38] },
  ],
  ghsl_smod: [
    { at: 0,    rgb: [247, 252, 240] },
    { at: 0.25, rgb: [189, 201, 225] },
    { at: 0.5,  rgb: [116, 169, 207] },
    { at: 0.75, rgb: [43, 140, 190] },
    { at: 1,    rgb: [8, 48, 107] },
  ],
  vulnerability: [
    { at: 0,    rgb: [0, 200, 83] },
    { at: 0.35, rgb: [255, 214, 0] },
    { at: 0.65, rgb: [255, 145, 0] },
    { at: 1,    rgb: [255, 23, 68] },
  ],
};

const LAYER_CONFIG: Record<MapLayer, {
  legendTitle: string;
  heightNote: string;
  unit: string;
  ramp: ColorStop[];
  getValue: (p: WardProperties, wardSim: Record<string, number>, domains?: WardCollection | null, cityKey?: string) => number;
  formatValue: (v: number) => string;
  tooltipLabel: string;
  defaultBounds: [number, number];
}> = {
  lst: {
    legendTitle: "Surface Temperature (LST)",
    heightNote: "Height ∝ temperature",
    unit: "°C",
    ramp: LAYER_RAMPS.lst,
    getValue: (p, wardSim, domains, cityKey) => {
      if (wardSim[p.ward_id] !== undefined) return wardSim[p.ward_id];
      if (p.name && cityKey && domains) {
        const suffix = `_${p.name.toLowerCase().replace(/ /g, '_')}`;
        const matchKey = Object.keys(wardSim).find((k) => k.endsWith(suffix));
        if (matchKey && wardSim[matchKey] !== undefined) {
          const simVal = wardSim[matchKey];
          const wardFeature = domains.features.find((f) => f.properties.ward_id === matchKey);
          if (wardFeature) {
            const baseVal = wardFeature.properties.lst_calibrated_c ?? wardFeature.properties.avg_lst_c;
            const delta = Math.max(0, baseVal - simVal);
            return (p.lst_calibrated_c ?? p.avg_lst_c) - delta;
          }
        }
      }
      return p.lst_calibrated_c ?? p.avg_lst_c;
    },
    formatValue: (v) => `${v.toFixed(1)}°C`,
    tooltipLabel: "LST",
    defaultBounds: [32, 44],
  },
  thermal: {
    legendTitle: "Land Surface Temperature",
    heightNote: "Satellite thermal raster (Landsat ST_B10)",
    unit: " K",
    ramp: THERMAL_JET_STOPS,
    getValue: (p, wardSim, domains, cityKey) => {
      if (wardSim[p.ward_id] !== undefined) return wardSim[p.ward_id] + 273.15;
      let temp = p.lst_calibrated_c ?? p.avg_lst_c;
      if (p.name && cityKey && domains) {
        const suffix = `_${p.name.toLowerCase().replace(/ /g, '_')}`;
        const matchKey = Object.keys(wardSim).find((k) => k.endsWith(suffix));
        if (matchKey && wardSim[matchKey] !== undefined) {
          const simVal = wardSim[matchKey];
          const wardFeature = domains.features.find((f) => f.properties.ward_id === matchKey);
          if (wardFeature) {
            const baseVal = wardFeature.properties.lst_calibrated_c ?? wardFeature.properties.avg_lst_c;
            const delta = Math.max(0, baseVal - simVal);
            temp = temp - delta;
          }
        }
      }
      return temp + 273.15;
    },
    formatValue: (v) => `${v.toFixed(1)} K`,
    tooltipLabel: "LST",
    defaultBounds: [305, 320],
  },
  utci: {
    legendTitle: "Heat Stress (UTCI)",
    heightNote: "Height ∝ heat stress",
    unit: "°C UTCI",
    ramp: LAYER_RAMPS.utci,
    getValue: (p, wardSim, domains, cityKey) => {
      let utci = p.heat_stress_utci_c;
      if (p.name && cityKey && domains) {
        const suffix = `_${p.name.toLowerCase().replace(/ /g, '_')}`;
        const matchKey = Object.keys(wardSim).find((k) => k.endsWith(suffix));
        if (matchKey && wardSim[matchKey] !== undefined) {
          const simVal = wardSim[matchKey];
          const wardFeature = domains.features.find((f) => f.properties.ward_id === matchKey);
          if (wardFeature) {
            const baseVal = wardFeature.properties.lst_calibrated_c ?? wardFeature.properties.avg_lst_c;
            const delta = Math.max(0, baseVal - simVal);
            utci = utci - delta * 0.72;
          }
        }
      }
      return utci;
    },
    formatValue: (v) => `${v.toFixed(1)}°C UTCI`,
    tooltipLabel: "UTCI",
    defaultBounds: [18, 30],
  },
  ndvi: {
    legendTitle: "Green Coverage (NDVI)",
    heightNote: "Height ∝ vegetation",
    unit: "",
    ramp: LAYER_RAMPS.ndvi,
    getValue: (p) => p.ndvi,
    formatValue: (v) => v.toFixed(2),
    tooltipLabel: "NDVI",
    defaultBounds: [0.1, 0.35],
  },
  svf: {
    legendTitle: "Building Density",
    heightNote: "Height ∝ built-up area",
    unit: "",
    ramp: LAYER_RAMPS.svf,
    getValue: (p) => p.impervious_frac ?? Math.max(0, 1 - p.ndvi),
    formatValue: (v) => v.toFixed(2),
    tooltipLabel: "Built-up",
    defaultBounds: [0, 0.8],
  },
  ghsl_built: {
    legendTitle: "GHSL Built-up Surface",
    heightNote: "Height ∝ built-up density (GHSL Built-S)",
    unit: "",
    ramp: LAYER_RAMPS.ghsl_built,
    getValue: (p) => p.ghsl_built ?? p.building_density ?? p.impervious_frac ?? Math.max(0, 1 - p.ndvi),
    formatValue: (v) => `${(Math.min(1, Math.max(0, v)) * 100).toFixed(0)}%`,
    tooltipLabel: "GHSL Built-up",
    defaultBounds: [0, 1],
  },
  ghsl_population: {
    legendTitle: "GHSL Population",
    heightNote: "Height ∝ population exposure (GHSL)",
    unit: "",
    ramp: LAYER_RAMPS.ghsl_population,
    getValue: (p) => p.population ?? 0,
    formatValue: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)),
    tooltipLabel: "Population",
    defaultBounds: [0, 500],
  },
  ghsl_smod: {
    legendTitle: "GHSL Settlement (SMOD)",
    heightNote: "Height ∝ urban settlement degree",
    unit: "",
    ramp: LAYER_RAMPS.ghsl_smod,
    getValue: (p) => {
      if (p.ghsl_smod != null && p.ghsl_smod > 0) return Math.min(1, p.ghsl_smod / 30);
      if (p.lcz_class != null) return Math.min(1, p.lcz_class / 10);
      return p.building_density ?? p.impervious_frac ?? 0;
    },
    formatValue: (v) => (v >= 0.66 ? "Urban core" : v >= 0.33 ? "Suburban" : "Rural/open"),
    tooltipLabel: "SMOD",
    defaultBounds: [0, 1],
  },
  vulnerability: {
    legendTitle: "Risk Level",
    heightNote: "Height ∝ risk score",
    unit: "",
    ramp: LAYER_RAMPS.vulnerability,
    getValue: (p) => {
      const hotspot = p.hotspot_class ?? 0;
      const lst = p.lst_calibrated_c ?? p.avg_lst_c;
      const lstScore = Math.max(0, Math.min(1, (lst - 34) / 10));
      return hotspot + p.hotspot_fraction * 2 + lstScore * 0.5;
    },
    formatValue: (v) => (v >= 2.5 ? "Critical" : v >= 1.5 ? "High" : v >= 0.75 ? "Moderate" : "Low"),
    tooltipLabel: "Risk",
    defaultBounds: [0, 3],
  },
};

function valueRgba(value: number, vmin: number, vmax: number, ramp: ColorStop[], alpha = 235): [number, number, number, number] {
  const rgb = rampRgb(normalize(value, vmin, vmax), ramp);
  return [rgb[0], rgb[1], rgb[2], alpha];
}

function valueElevation(value: number, vmin: number, vmax: number, layer: MapLayer): number {
  const t = normalize(value, vmin, vmax);
  if (layer === "lst" || layer === "utci") {
    return Math.max(80, t * 2200);
  }
  if (layer === "ghsl_built" || layer === "ghsl_population" || layer === "ghsl_smod") {
    return Math.max(80, t * 1600);
  }
  return Math.max(80, t * 1400);
}

function legendStops(ramp: ColorStop[], vmin: number, vmax: number, unit: string) {
  return ramp.map((stop) => ({
    rgb: stop.rgb,
    label: unit ? `${(vmin + (vmax - vmin) * stop.at).toFixed(1)}${unit}` : (vmin + (vmax - vmin) * stop.at).toFixed(2),
  }));
}

/* ── Layer / view constants ─────────────────────────────────────────────── */
const LAYER_LABELS: { id: MapLayer; label: string; tip: string }[] = [
  { id: "lst",           label: "Surface Temperature",    tip: "How hot the ground surface is (°C) from satellite data." },
  { id: "thermal",       label: "Thermal View",           tip: "Real satellite thermal imagery (Landsat ST_B10, Kelvin) on Esri satellite basemap." },
  { id: "utci",          label: "Heat Stress on People",  tip: "How uncomfortable the heat feels to a person outdoors." },
  { id: "ndvi",          label: "Green Coverage",         tip: "How much vegetation (trees, grass) is in each area. Higher = cooler." },
  { id: "svf",           label: "Building Density",       tip: "How densely built the area is. Dense areas trap more heat." },
  { id: "ghsl_built",    label: "GHSL Built-up",          tip: "Real GHSL Built-S surface density — urban exposure & planning context." },
  { id: "ghsl_population", label: "GHSL Population",    tip: "Real GHSL population per cell — vulnerability & exposure to heat." },
  { id: "ghsl_smod",       label: "GHSL Settlement",    tip: "GHSL SMOD settlement degree — urban core vs suburban vs rural context." },
  { id: "vulnerability", label: "Risk Level",             tip: "Combined heat risk score — red areas need urgent intervention." },
];

interface TooltipState {
  x: number; y: number;
  value: number;
  valueLabel: string;
  formatted: string;
  vuln: string;
  name: string;
}

/* ── Props ──────────────────────────────────────────────────────────────── */
interface HeatMapProps {
  cityKey:         string;
  cityName:        string;
  domains:         WardCollection | null;
  fineGrid:        WardCollection | null;
  samplePoints:    SamplePointCollection | null;
  hotspots:        HotspotCollection | null;
  heatmapMeta:     HeatmapMeta | null;
  bbox:            number[];
  layer:           MapLayer;
  selectedWard:    WardProperties | null;
  targetWard:      string;
  onSelectWard:    (p: WardProperties | null) => void;
  wardSimulations: Record<string, number>;
  onLayerChange:   (l: MapLayer) => void;
  pointPrediction: PointPrediction | null;
  predicting:      boolean;
  onMapClick:      (lon: number, lat: number) => void;
}

export default function HeatMap({
  cityKey,
  cityName,
  domains,
  fineGrid,
  hotspots,
  heatmapMeta,
  bbox,
  layer,
  selectedWard,
  onSelectWard,
  wardSimulations,
  onLayerChange,
  pointPrediction,
  predicting,
  onMapClick,
}: HeatMapProps) {
  const isThermalMode = layer === "thermal";
  const [showGrid,      setShowGrid]      = useState(true);
  const [showDomains,   setShowDomains]   = useState(true);
  const [showHotspots,  setShowHotspots]  = useState(true);
  const [pitch,       setPitch]       = useState(45);
  const [bearing,     setBearing]     = useState(-15);
  const [thermalOverlay, setThermalOverlay] = useState<ThermalOverlayMeta | null>(null);
  const [thermalLoading, setThermalLoading] = useState(false);
  const [thermalError, setThermalError] = useState<string | null>(null);
  const [selectedHotspot, setSelectedHotspot] = useState<HotspotFeature | null>(null);
  const [pinIconReady, setPinIconReady] = useState(false);
  const [viewState,   setViewState]   = useState<MapViewState>(() => ({
    longitude: bbox?.length === 4 ? (bbox[0] + bbox[2]) / 2 : 77.59,
    latitude:  bbox?.length === 4 ? (bbox[1] + bbox[3]) / 2 : 12.97,
    zoom:      11.2,
    pitch:     45,
    bearing:   -15,
    minZoom:   6,
    maxZoom:   18,
  }));
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const layerConfig = LAYER_CONFIG[layer];

  /* Load georeferenced Landsat thermal overlay (RGBA PNG on satellite basemap) */
  useEffect(() => {
    if (!isThermalMode || !cityKey) {
      setThermalOverlay(null);
      setThermalError(null);
      setThermalLoading(false);
      return;
    }
    let cancelled = false;
    setThermalLoading(true);
    setThermalError(null);
    getThermalOverlayMeta(cityKey)
      .then((data) => {
        if (!cancelled) {
          setThermalOverlay(data);
          setThermalLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setThermalOverlay(null);
          setThermalError(err instanceof Error ? err.message : "Thermal overlay unavailable");
          setThermalLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [isThermalMode, cityKey]);

  const scaleBounds = useMemo<[number, number]>(() => {
    if (isThermalMode) {
      if (thermalOverlay) return [thermalOverlay.vmin_k, thermalOverlay.vmax_k];
      return layerConfig.defaultBounds;
    }
    const metaOk = heatmapMeta?.layer === layer && heatmapMeta.vmax > heatmapMeta.vmin;
    if (metaOk) return [heatmapMeta.vmin, heatmapMeta.vmax];

    const values = (fineGrid?.features ?? []).map((f) =>
      layerConfig.getValue(f.properties, wardSimulations, domains, cityKey)
    ).filter((v) => Number.isFinite(v));

    if (values.length >= 2) {
      const vmin = Math.min(...values);
      const vmax = Math.max(...values);
      if (vmax > vmin) return [vmin, vmax];
    }

    return layerConfig.defaultBounds;
  }, [fineGrid, heatmapMeta, layer, layerConfig, wardSimulations, isThermalMode, thermalOverlay]);

  const [vmin, vmax] = scaleBounds;
  const thermalLegendRamp = isThermalMode ? THERMAL_JET_STOPS : layerConfig.ramp;
  const legendItems = useMemo(
    () => legendStops(thermalLegendRamp, vmin, vmax, isThermalMode ? " K" : layerConfig.unit),
    [thermalLegendRamp, layerConfig, vmin, vmax, isThermalMode]
  );

  const thermalImageCoords = useMemo(() => {
    if (!thermalOverlay?.coordinates) return null;
    return thermalOverlay.coordinates as [
      [number, number], [number, number], [number, number], [number, number]
    ];
  }, [thermalOverlay]);

  const cellValue = useCallback((p: WardProperties) => {
    return layerConfig.getValue(p, wardSimulations, domains, cityKey);
  }, [layerConfig, wardSimulations, domains, cityKey]);

  /* sync pitch into viewState when user clicks a button */
  const applyPitch = useCallback((p: number) => {
    setPitch(p);
    setViewState((v) => ({ ...v, pitch: p }));
  }, []);

  const applyBearing = useCallback((b: number) => {
    setBearing(b);
    setViewState((v) => ({ ...v, bearing: b }));
  }, []);

  /* Thermal view: flat north-up satellite (fixes skewed rectangle overlay) */
  useEffect(() => {
    if (isThermalMode) {
      applyPitch(0);
      applyBearing(0);
      setShowDomains(false);
    }
  }, [isThermalMode, cityKey, applyPitch, applyBearing]);

  useEffect(() => {
    if (hotspots?.features?.length) setShowHotspots(true);
  }, [hotspots]);

  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => setPinIconReady(true);
    img.onerror = () => setPinIconReady(false);
    img.src = "/hotspot-pin.svg";
  }, []);

  /* recenter when city changes */
  const centeredView = useMemo<MapViewState>(() => {
    const b = thermalOverlay?.bounds;
    const lon = b ? (b.west + b.east) / 2 : bbox?.length === 4 ? (bbox[0] + bbox[2]) / 2 : 77.59;
    const lat = b ? (b.south + b.north) / 2 : bbox?.length === 4 ? (bbox[1] + bbox[3]) / 2 : 12.97;
    return {
      longitude: lon,
      latitude:  lat,
      zoom:      isThermalMode ? 11.8 : 11.2,
      pitch:     isThermalMode ? 0 : pitch,
      bearing:   isThermalMode ? 0 : bearing,
      minZoom:   6,
      maxZoom:   18,
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cityKey, bbox, pitch, bearing, isThermalMode, thermalOverlay]);

  /* Use API pixel-aligned grid only — no client-side bbox fallback (misaligns) */
  const displayGrid = useMemo<WardCollection | null>(() => {
    if (fineGrid?.features?.length) return fineGrid;
    return null;
  }, [fineGrid]);

  const handleGridHover = useCallback((info: PickingInfo) => {
    if (info.object && info.x != null && info.y != null) {
      const p = info.object.properties as WardProperties;
      const value = cellValue(p);
      setTooltip({
        x: info.x, y: info.y,
        value,
        valueLabel: layerConfig.tooltipLabel,
        formatted: layerConfig.formatValue(value),
        vuln: p.vulnerability_class,
        name: p.name,
      });
    } else {
      setTooltip(null);
    }
  }, [cellValue, layerConfig]);

  const handleWardHover = useCallback((info: PickingInfo) => {
    if (!showGrid && info.object && info.x != null && info.y != null) {
      const p = info.object.properties as WardProperties;
      const value = cellValue(p);
      setTooltip({
        x: info.x, y: info.y,
        value,
        valueLabel: layerConfig.tooltipLabel,
        formatted: layerConfig.formatValue(value),
        vuln: p.vulnerability_class,
        name: p.name,
      });
    } else if (showGrid) {
      setTooltip(null);
    }
  }, [cellValue, layerConfig, showGrid]);

  /* deck.gl layers */
  const layers = useMemo(() => {
    const out = [];
    const gridVisible = showGrid && !isThermalMode;

    /* ── 3-D extruded regular grid ─────────────────────────────────── */
    if (gridVisible && displayGrid) {
      out.push(
        new GeoJsonLayer<WardProperties>({
          id:                 `grid-3d-${cityKey}-${layer}`,
          data:               displayGrid as FeatureCollection<Polygon, WardProperties>,
          pickable:           true,
          stroked:            true,
          filled:             true,
          extruded:           true,
          wireframe:          true,
          lineWidthMinPixels: 1,
          /* white wire between cells */
          getLineColor:  [255, 255, 255, 25] as [number,number,number,number],
          getFillColor:  (f) => {
            const p = f.properties as WardProperties;
            const value = cellValue(p);
            return valueRgba(value, vmin, vmax, layerConfig.ramp, 235);
          },
          getElevation:  (f) => {
            const p = f.properties as WardProperties;
            const value = cellValue(p);
            return valueElevation(value, vmin, vmax, layer);
          },
          elevationScale: 1,
          updateTriggers: { getFillColor: [wardSimulations, layer, vmin, vmax], getElevation: [wardSimulations, layer, vmin, vmax] },
          onHover:  handleGridHover,
          onClick:  (info: PickingInfo) => {
            if (info.object) onSelectWard(info.object.properties as WardProperties);
            if (info.coordinate) onMapClick(info.coordinate[0], info.coordinate[1]);
          },
        })
      );
    }

    /* ── Named ward outlines (hidden in thermal satellite view) ───── */
    if (showDomains && domains && !isThermalMode) {
      out.push(
        new GeoJsonLayer({
          id:                 `wards-${cityKey}`,
          data:               domains as unknown as FeatureCollection,
          pickable:           !showGrid,
          stroked:            true,
          filled:             true,
          extruded:           false,
          lineWidthMinPixels: 2,
          getLineColor: (f: { properties: WardProperties }) =>
            (selectedWard?.ward_id === f.properties.ward_id
              ? [8, 145, 178, 255]
              : [60, 80, 120, 140]) as [number,number,number,number],
          getFillColor: (_f: unknown) => [0, 0, 0, 0] as [number,number,number,number],
          updateTriggers: { getLineColor: selectedWard?.ward_id },
          onHover: handleWardHover,
          onClick: (info: PickingInfo) => {
            if (info.object) onSelectWard(info.object.properties as WardProperties);
            if (info.coordinate) onMapClick(info.coordinate[0], info.coordinate[1]);
          },
        })
      );
    }

    /* ── Hotspot map-pin layer (always on top of 3-D grid) ─────────── */
    if (showHotspots && hotspots && pinIconReady && hotspots.features.length > 0) {
      const pinData = hotspots.features.filter((f) => f.properties.hotspot_class >= 1);
      out.push(
        new IconLayer<HotspotFeature>({
          id:              `hotspots-${cityKey}`,
          data:            pinData.length ? pinData : hotspots.features,
          getPosition:     (f) => f.geometry.coordinates,
          getIcon:         () => ({
            url: "/hotspot-pin.svg",
            width: 48,
            height: 64,
            anchorY: 64,
            mask: true,
          }),
          getSize:         (f) => (f.properties.hotspot_class >= 2 ? 46 : 38),
          sizeUnits:       "pixels",
          getColor:        (f) =>
            f.properties.hotspot_class >= 2
              ? [255, 23, 68, 255]
              : [255, 166, 0, 255],
          billboard:       true,
          pickable:        true,
          parameters:      { depthTest: false } as any,
          onClick:         (info: PickingInfo<HotspotFeature>) => {
            if (!info.object) return;
            setSelectedHotspot(info.object);
            onMapClick(info.object.geometry.coordinates[0], info.object.geometry.coordinates[1]);
          },
        })
      );
    }

    return out;
  }, [cityKey, layer, layerConfig, cellValue, vmin, vmax, displayGrid, domains, showGrid, isThermalMode, showDomains, showHotspots, hotspots, pinIconReady, wardSimulations, selectedWard, handleGridHover, handleWardHover, onSelectWard, onMapClick]);

  const vulnCls = (v: string) =>
    v === "CRITICAL" ? "text-red-400 font-bold" : v === "HIGH" ? "text-orange-400 font-bold" :
    v === "MODERATE" ? "text-yellow-400 font-bold" : "text-green-400 font-bold";

  const getWardRecommendation = (vuln: string) => {
    const v = vuln.toUpperCase();
    if (v === "CRITICAL") return "🚨 Critical Heat: Paint rooftops white (reflective paint) & prioritize dense street tree planting immediately.";
    if (v === "HIGH") return "⚠️ High Risk: Expand vegetative canopy cover by 20% & establish community pocket parks.";
    if (v === "MODERATE") return "⚡ Moderate: Consider building green roofs or installing local mist/water cooling corridors.";
    return "✅ Low Risk: Maintain current urban vegetation canopy and water bodies.";
  };

  return (
    <div className="relative h-full min-h-0 w-full flex-1">

      {/* ── Controls ──────────────────────────────────────────────────── */}
      <div className="absolute left-3 top-3 z-10 max-h-[80vh] overflow-y-auto rounded-xl border border-slate-700/60 bg-slate-900/95 p-3 text-xs shadow-2xl text-slate-200 backdrop-blur-md">
        <p className="mb-2 font-semibold text-white text-sm">{cityName}</p>

        {LAYER_LABELS.map((l) => (
          <label key={l.id} className="flex cursor-pointer items-center gap-2 py-0.5 text-slate-300 hover:text-white" title={l.tip}>
            <input type="radio" name="mapLayer" checked={layer === l.id} onChange={() => onLayerChange(l.id)} className="accent-cyan-400" />
            {l.label}
          </label>
        ))}

        <div className="my-2 space-y-1.5 border-t border-slate-800 pt-2">
          {!isThermalMode && (
            <label className="flex cursor-pointer items-center gap-2 text-slate-300">
              <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} className="accent-cyan-400" />
              3-D heat grid
            </label>
          )}
          {isThermalMode && (
            <p className="text-[10px] text-cyan-400/90 leading-snug">
              Real Landsat 8 thermal (ST_B10) aligned to satellite imagery. Ocean masked.
            </p>
          )}
          {!isThermalMode && (
            <label className="flex cursor-pointer items-center gap-2 text-slate-300">
              <input type="checkbox" checked={showDomains} onChange={(e) => setShowDomains(e.target.checked)} className="accent-cyan-400" />
              Area outlines
            </label>
          )}
          <label className="flex cursor-pointer items-center gap-2 text-slate-300">
            <input type="checkbox" checked={showHotspots} onChange={(e) => setShowHotspots(e.target.checked)} className="accent-red-500" />
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
              Heat hotspots
            </span>
          </label>
        </div>

        <div className="border-t border-slate-800 pt-2">
          <p className="mb-1 text-[10px] uppercase text-slate-500">View angle</p>
          {isThermalMode ? (
            <p className="text-[10px] text-slate-500">North-up satellite view (fixed)</p>
          ) : (
            <div className="flex gap-1">
              {([0, 30, 45, 60] as number[]).map((p) => (
                <button key={p} type="button" onClick={() => applyPitch(p)}
                  className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                    pitch === p ? "bg-cyan-500 text-slate-900" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                  }`}>
                  {p === 0 ? "Top" : `${p}°`}
                </button>
              ))}
            </div>
          )}
        </div>
        <p className="mt-2 text-[9px] text-slate-500">Drag to rotate · scroll to zoom</p>
      </div>

      {/* ── Selected ward + AIML prediction ─────────────────────────── */}
      {(selectedWard || pointPrediction) && (
        <div className="absolute right-3 top-3 z-10 w-64 rounded-xl border border-slate-700/60 bg-slate-900/95 p-3 text-xs shadow-2xl text-slate-200 backdrop-blur-md">
          {selectedWard && (
            <>
              <p className="text-sm font-semibold text-white">{selectedWard.name}</p>
              <p className={`mt-0.5 text-[10px] font-semibold uppercase ${vulnCls(selectedWard.vulnerability_class)}`}>
                {selectedWard.vulnerability_class}
              </p>
              <table className="mt-2 w-full text-left">
                <tbody>
                  {([
                    ["Satellite LST",  `${selectedWard.avg_lst_c.toFixed(1)}°C`],
                    ["Calibrated LST", `${(selectedWard.lst_calibrated_c ?? selectedWard.avg_lst_c).toFixed(1)}°C`],
                    ["Simulated LST", `${(wardSimulations[selectedWard.ward_id] ?? selectedWard.simulated_lst_c).toFixed(1)}°C`],
                    ["Heat Stress",   `${selectedWard.heat_stress_utci_c.toFixed(1)}°C UTCI`],
                    ["NDVI (Greenery)",  selectedWard.ndvi.toFixed(2)],
                  ] as [string,string][]).map(([lbl, val]) => (
                    <tr key={lbl}>
                      <td className="py-0.5 text-slate-400 text-[11px]">{lbl}</td>
                      <td className="py-0.5 text-right font-mono text-white text-[11px]">{val}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="mt-2.5 rounded bg-slate-800/60 p-2 text-[10px] text-slate-300 leading-relaxed border border-slate-700/40">
                {getWardRecommendation(selectedWard.vulnerability_class)}
              </div>
            </>
          )}

          <div className={`${selectedWard ? "mt-3.5 border-t border-slate-800 pt-3" : ""}`}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-cyan-400">
              AIML Prediction {predicting && <span className="text-slate-500">· running…</span>}
            </p>
            {pointPrediction ? (
              <div className="space-y-2 mt-2">
                <table className="w-full text-left">
                  <tbody>
                    {([
                      ["AI LST",       `${pointPrediction.predicted_lst_c.toFixed(1)}°C`],
                      ["Calibrated LST", `${(pointPrediction.observed_lst_calibrated_c ?? pointPrediction.observed_lst_c).toFixed(1)}°C`],
                      ["Satellite LST", `${pointPrediction.observed_lst_c.toFixed(1)}°C`],
                      ["Hotspot Label", pointPrediction.hotspot_label],
                    ] as [string,string][]).map(([lbl, val]) => (
                      <tr key={lbl}>
                        <td className="py-0.5 text-slate-400 text-[11px]">{lbl}</td>
                        <td className={`py-0.5 text-right font-mono text-[11px] ${
                          lbl === "AI LST" ? "font-bold text-cyan-400" : "text-white"
                        }`}>{val}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Residual explanation */}
                <div className="rounded bg-slate-800/40 p-1.5 text-[9px] text-slate-400 border border-slate-800/80 leading-normal">
                  <span className="font-semibold text-slate-300">Residual: </span>
                  {pointPrediction.residual_c.toFixed(2)}°C
                  <p className="mt-0.5 text-slate-500">
                    {pointPrediction.residual_c > 0.5 
                      ? "💡 Local building features are absorbing more heat than predicted."
                      : pointPrediction.residual_c < -0.5 
                      ? "💡 Local canopy or shade cooling is performing better than predicted."
                      : "💡 Surface matches the regional baseline projection."}
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-1 text-[10px] text-slate-500">Click any map cell for live XGBoost inference</p>
            )}
          </div>

          <button
            type="button"
            onClick={() => onSelectWard(null)}
            className="mt-3.5 block w-full text-center py-1 rounded bg-slate-800 text-[10px] text-slate-400 hover:text-white transition-colors border border-slate-700/40"
          >
            ✕ Close Details
          </button>
        </div>
      )}

      {/* ── Legend ──────────────────────────────────────────────────── */}
      {isThermalMode ? (
        <div className="absolute bottom-3 right-3 z-10 flex items-stretch gap-2 rounded-xl border border-slate-700/60 bg-slate-900/95 px-3 py-2.5 text-[10px] text-slate-200 shadow-2xl backdrop-blur-md">
          <div className="flex flex-col justify-between py-0.5 text-[9px] font-mono text-slate-400">
            <span>{vmax.toFixed(0)}</span>
            <span>{((vmin + vmax) / 2).toFixed(0)}</span>
            <span>{vmin.toFixed(0)}</span>
          </div>
          <div
            className="w-3 rounded-sm"
            style={{
              background: `linear-gradient(to top, ${THERMAL_JET_STOPS.map((s) =>
                `rgb(${s.rgb[0]},${s.rgb[1]},${s.rgb[2]}) ${s.at * 100}%`
              ).join(", ")})`,
            }}
          />
          <div className="flex flex-col justify-center">
            <p className="font-semibold uppercase tracking-wide text-white text-[10px]">LST (K)</p>
            <p className="mt-1 text-[9px] text-slate-500 max-w-[120px] leading-snug">
              {thermalOverlay?.source ?? "Landsat 8 ST_B10"}
            </p>
            {thermalLoading && (
              <p className="mt-1 text-[9px] text-cyan-400/90 animate-pulse">Loading thermal raster…</p>
            )}
            {thermalError && (
              <p className="mt-1 text-[9px] text-amber-400/90">{thermalError}</p>
            )}
          </div>
        </div>
      ) : (
        <div className="absolute bottom-3 left-3 z-10 rounded-xl border border-slate-700/60 bg-slate-900/95 px-3 py-2.5 text-[10px] text-slate-200 shadow-2xl backdrop-blur-md">
          <p className="mb-1.5 font-semibold uppercase tracking-wide text-white">{layerConfig.legendTitle}</p>
          <div
            className="mb-2 h-2.5 w-full rounded-sm"
            style={{
              background: `linear-gradient(to right, ${legendItems.map((item, i) => {
                const pct = (i / Math.max(legendItems.length - 1, 1)) * 100;
                return `rgb(${item.rgb[0]},${item.rgb[1]},${item.rgb[2]}) ${pct}%`;
              }).join(", ")})`,
            }}
          />
          <div className="flex justify-between text-[9px] text-slate-500">
            <span>Low: {legendItems[0]?.label}</span>
            <span>High: {legendItems[legendItems.length - 1]?.label}</span>
          </div>
          <p className="mt-1.5 text-[9px] text-slate-500">{layerConfig.heightNote}</p>
        </div>
      )}

      {/* ── Hover tooltip ─────────────────────────────────────────────── */}
      {tooltip && (
        <div className="pointer-events-none absolute z-20 rounded-lg border border-slate-700/60 bg-slate-950/95 px-2.5 py-1.5 text-xs text-slate-200 shadow-2xl backdrop-blur-sm"
          style={{ left: tooltip.x + 14, top: tooltip.y + 14 }}>
          <p className="font-semibold text-white">{tooltip.name}</p>
          <p className="text-slate-400 mt-0.5">{tooltip.valueLabel}: <span className="font-mono text-white font-bold">{tooltip.formatted}</span></p>
          <p className={`font-semibold text-[10px] mt-0.5 ${vulnCls(tooltip.vuln)}`}>{tooltip.vuln}</p>
        </div>
      )}

      {/* ── DeckGL canvas ─────────────────────────────────────────────── */}
      {selectedHotspot && (
        <div className="absolute bottom-3 right-3 z-20 w-72 rounded-xl border border-red-500/40 bg-slate-950/95 p-3 text-xs text-slate-200 shadow-2xl backdrop-blur-md">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-red-300">Heat Hotspot Pin</p>
              <p className="mt-0.5 text-sm font-bold text-white">
                {selectedHotspot.properties.hotspot_label ??
                  (selectedHotspot.properties.hotspot_class >= 2 ? "Severe hotspot" : "Moderate hotspot")}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setSelectedHotspot(null)}
              className="rounded bg-slate-800 px-2 py-0.5 text-slate-400 hover:text-white"
              aria-label="Close hotspot details"
            >
              ×
            </button>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded bg-slate-900/70 p-2">
              <span className="block text-slate-500">Satellite LST</span>
              <span className="font-mono text-red-300">{selectedHotspot.properties.lst_c.toFixed(1)}°C</span>
            </div>
            <div className="rounded bg-slate-900/70 p-2">
              <span className="block text-slate-500">Hotspot class</span>
              <span className="font-mono text-red-300">{selectedHotspot.properties.hotspot_class}</span>
            </div>
            {selectedHotspot.properties.gi_star_z != null && (
              <div className="rounded bg-slate-900/70 p-2">
                <span className="block text-slate-500">Gi* z-score</span>
                <span className="font-mono text-red-300">{selectedHotspot.properties.gi_star_z.toFixed(2)}</span>
              </div>
            )}
            {selectedHotspot.properties.population != null && selectedHotspot.properties.population > 0 && (
              <div className="rounded bg-slate-900/70 p-2">
                <span className="block text-slate-500">GHSL pop.</span>
                <span className="font-mono text-red-300">
                  {selectedHotspot.properties.population >= 1000
                    ? `${(selectedHotspot.properties.population / 1000).toFixed(1)}k`
                    : selectedHotspot.properties.population.toFixed(0)}
                </span>
              </div>
            )}
          </div>
          <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
            This pin marks a high-temperature pixel detected from the real satellite LST hotspot layer. Click nearby map cells for AIML prediction and residual details.
          </p>
        </div>
      )}

      <DeckGL
        key={`${cityKey}-${layer}`}
        initialViewState={centeredView}
        viewState={viewState}
        onViewStateChange={({ viewState: vs }) => setViewState(vs as MapViewState)}
        controller={{ dragRotate: !isThermalMode, touchRotate: !isThermalMode, keyboard: true }}
        layers={layers}
        style={{ position: "absolute", top: "0", left: "0", right: "0", bottom: "0" }}
      >
        <Map mapStyle={isThermalMode ? SATELLITE_MAP_STYLE : MAP_STYLE}>
          {isThermalMode && thermalImageCoords && (
            <Source
              id="thermal-satellite"
              type="image"
              url={`${thermalOverlayUrl(cityKey)}?v=${thermalOverlay?.width ?? 0}`}
              coordinates={thermalImageCoords}
            >
              <MapLayerGL
                id="thermal-satellite-layer"
                type="raster"
                paint={{ "raster-opacity": 0.9, "raster-fade-duration": 0 }}
              />
            </Source>
          )}
        </Map>
      </DeckGL>
    </div>
  );
}
