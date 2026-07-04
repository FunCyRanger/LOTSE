"""LOTSE Neighborhood dashboard — auto-created on integration setup."""

import logging

from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DASHBOARD_CONFIG = {
    "title": "LOTSE Neighborhood",
    "views": [
        {
            "title": "Combined Mesh",
            "path": "combined-mesh",
            "badges": [],
            "cards": [
                {
                    "type": "entities",
                    "title": "Grid Power",
                    "entities": [
                        "sensor.combined_mesh_gp",
                        "sensor.combined_mesh_gip",
                        "sensor.combined_mesh_gep",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Solar",
                    "entities": [
                        "sensor.combined_mesh_sp",
                        "sensor.combined_mesh_solar_capacity",
                        "sensor.combined_solar_utilization",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Cumulative Energy (add to Energy Dashboard)",
                    "entities": [
                        "sensor.combined_mesh_gei",
                        "sensor.combined_mesh_geo",
                        "sensor.combined_mesh_se",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Neighborhood",
                    "entities": [
                        "sensor.combined_mesh_bs",
                        "sensor.combined_mesh_soc_weighted",
                        "sensor.combined_mesh_battery_capacity",
                        "sensor.combined_mesh_self_consumption_rate",
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
    for d in dashboards.async_items():
        data = d.get("data", {})
        if isinstance(data, dict) and data.get("title") == "LOTSE Neighborhood":
            return
    try:
        await dashboards.async_create_item({
            "id": "lotse_neighborhood",
            "data": DASHBOARD_CONFIG,
        })
        _LOGGER.info("Created LOTSE Neighborhood dashboard")
    except Exception as exc:
        _LOGGER.warning("Could not create LOTSE dashboard: %s", exc)
