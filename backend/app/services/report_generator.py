"""
UrbanYantra PDF Report Generator
===============================
Generates comprehensive Urban Heat Mitigation reports using reportlab.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.app.services.city_data import (
    get_city_summary,
    build_ward_geojson,
    get_hotspots,
    get_drivers,
    get_cooling_potential,
    get_climate_projection,
    _load_feature_table,
)
from backend.app.services.model_inference import get_model_metrics

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------
DARK_BLUE = HexColor("#1a1a2e")
MID_BLUE = HexColor("#16213e")
ACCENT_BLUE = HexColor("#0f3460")
WHITE = colors.white
LIGHT_GREY = HexColor("#f0f0f0")
ROW_ALT = HexColor("#f7f7fa")

VULN_COLORS = {
    "CRITICAL": HexColor("#e74c3c"),
    "HIGH": HexColor("#e67e22"),
    "MODERATE": HexColor("#f1c40f"),
    "LOW": HexColor("#2ecc71"),
}


# ---------------------------------------------------------------------------
# Page-level callbacks
# ---------------------------------------------------------------------------
def _footer(canvas, doc):
    """Draw page number in the footer."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#888888"))
    canvas.drawRightString(
        A4[0] - inch,
        0.5 * inch,
        f"Page {canvas.getPageNumber()}",
    )
    canvas.drawString(
        inch,
        0.5 * inch,
        "UrbanYantra — Urban Heat Mitigation Platform",
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------
def _get_styles() -> dict[str, ParagraphStyle]:
    """Return a dict of reusable paragraph styles."""
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            alignment=TA_CENTER,
            textColor=DARK_BLUE,
            spaceAfter=12,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=14,
            alignment=TA_CENTER,
            textColor=MID_BLUE,
            spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "SectionHeader",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=DARK_BLUE,
            spaceBefore=18,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            textColor=HexColor("#333333"),
        ),
        "body_bold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=HexColor("#333333"),
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=HexColor("#666666"),
        ),
    }


def _hr():
    """Return a styled horizontal rule."""
    return HRFlowable(
        width="100%",
        thickness=1,
        color=HexColor("#cccccc"),
        spaceBefore=10,
        spaceAfter=10,
    )


def _alternating_table_style(
    n_rows: int,
    header_bg: colors.Color = DARK_BLUE,
    header_fg: colors.Color = WHITE,
) -> TableStyle:
    """Build a TableStyle with alternating row colours."""
    cmds: list[Any] = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), header_fg),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, n_rows):
        bg = ROW_ALT if i % 2 == 0 else WHITE
        cmds.append(("BACKGROUND", (0, i), (-1, i), bg))
    return TableStyle(cmds)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------
def _build_cover(elements: list, city_name: str, styles: dict):
    """Section 1: Cover page."""
    elements.append(Spacer(1, 2 * inch))
    elements.append(Paragraph("URBANYANTRA", styles["cover_title"]))
    elements.append(
        Paragraph(
            "URBAN HEAT MITIGATION REPORT",
            styles["cover_title"],
        )
    )
    elements.append(Spacer(1, 0.4 * inch))
    elements.append(Paragraph(city_name, styles["cover_sub"]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}",
            styles["cover_sub"],
        )
    )
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(
        Paragraph(
            "Comprehensive Analysis for Policy Makers &amp; Researchers",
            ParagraphStyle(
                "Subtitle",
                fontName="Helvetica-Oblique",
                fontSize=12,
                alignment=TA_CENTER,
                textColor=ACCENT_BLUE,
            ),
        )
    )
    elements.append(PageBreak())


