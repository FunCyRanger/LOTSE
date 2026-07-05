"""LOTSE Neighborhood dashboard — auto-created on integration setup."""

import logging

from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DASHBOARD_CONFIG = {
    "title": "LOTSE Neighborhood",
    "views": [
        {
            "title": "Grid Stability",
            "path": "grid-stability",
            "badges": [],
            "cards": [
                {
                    "type": "entities",
                    "title": "Power Snapshot",
                    "entities": [
                        "sensor.combined_mesh_gp",
                        "sensor.combined_mesh_sp",
                        "sensor.combined_mesh_bp",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Frequency",
                    "entities": [
                        "sensor.combined_mesh_gf_avg",
                        "sensor.combined_mesh_gf_min",
                        "sensor.combined_mesh_gf_max",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Voltage L1",
                    "entities": [
                        "sensor.combined_mesh_gv1_max",
                        "sensor.combined_mesh_gv1_min",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Voltage L2 / L3",
                    "entities": [
                        "sensor.combined_mesh_gv2_max",
                        "sensor.combined_mesh_gv2_min",
                        "sensor.combined_mesh_gv3_max",
                        "sensor.combined_mesh_gv3_min",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Phase Currents & Power Factor",
                    "entities": [
                        "sensor.combined_mesh_ga1_sum",
                        "sensor.combined_mesh_ga2_sum",
                        "sensor.combined_mesh_ga3_sum",
                        "sensor.combined_mesh_gpf_avg",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Reactive & Apparent Power",
                    "entities": [
                        "sensor.combined_mesh_gq_sum",
                        "sensor.combined_mesh_gs_sum",
                    ],
                },
            ],
        },
        {
            "title": "Cumulative Energy",
            "path": "cumulative-energy",
            "badges": [],
            "cards": [
                {
                    "type": "entities",
                    "title": "Grid (add to Energy Dashboard)",
                    "entities": [
                        "sensor.combined_mesh_gei",
                        "sensor.combined_mesh_geo",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Solar",
                    "entities": [
                        "sensor.combined_mesh_se",
                        "sensor.combined_mesh_se_clean",
                        "sensor.combined_mesh_solar_capacity",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Battery",
                    "entities": [
                        "sensor.combined_mesh_bei",
                        "sensor.combined_mesh_beo",
                        "sensor.combined_mesh_battery_capacity",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Neighborhood",
                    "entities": [
                        "sensor.combined_mesh_bs",
                        "sensor.combined_mesh_soc_weighted",
                        "sensor.combined_mesh_participants",
                        "sensor.combined_mesh_config_ready",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Solar Forecast",
                    "entities": [
                        "sensor.solar_production_forecast",
                        "sensor.combined_mesh_solar_capacity",
                    ],
                },
            ],
        },
    ],
}


async def async_create_lovelace_dashboard(hass: HomeAssistant) -> None:
    if LOVELACE_DOMAIN not in hass.data:
        _LOGGER.warning("Lovelace not available — skipping dashboard creation")
        return
    dashboards = hass.data[LOVELACE_DOMAIN].dashboards
    if dashboards is None:
        return
    try:
        if hasattr(dashboards, "async_items"):
            items = dashboards.async_items()
        elif isinstance(dashboards, dict):
            items = list(dashboards.values())
        else:
            return
    except Exception:
        return

    for d in items:
        if isinstance(d, dict):
            data = d.get("data", {})
        else:
            data = getattr(d, "config", {})
        if isinstance(data, dict) and data.get("title") == "LOTSE Neighborhood":
            return

    config = {
        "id": "lotse_neighborhood",
        "data": DASHBOARD_CONFIG,
    }
    try:
        await dashboards.async_create_item(config)
        _LOGGER.info("Created LOTSE Neighborhood dashboard")
    except AttributeError:
        if isinstance(dashboards, dict):
            dashboards["lotse_neighborhood"] = config
            _LOGGER.info("Created LOTSE Neighborhood dashboard")
    except Exception as exc:
        _LOGGER.warning("Could not create LOTSE dashboard: %s", exc)
