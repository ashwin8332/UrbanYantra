"""
LLM-powered chat service for UrbanYantra.

Uses the OpenRouter API (google/gemini-2.0-flash-001) to provide
context-aware, analytical responses about urban heat islands.
Falls back to the rule-based chat_response when the API is unavailable.
"""

import logging
import os
import requests
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — set OPENROUTER_API_KEY on HF Space / Render (never commit keys)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash"
APP_REFERER = os.environ.get(
    "APP_PUBLIC_URL",
    os.environ.get("CORS_ALLOW_ORIGINS", "https://urban-yantra.vercel.app").split(",")[0].strip(),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_llm_available() -> bool:
    """Quick check if OpenRouter API key is configured."""
    return bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-"))


def _build_city_context(city_key: str) -> str:
    """Aggregate all available city data into a context string for the LLM."""

    from backend.app.services.city_data import (
        get_city_summary,
        get_drivers,
        get_cooling_potential,
        get_climate_projection,
    )

    sections: list[str] = []

    # --- City summary --------------------------------------------------
    try:
        summary = get_city_summary(city_key)
        metrics = summary.get("metrics", {})
        sections.append(
            "## City Summary\n"
            f"- **City**: {summary.get('city_name', city_key)}\n"
            f"- **Data Mode**: {summary.get('data_mode', 'unknown')}\n"
            f"- **Average LST**: {metrics.get('avg_city_lst_c', 'N/A')}°C\n"
            f"- **Heat Stress (UTCI)**: {metrics.get('avg_heat_stress_utci_c', 'N/A')}°C\n"
            f"- **Resilience Index**: {metrics.get('resilience_index', 'N/A')}/100\n"
            f"- **CO₂ Sequestration**: {metrics.get('co2_sequestration_tons_yr', 0)} tons/yr"
        )
    except Exception:
        pass

    # --- UHI drivers ---------------------------------------------------
    try:
        drivers_data = get_drivers(city_key)
        driver_list = drivers_data.get("drivers", [])
        if driver_list:
            lines = [f"- {d['feature']}: {d['importance_pct']}%" for d in driver_list]
            sections.append("## UHI Drivers (SHAP Importance)\n" + "\n".join(lines))
    except Exception:
        pass

    # --- Cooling potential / strategies --------------------------------
    try:
        cooling = get_cooling_potential(city_key)
        if cooling:
            lines = [f"- {s['strategy']}: {s['delta_t_c']}°C cooling" for s in cooling]
            sections.append("## Cooling Strategies & Potential\n" + "\n".join(lines))
    except Exception:
        pass

    # --- Climate projection --------------------------------------------
    try:
        projection = get_climate_projection(city_key)
        if projection:
            lines = [f"- Year {p['year']}: {p['lst_c']}°C" for p in projection]
            sections.append("## Climate Projection (2020-2050)\n" + "\n".join(lines))
    except Exception:
        pass

    # --- ML model metrics (optional) -----------------------------------
    try:
        from backend.app.services.model_inference import get_model_metrics

        metrics = get_model_metrics(city_key)
        if metrics:
            lst_reg = metrics.get("lst_regression", {})
            hotspot = metrics.get("hotspot_classifier", {})
            sections.append(
                "## ML Model Performance Metrics\n"
                f"- **Model**: {metrics.get('model', 'Unknown')}\n"
                f"- **LST MAE**: {lst_reg.get('mae_c', 'N/A')}°C\n"
                f"- **LST R²**: {lst_reg.get('r2', 'N/A')}\n"
                f"- **Hotspot Accuracy**: {hotspot.get('accuracy', 'N/A')}\n"
                f"- **Features**: {metrics.get('feature_count', 'N/A')}"
            )
    except Exception:
        pass  # model_inference may not be available

    return "\n\n".join(sections) if sections else "No city data available."


def _build_system_prompt(city_key: str) -> str:
    """Construct the system prompt with role instructions and city context."""

    city_context = _build_city_context(city_key)

    return (
        "You are **UrbanYantra AI**, an expert urban heat island (UHI) analyst "
        "and climate adaptation advisor. You have deep knowledge of remote "
        "sensing, land-surface temperature modelling, urban planning, and "
        "nature-based cooling interventions.\n\n"
        "# Your Data Context\n"
        f"{city_context}\n\n"
        "# Instructions\n"
        "1. **Evidence-based answers** – Always ground your responses in the "
        "data provided above. Cite specific numbers, percentages, and metrics "
        "when available.\n"
        "2. **Recommend interventions** – When relevant, suggest concrete "
        "cooling strategies (green roofs, urban forestry, cool pavements, "
        "water features) and estimate their potential impact using the "
        "Cooling Strategies data.\n"
        "3. **Dual audience support** – If the user appears to be a "
        "researcher or technical professional, provide detailed technical "
        "analysis with proper terminology. If the user seems to be a general "
        "audience member, use plain language with helpful analogies.\n"
        "4. **Climate projections** – When discussing future scenarios, "
        "reference the Climate Projection data and explain implications.\n"
        "5. **Stay on topic** – Focus on urban heat, climate adaptation, and "
        "the specific city being analysed. Politely redirect off-topic "
        "questions.\n"
        "6. **Reports** – If the user asks you to generate, create, or "
        "download a report, let them know they can click the **Download "
        "Report** button in the application interface to get a comprehensive "
        "PDF report.\n"
        "7. Keep responses concise but thorough. Use markdown formatting "
        "(headings, bullet points, bold) for readability.\n"
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def llm_chat_response(
    message: str,
    city_key: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """Return an LLM-generated response; falls back to rule-based chat on error.

    Parameters
    ----------
    message:
        The latest user message.
    city_key:
        Identifier for the city (e.g. ``"delhi"``, ``"mumbai"``).
    conversation_history:
        Optional list of prior ``{"role": ..., "content": ...}`` dicts.

    Returns
    -------
    str
        The assistant's reply.
    """

    # Import fallback early so it's always available
    from backend.app.services.city_data import chat_response as rule_based_chat

    if not is_llm_available():
        return rule_based_chat(message, city_key)

    try:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _build_system_prompt(city_key)},
        ]

        # Append recent conversation history (last 10 messages)
        if conversation_history:
            messages.extend(conversation_history[-10:])

        # Append the current user message
        messages.append({"role": "user", "content": message})

        # ---- Call OpenRouter API --------------------------------------
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": APP_REFERER,
            "X-Title": "UrbanYantra",
        }

        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as exc:
        logger.warning("OpenRouter LLM failed, using rule-based fallback: %s", exc)
        return rule_based_chat(message, city_key)