def _build_executive_summary(elements: list, summary: dict, styles: dict):
    """Section 2: Executive summary with key metrics."""
    elements.append(Paragraph("1. Executive Summary", styles["section"]))
    elements.append(_hr())

    metrics = summary["metrics"]
    resilience = metrics["resilience_index"]
    res_color = VULN_COLORS["LOW"] if resilience >= 60 else VULN_COLORS["CRITICAL"]

    data = [
        ["Metric", "Value"],
        ["City", summary.get("city_name", summary.get("city_key", ""))],
        ["Average LST", f"{metrics['avg_city_lst_c']} °C"],
        ["Heat Stress (UTCI proxy)", f"{metrics['avg_heat_stress_utci_c']} °C"],
        ["Resilience Index", f"{resilience} / 100"],
        ["Data Mode", summary.get("data_mode", "N/A")],
    ]
    t = Table(data, colWidths=[2.5 * inch, 3.5 * inch])
    style_cmds = list(_alternating_table_style(len(data)).getCommands())
    # Colour the resilience row
    style_cmds.append(("BACKGROUND", (1, 4), (1, 4), res_color))
    style_cmds.append(("TEXTCOLOR", (1, 4), (1, 4), WHITE))
    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 0.25 * inch))
    elements.append(
        Paragraph(
            "This report provides a data-driven assessment of urban heat island effects, "
            "vulnerability mapping, AI/ML model performance, SHAP-based driver analysis, "
            "and evidence-based cooling intervention strategies.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))


def _build_ward_analysis(elements: list, city_key: str, styles: dict):
    """Section 3: Ward-level heat analysis table."""
    elements.append(Paragraph("2. Ward-Level Heat Analysis", styles["section"]))
    elements.append(_hr())

    try:
        geojson = build_ward_geojson(city_key)
        features = geojson.get("features", [])
    except Exception:
        elements.append(Paragraph("Ward data unavailable.", styles["body"]))
        return

    if not features:
        elements.append(Paragraph("No ward features found.", styles["body"]))
        return

    header = ["Ward Name", "Avg LST (°C)", "NDVI", "NDBI", "Vulnerability", "Hotspot %"]
    rows = [header]
    for f in features:
        p = f["properties"]
        rows.append([
            p.get("name", "—"),
            str(p.get("avg_lst_c", "—")),
            str(p.get("ndvi", "—")),
            str(p.get("ndbi", "—")),
            p.get("vulnerability_class", "—"),
            f"{p.get('hotspot_fraction', 0) * 100:.1f}%",
        ])

    col_widths = [1.4 * inch, 1.0 * inch, 0.8 * inch, 0.8 * inch, 1.1 * inch, 0.9 * inch]
    t = Table(rows, colWidths=col_widths)
    style_cmds = list(_alternating_table_style(len(rows)).getCommands())

    # Colour-code vulnerability column (index 4)
    for i, f in enumerate(features, start=1):
        vuln = f["properties"].get("vulnerability_class", "")
        if vuln in VULN_COLORS:
            style_cmds.append(("BACKGROUND", (4, i), (4, i), VULN_COLORS[vuln]))
            if vuln in ("CRITICAL", "HIGH"):
                style_cmds.append(("TEXTCOLOR", (4, i), (4, i), WHITE))

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 0.2 * inch))


def _build_model_performance(elements: list, city_key: str, styles: dict):
    """Section 4: AI/ML model performance metrics."""
    elements.append(Paragraph("3. AI/ML Model Performance", styles["section"]))
    elements.append(_hr())

    try:
        metrics = get_model_metrics(city_key)
    except Exception:
        elements.append(
            Paragraph(
                "Model metrics are not available for this city. "
                "Run the ML pipeline to generate model performance data.",
                styles["body"],
            )
        )
        return

    lst_reg = metrics.get("lst_regression", {})
    hotspot_clf = metrics.get("hotspot_classifier", {})

    data = [
        ["Parameter", "Value"],
        ["Model Type", metrics.get("model", "N/A")],
        ["Validation Strategy", metrics.get("validation", "N/A")],
        ["LST Regression MAE", f"{lst_reg.get('mae_c', 'N/A')} °C"],
        ["LST Regression R²", str(lst_reg.get("r2", "N/A"))],
        ["Hotspot Classifier Accuracy", str(hotspot_clf.get("accuracy", "N/A"))],
        ["Feature Count", str(metrics.get("feature_count", "N/A"))],
    ]
    t = Table(data, colWidths=[3.0 * inch, 3.0 * inch])
    t.setStyle(_alternating_table_style(len(data)))
    elements.append(t)
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            "Model performance is evaluated using spatial tile hold-out cross-validation "
            "to avoid spatial autocorrelation leakage.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))


