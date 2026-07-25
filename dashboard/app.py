"""Streamlit dashboard for interactive map viewing and scenario sliders."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from simulation.fit_surrogate import predict_surrogate
from utils import list_city_keys, load_city_config

ROOT = Path(__file__).resolve().parent.parent
CITIES_YAML = ROOT / "configs" / "cities.yaml"
DEFAULT_OUT = ROOT / "outputs" / "pune"


@st.cache_data
def load_raster(path: str):
    import rasterio

    with rasterio.open(path) as src:
        return src.read(1), src.bounds


def main():
    st.set_page_config(page_title="Urban Heat Mitigation", layout="wide")
    st.title("Optimizing Urban Heat Mitigation — Demo Dashboard")

    city_keys = list_city_keys(CITIES_YAML) if CITIES_YAML.exists() else []
    if city_keys:
        selected = st.sidebar.selectbox("City", city_keys, index=city_keys.index("Pune") if "Pune" in city_keys else 0)
        cfg = load_city_config(CITIES_YAML, selected)
        out_dir = Path(cfg["output_dir"])
        city = cfg["city_name"]
    else:
        out_dir = Path(st.sidebar.text_input("Output directory", str(DEFAULT_OUT)))
        city = "Pilot City"

    if not out_dir.exists():
        st.warning("Run pipeline first: `py run_pipeline.py --city Mumbai` or `--config configs/pilot_city.yaml`")
        st.stop()

    st.subheader(city)

    col1, col2, col3 = st.columns(3)
    lst_path = out_dir / "rasters" / "lst_10m.tif"
    hotspot_path = out_dir / "maps" / "hotspot_class.tif"
    driver_path = out_dir / "rasters" / "driver_attribution.tif"

    if lst_path.exists():
        lst, _ = load_raster(str(lst_path))
        col1.image(lst, clamp=True, caption="LST (°C) — 10 m", use_container_width=True)

    if hotspot_path.exists():
        hs, _ = load_raster(str(hotspot_path))
        col2.image(hs, clamp=True, caption="Hotspot class (Gi* + LST; 0=normal, 1=moderate, 2=severe)", use_container_width=True)

    if driver_path.exists():
        drv, _ = load_raster(str(driver_path))
        col3.image(drv, clamp=True, caption="Driver attribution (feature code)", use_container_width=True)

    surrogate_path = out_dir / "simulation" / "surrogate_delta_t.joblib"
    if surrogate_path.exists():
        st.markdown("### Scenario simulator (surrogate model)")
        st.caption("Instant ΔT estimates — trained offline from InVEST-inspired sweeps.")
        c1, c2, c3 = st.columns(3)
        canopy = c1.slider("Tree canopy increase (%)", 0, 50, 25) / 100.0
        albedo = c2.slider("Cool-roof albedo increase", 0.0, 0.35, 0.15)
        water = c3.slider("Water feature area increase (%)", 0, 15, 5) / 100.0
        delta_t = predict_surrogate(canopy, albedo, water, surrogate_path)
        st.metric("Estimated mean cooling ΔT", f"{-delta_t:.2f} °C", help="Negative ΔT = cooling")

    st.markdown("### Scenario comparison")
    sim_dir = out_dir / "simulation"
    if sim_dir.exists():
        for png in sorted(sim_dir.glob("scenario_*.png")):
            st.image(str(png), caption=png.stem, use_container_width=True)

    rec_path = out_dir / "tables" / "intervention_rankings.csv"
    if rec_path.exists():
        st.markdown("### Ranked interventions")
        st.dataframe(pd.read_csv(rec_path).head(30), use_container_width=True)

    metrics_path = out_dir / "models" / "metrics.json"
    loo_path = ROOT / "outputs" / "multi_city" / "models" / "loo_cv_metrics.json"
    if metrics_path.exists() or loo_path.exists():
        st.markdown("### Model metrics")
        if metrics_path.exists():
            st.json(json.loads(metrics_path.read_text(encoding="utf-8")))
        if loo_path.exists():
            st.markdown("**Leave-one-city-out CV**")
            st.json(json.loads(loo_path.read_text(encoding="utf-8")))

    shap_path = out_dir / "explainability" / "shap_global_importance.png"
    if shap_path.exists():
        st.markdown("### SHAP global importance")
        st.image(str(shap_path), use_container_width=True)


if __name__ == "__main__":
    main()
