export interface CityInfo {
  city_key: string;
  city_name: string;
  state?: string;
  has_data: boolean;
  avg_lst_c: number | null;
}

export interface CitySummary {
  city_key: string;
  city_name: string;
  bbox: number[];
  data_mode: string;
  grid_resolution_m?: number;
  ward_boundaries?: string;
  calibration?: {
    bias_c: number;
    method: string;
    station_count: number;
  };
  metrics: {
    avg_city_lst_c: number;
    avg_heat_stress_utci_c: number;
    resilience_index: number;
    co2_sequestration_tons_yr: number;
    total_investment_m_usd: number;
  };
  is_real_data?: boolean;
  fetch_errors?: string[];
  data_sources?: Record<string, string>;
  artifacts_present?: Record<string, boolean>;
}

export interface WardProperties {
  ward_id: string;
  name: string;
  avg_lst_c: number;
  simulated_lst_c: number;
  heat_stress_utci_c: number;
  cooling_delta_c: number;
  ndvi: number;
  ndbi: number;
  vulnerability_class: string;
  hotspot_fraction: number;
  impervious_frac?: number;
  building_density?: number;
  population?: number;
  ghsl_built?: number;
  ghsl_smod?: number;
  lcz_class?: number;
  lst_calibrated_c?: number;
  boundary_source?: string;
  hotspot_class?: number;
}

export interface WardFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: WardProperties;
}

export interface WardCollection {
  type: "FeatureCollection";
  features: WardFeature[];
  meta?: { grid_step: number; rows: number; cols: number; cell_count: number };
}

export interface HeatmapMeta {
  layer: string;
  bounds: [[number, number], [number, number]];
  vmin: number;
  vmax: number;
  width: number;
  height: number;
  grid_step: number;
  unit?: string;
  source?: string;
  data_available?: boolean;
  error?: string;
}

export interface ThermalOverlayMeta {
  city_key: string;
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
  bounds: { west: number; south: number; east: number; north: number };
  vmin_k: number;
  vmax_k: number;
  unit: string;
  source: string;
  width: number;
  height: number;
}

export interface ThermalTilesMeta {
  city_key: string;
  tile_url: string;
  vmin_k: number;
  vmax_k: number;
  unit: string;
  source: string;
  palette?: string[];
  bounds: { west: number; south: number; east: number; north: number };
  coordinates?: [[number, number], [number, number], [number, number], [number, number]];
  overlay_url?: string;
}

export interface SamplePoint {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    lst_c: number;
    zone: string;
    cluster: string;
    hotspot_class: number;
    ndvi: number;
  };
}

export interface SamplePointCollection {
  type: "FeatureCollection";
  features: SamplePoint[];
  meta?: { stride: number; point_count: number; grid_size: string };
}

export interface Driver {
  feature: string;
  importance_pct: number;
}

export interface DataAuditItem {
  dataset_id: string;
  name: string;
  status: string;
  source: string;
  used_for: string;
  is_real: boolean;
}

export interface DataAudit {
  city_key: string;
  data_mode: string;
  synthetic_used: boolean;
  has_fetch_errors?: boolean;
  fetch_errors?: string[];
  datasets: DataAuditItem[];
}

export interface BenchmarkSummary {
  kaggle_uhi?: {
    rows: number;
    columns?: string[];
    temperature_mean_c?: number | null;
    land_cover_classes?: number | null;
    source: string;
    note?: string;
  };
  ey_uhi?: {
    rows: number;
    uhi_index_mean?: number | null;
    uhi_index_std?: number | null;
    lon_range?: number[] | null;
    lat_range?: number[] | null;
    source: string;
    note?: string;
  };
  training_pipeline?: {
    city_metrics?: Record<string, number>;
    external_baselines?: {
      kaggle_uhi?: { mae_c?: number; r2?: number; rows?: number };
      ey_uhi?: { mae?: number; r2?: number; rows?: number };
    };
  };
}

export interface UspMetrics {
  tree_green_cooling: {
    avg_potential_c: number;
    max_potential_c: number;
    description: string;
  };
  carbon_mitigation: {
    co2_tons_yr: number;
    description: string;
  };
  urban_planning: {
    avg_priority: number;
    high_priority_pixel_pct: number;
    top_zones: {
      name: string;
      lon: number;
      lat: number;
      planning_priority: number;
      lst_c: number;
      ndvi: number;
    }[];
    description: string;
  };
}

export interface CoolingStrategy {
  strategy: string;
  delta_t_c: number;
}

export interface ClimatePoint {
  year: number;
  lst_c: number;
}

export interface ScenarioResult {
  mean_cooling_delta_c: number;
  simulated_avg_lst_c: number;
  baseline_avg_lst_c: number;
  simulated_utci_c: number;
  co2_sequestration_tons_yr: number;
  total_investment_m_usd: number;
  ward_updates: { ward_id: string; simulated_lst_c: number; cooling_delta_c: number }[];
}

export type MapLayer = "lst" | "thermal" | "utci" | "ndvi" | "svf" | "ghsl_built" | "ghsl_population" | "ghsl_smod" | "vulnerability";

export interface SimulationState {
  coolRoofs: number;
  greenRoofs: number;
  urbanGreening: number;
  blueInfra: number;
  budget: number;
  targetWard: string;
}

export interface ModelMetrics {
  city_key: string;
  model: string;
  validation: string;
  lst_regression: {
    mae_c: number;
    r2: number;
    rf_mae_c: number;
    rf_r2: number;
  };
  hotspot_classifier: {
    accuracy: number;
  };
  feature_count: number;
}

export interface PointPrediction {
  city_key: string;
  lon: number;
  lat: number;
  pixel_lon: number;
  pixel_lat: number;
  observed_lst_c: number;
  observed_lst_calibrated_c?: number;
  predicted_lst_c: number;
  residual_c: number;
  observed_hotspot_class: number;
  predicted_hotspot_class: number;
  hotspot_label: string;
  probabilities: { class: number; label: string; probability: number }[];
  lst_model: string;
  hotspot_model: string;
}

// Phase 2 — Hotspot overlay
export interface HotspotFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    hotspot_id: string;
    lst_c: number;
    hotspot_class: number;
    hotspot_label?: string;
    gi_star_z?: number;
    ndvi?: number;
    population?: number;
  };
}

export interface HotspotCollection {
  type: "FeatureCollection";
  features: HotspotFeature[];
}

export interface InterventionRanking {
  rank: number;
  intervention_type: string;
  intervention_description?: string;
  lon: number;
  lat: number;
  estimated_temp_reduction_c: number;
  cost_effectiveness_score?: number;
  implementation_complexity?: string;
  confidence?: string;
  baseline_lst_c?: number;
  post_lst_c?: number;
  target_row?: number;
  target_col?: number;
}

export interface ScenarioComparisonEntry {
  name: string;
  icon: string;
  temperature_c: number;
  temp_reduction_c: number;
  carbon_reduction_pct: number;
  estimated_cost_m_usd: number;
  heat_stress_reduction_pct: number;
  population_benefited: number;
  overall_score: number;
  utci_c: number;
  co2_tons_yr: number;
  ward_updates: { ward_id: string; simulated_lst_c: number; cooling_delta_c: number }[];
  reasoning: string[];
  inputs: {
    cool_roofs: number;
    green_roofs: number;
    urban_greening: number;
    blue_infra: number;
  };
}

export interface ScenarioComparisonResult {
  city_key: string;
  baseline_lst_c: number;
  scenarios: ScenarioComparisonEntry[];
  recommendation: {
    strategy: string;
    reason: string;
    confidence_pct: number;
  };
}