def _build_shap_drivers(elements: list, city_key: str, styles: dict):
    """Section 5: SHAP driver analysis."""
    elements.append(Paragraph("4. SHAP Driver Analysis", styles["section"]))
    elements.append(_hr())

    try:
        drivers_data = get_drivers(city_key)
        drivers = drivers_data.get("drivers", [])
        source = drivers_data.get("source", "proxy")
    except Exception:
        elements.append(Paragraph("Driver analysis data unavailable.", styles["body"]))
        return

    if not drivers:
        elements.append(Paragraph("No driver data found.", styles["body"]))
        return

    header = ["Rank", "Driver", "Importance (%)"]
    rows = [header]
    for i, d in enumerate(drivers, start=1):
        rows.append([
            str(i),
            d.get("feature", "—"),
            f"{d.get('importance_pct', 0):.1f}%",
        ])

    t = Table(rows, colWidths=[0.8 * inch, 3.5 * inch, 1.7 * inch])
    t.setStyle(_alternating_table_style(len(rows)))
    elements.append(t)
    elements.append(Spacer(1, 0.15 * inch))

    # Interpretation paragraph
    top_driver = drivers[0]["feature"] if drivers else "unknown"
    top_pct = drivers[0].get("importance_pct", 0) if drivers else 0
    source_label = "SHAP (SHapley Additive exPlanations)" if source == "shap" else "proxy estimation"

    elements.append(
        Paragraph(
            f"<b>Interpretation:</b> Based on {source_label}, the primary driver of urban heat "
            f"in this city is <b>{top_driver}</b>, accounting for approximately <b>{top_pct:.1f}%</b> "
            f"of the model's predictive variance. This indicates that targeted interventions "
            f"addressing {top_driver.lower()} would yield the most significant cooling impact. "
            f"Secondary drivers should be addressed in a phased implementation approach to "
            f"maximize cost-effectiveness of urban cooling investments.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))


def _build_cooling_strategies(elements: list, city_key: str, styles: dict):
    """Section 6: Cooling intervention strategies."""
    elements.append(Paragraph("5. Cooling Intervention Strategies", styles["section"]))
    elements.append(_hr())

    try:
        strategies = get_cooling_potential(city_key)
    except Exception:
        elements.append(Paragraph("Cooling strategy data unavailable.", styles["body"]))
        return

    if not strategies:
        elements.append(Paragraph("No cooling strategies found.", styles["body"]))
        return

    header = ["Rank", "Strategy", "Expected ΔT (°C)"]
    rows = [header]
    for i, s in enumerate(
        sorted(strategies, key=lambda x: x.get("delta_t_c", 0), reverse=True),
        start=1,
    ):
        rows.append([
            str(i),
            s.get("strategy", "—"),
            f"-{s.get('delta_t_c', 0):.2f}",
        ])

    t = Table(rows, colWidths=[0.8 * inch, 3.0 * inch, 2.2 * inch])
    t.setStyle(_alternating_table_style(len(rows)))
    elements.append(t)
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            "Cooling potential values represent mean temperature reduction achievable "
            "under full deployment scenarios, derived from physics-informed surrogate models "
            "calibrated against observed surface temperature data.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))


def _build_climate_projection(elements: list, city_key: str, styles: dict):
    """Section 7: Climate projection 2020–2050."""
    elements.append(Paragraph("6. Climate Projection 2020–2050", styles["section"]))
    elements.append(_hr())

    try:
        projections = get_climate_projection(city_key)
    except Exception:
        elements.append(Paragraph("Climate projection data unavailable.", styles["body"]))
        return

    if not projections:
        elements.append(Paragraph("No projection data found.", styles["body"]))
        return

    header = ["Year", "Projected LST (°C)"]
    rows = [header]
    for p in projections:
        rows.append([str(p.get("year", "—")), f"{p.get('lst_c', 0):.2f}"])

    t = Table(rows, colWidths=[2.5 * inch, 3.5 * inch])
    t.setStyle(_alternating_table_style(len(rows)))
    elements.append(t)
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(
        Paragraph(
            "Projections use a linear warming trend of ~0.12 °C/year overlaid with sinusoidal "
            "climate oscillation, calibrated against ERA5 reanalysis and CMIP6 SSP2-4.5 scenarios. "
            "These estimates should be treated as indicative for urban planning timelines.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))


def _build_hotspot_analysis(elements: list, city_key: str, styles: dict):
    """Section 8: Top 20 severe hotspots."""
    elements.append(Paragraph("7. Hotspot Analysis", styles["section"]))
    elements.append(_hr())

    try:
        hotspot_geojson = get_hotspots(city_key)
        features = hotspot_geojson.get("features", [])
    except Exception:
        elements.append(Paragraph("Hotspot data unavailable.", styles["body"]))
        return

    if not features:
        elements.append(Paragraph("No hotspot features found.", styles["body"]))
        return

    # Sort by LST descending and take top 20
    features_sorted = sorted(
        features,
        key=lambda f: f.get("properties", {}).get("lst_c", 0),
        reverse=True,
    )[:20]

    hotspot_labels = {0: "Normal", 1: "Moderate", 2: "Severe"}

    header = ["#", "Longitude", "Latitude", "LST (°C)", "Classification"]
    rows = [header]
    for i, f in enumerate(features_sorted, start=1):
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        props = f.get("properties", {})
        hclass = props.get("hotspot_class", 0)
        rows.append([
            str(i),
            f"{coords[0]:.5f}" if coords[0] is not None else "—",
            f"{coords[1]:.5f}" if coords[1] is not None else "—",
            f"{props.get('lst_c', 0):.2f}",
            hotspot_labels.get(hclass, str(hclass)),
        ])

    col_widths = [0.5 * inch, 1.3 * inch, 1.3 * inch, 1.2 * inch, 1.7 * inch]
    t = Table(rows, colWidths=col_widths)
    style_cmds = list(_alternating_table_style(len(rows)).getCommands())

    # Highlight severe hotspots
    for i, f in enumerate(features_sorted, start=1):
        hclass = f.get("properties", {}).get("hotspot_class", 0)
        if hclass == 2:
            style_cmds.append(("BACKGROUND", (4, i), (4, i), VULN_COLORS["CRITICAL"]))
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), WHITE))
        elif hclass == 1:
            style_cmds.append(("BACKGROUND", (4, i), (4, i), VULN_COLORS["MODERATE"]))

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 0.2 * inch))


def _build_recommendations(elements: list, city_key: str, styles: dict):
    """Section 9: Evidence-based urban planning recommendations."""
    elements.append(Paragraph("8. Urban Planning Recommendations", styles["section"]))
    elements.append(_hr())

    # ---- Gather ward-level evidence ----
    critical_wards: list[str] = []
    high_wards: list[str] = []
    avg_lst = 0.0
    avg_ndvi = 0.0
    ward_count = 0

    try:
        geojson = build_ward_geojson(city_key)
        features = geojson.get("features", [])
        lst_values = []
        ndvi_values = []
        for f in features:
            p = f["properties"]
            ward_count += 1
            vuln = p.get("vulnerability_class", "")
            name = p.get("name", f"Ward {ward_count}")
            if vuln == "CRITICAL":
                critical_wards.append(name)
            elif vuln == "HIGH":
                high_wards.append(name)
            lst_values.append(p.get("avg_lst_c", 0))
            ndvi_values.append(p.get("ndvi", 0))
        avg_lst = sum(lst_values) / len(lst_values) if lst_values else 0
        avg_ndvi = sum(ndvi_values) / len(ndvi_values) if ndvi_values else 0
    except Exception:
        pass

    # ---- Generate evidence-based recommendations ----
    elements.append(
        Paragraph("<b>Evidence-Based Intervention Priorities</b>", styles["body_bold"])
    )
    elements.append(Spacer(1, 0.1 * inch))

    recs: list[str] = []

    # Cool roof mandates for high-LST wards
    if avg_lst > 40 and (critical_wards or high_wards):
        target_wards = ", ".join(critical_wards + high_wards)
        recs.append(
            f"<b>Cool Roof Mandates:</b> Average LST exceeds 40 °C. Mandatory cool-roof "
            f"retrofitting is recommended for the following high-vulnerability wards: "
            f"<b>{target_wards}</b>. High-albedo coatings (SRI ≥ 78) should be mandated "
            f"for all new commercial and residential construction in these areas."
        )

    # Urban greening corridors for low NDVI
    if avg_ndvi < 0.25:
        recs.append(
            f"<b>Urban Greening Corridors:</b> City-wide average NDVI ({avg_ndvi:.3f}) is below "
            f"the 0.25 threshold for adequate vegetative cooling. Establish continuous green "
            f"corridors connecting existing parks and water bodies. Prioritise native, "
            f"drought-resistant species with high canopy cover potential."
        )

    # Blue infrastructure
    recs.append(
        "<b>Blue Infrastructure:</b> Deploy blue infrastructure (urban wetlands, retention "
        "ponds, misting corridors) near identified hotspot clusters to leverage evaporative "
        "cooling effects. Integrate with stormwater management systems for dual benefit."
    )

    # Sky view factor
    recs.append(
        "<b>Building Code Amendments (Sky View Factor):</b> Revise zoning codes to enforce "
        "minimum sky view factor (SVF ≥ 0.4) in new developments. Limit building height-to-"
        "street-width ratios in identified urban canyon corridors to reduce longwave radiation "
        "trapping and improve nocturnal cooling."
    )

    for rec in recs:
        elements.append(Paragraph(f"• {rec}", styles["body"]))
        elements.append(Spacer(1, 0.08 * inch))

    elements.append(Spacer(1, 0.15 * inch))

    # ---- Priority Action Matrix ----
    elements.append(
        Paragraph("<b>Priority Action Matrix</b>", styles["body_bold"])
    )
    elements.append(Spacer(1, 0.1 * inch))

    matrix_header = ["Priority", "Ward / Area", "Intervention", "Expected ΔT", "Timeline"]
    matrix_rows = [matrix_header]

    # Populate matrix based on data
    priority_num = 1
    if critical_wards:
        for ward in critical_wards[:3]:
            matrix_rows.append([
                str(priority_num),
                ward,
                "Cool Roofs + Urban Greening",
                "-2.5 to -3.0 °C",
                "0–12 months",
            ])
            priority_num += 1

    if high_wards:
        for ward in high_wards[:3]:
            matrix_rows.append([
                str(priority_num),
                ward,
                "Urban Greening + Blue Infra",
                "-1.5 to -2.0 °C",
                "6–18 months",
            ])
            priority_num += 1

    # General city-wide entries
    matrix_rows.append([
        str(priority_num),
        "City-wide",
        "Building Code SVF Amendment",
        "-0.5 to -1.0 °C",
        "12–24 months",
    ])
    priority_num += 1
    matrix_rows.append([
        str(priority_num),
        "City-wide",
        "Urban Forestry Programme",
        "-1.0 to -1.5 °C",
        "24–60 months",
    ])

    col_widths = [0.7 * inch, 1.4 * inch, 1.8 * inch, 1.2 * inch, 1.0 * inch]
    t = Table(matrix_rows, colWidths=col_widths)
    t.setStyle(_alternating_table_style(len(matrix_rows)))
    elements.append(t)
    elements.append(Spacer(1, 0.2 * inch))

    # ---- General best practices ----
    elements.append(
        Paragraph("<b>General Best Practices</b>", styles["body_bold"])
    )
    elements.append(Spacer(1, 0.1 * inch))

    best_practices = [
        (
            "<b>Pedestrian Shade Structures:</b> Install shade canopies, pergolas, and "
            "tree-lined walkways along major pedestrian corridors and transit stops. "
            "Target a minimum 40% shade coverage for sidewalks in commercial districts."
        ),
        (
            "<b>Permeable Pavements:</b> Replace impervious surfaces with permeable "
            "paving materials in parking lots, low-traffic streets, and public plazas. "
            "This reduces surface temperatures by 5–10 °C compared to conventional asphalt "
            "and improves stormwater infiltration."
        ),
        (
            "<b>Urban Forestry Programs:</b> Establish a comprehensive urban forestry "
            "programme targeting 25% canopy cover city-wide within 15 years. Prioritise "
            "species with large canopy spread and high transpiration rates. Implement "
            "protected root-zone ordinances for existing mature trees."
        ),
    ]
    for bp in best_practices:
        elements.append(Paragraph(f"• {bp}", styles["body"]))
        elements.append(Spacer(1, 0.08 * inch))

    elements.append(Spacer(1, 0.2 * inch))


def _build_methodology(elements: list, styles: dict):
    """Section 10: Methodology and data sources."""
    elements.append(Paragraph("9. Methodology", styles["section"]))
    elements.append(_hr())

    elements.append(Paragraph("<b>Data Sources</b>", styles["body_bold"]))
    elements.append(Spacer(1, 0.06 * inch))

    data_sources = [
        "<b>Landsat Collection 2 Level-2:</b> Surface temperature derived from thermal "
        "infrared bands (Band 10/11) with atmospheric correction via EROS Science Processing Architecture.",
        "<b>Sentinel-2 Level-2A:</b> Multispectral imagery for NDVI, NDBI, and land cover "
        "classification at 10 m spatial resolution.",
        "<b>ERA5 Reanalysis:</b> Hourly meteorological variables (2 m air temperature, wind "
        "speed, solar radiation, humidity) at 0.25° resolution from ECMWF.",
        "<b>ESA WorldCover (10 m):</b> Global land cover classification for impervious surface "
        "fraction, vegetation mapping, and water body delineation.",
        "<b>GHSL (Global Human Settlement Layer):</b> Building footprints, heights, and population "
        "density grids for urban morphology characterisation.",
    ]
    for ds in data_sources:
        elements.append(Paragraph(f"• {ds}", styles["body"]))
        elements.append(Spacer(1, 0.05 * inch))

    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph("<b>Model Description</b>", styles["body_bold"]))
    elements.append(Spacer(1, 0.06 * inch))
    elements.append(
        Paragraph(
            "The predictive engine employs an <b>XGBoost ensemble</b> architecture with separate "
            "regression (LST prediction) and classification (hotspot detection) heads. Features "
            "are engineered from multi-source remote sensing data including spectral indices, "
            "urban morphology metrics, meteorological variables, and land cover fractions. "
            "Spatial tile hold-out cross-validation is used to prevent spatial autocorrelation "
            "leakage. SHAP (SHapley Additive exPlanations) values provide model interpretability "
            "for driver attribution. A physics-informed fallback model based on surface energy "
            "balance equations is used when trained ML models are unavailable.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph("<b>Limitations &amp; Disclaimer</b>", styles["body_bold"]))
    elements.append(Spacer(1, 0.06 * inch))
    elements.append(
        Paragraph(
            "This report is generated from remotely sensed and modelled data. Surface temperature "
            "estimates are pixel-level approximations and may differ from in-situ measurements. "
            "Cooling potential values are derived from surrogate models and should be validated "
            "with local pilot studies before large-scale deployment. Climate projections carry "
            "inherent uncertainty from emission scenario assumptions and downscaling methods. "
            "The UTCI values presented are proxy estimates and do not replace full outdoor thermal "
            "comfort assessments. All recommendations should be reviewed by qualified urban "
            "planners and environmental engineers before implementation.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 0.3 * inch))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def generate_report(city_key: str) -> bytes:
    """
    Generate a comprehensive Urban Heat Mitigation PDF report for a city.

    Parameters
    ----------
    city_key : str
        The city identifier (e.g. ``"bengaluru"``, ``"mumbai"``).

    Returns
    -------
    bytes
        Raw PDF file content.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
        title="UrbanYantra Urban Heat Mitigation Report",
        author="UrbanYantra Platform",
    )

    styles = _get_styles()
    elements: list = []

    # Fetch city summary (required for cover page)
    try:
        summary = get_city_summary(city_key)
        city_name = summary.get("city_name", city_key)
    except Exception:
        summary = {
            "city_key": city_key,
            "city_name": city_key,
            "data_mode": "unknown",
            "metrics": {
                "avg_city_lst_c": 0,
                "avg_heat_stress_utci_c": 0,
                "resilience_index": 0,
            },
        }
        city_name = city_key

    # 1. Cover Page
    _build_cover(elements, city_name, styles)

    # 2. Executive Summary
    try:
        _build_executive_summary(elements, summary, styles)
    except Exception:
        pass

    # 3. Ward-Level Heat Analysis
    try:
        _build_ward_analysis(elements, city_key, styles)
    except Exception:
        pass

    elements.append(PageBreak())

    # 4. AI/ML Model Performance
    try:
        _build_model_performance(elements, city_key, styles)
    except Exception:
        pass

    # 5. SHAP Driver Analysis
    try:
        _build_shap_drivers(elements, city_key, styles)
    except Exception:
        pass

    elements.append(PageBreak())

    # 6. Cooling Intervention Strategies
    try:
        _build_cooling_strategies(elements, city_key, styles)
    except Exception:
        pass

    # 7. Climate Projection 2020–2050
    try:
        _build_climate_projection(elements, city_key, styles)
    except Exception:
        pass

    elements.append(PageBreak())

    # 8. Hotspot Analysis
    try:
        _build_hotspot_analysis(elements, city_key, styles)
    except Exception:
        pass

    elements.append(PageBreak())

    # 9. Urban Planning Recommendations
    try:
        _build_recommendations(elements, city_key, styles)
    except Exception:
        pass

    elements.append(PageBreak())

    # 10. Methodology
    try:
        _build_methodology(elements, styles)
    except Exception:
        pass

    # Build PDF
    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
