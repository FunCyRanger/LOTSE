"""LOTSE Neighborhood dashboard — auto-created on integration setup."""

import logging

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.const import (
    LOVELACE_DATA,
    CONF_URL_PATH,
    DEFAULT_ICON,
    MODE_STORAGE,
)
from homeassistant.components.lovelace.dashboard import (
    DASHBOARDS_STORAGE_KEY,
    DASHBOARDS_STORAGE_VERSION,
    LovelaceStorage,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

URL_PATH = "lotse-neighborhood"
DASHBOARD_TITLE = "LOTSE Neighborhood"
DASHBOARD_ICON = "mdi:transmission-tower"

DASHBOARD_CONFIG = {
    "title": DASHBOARD_TITLE,
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
                        "sensor.combined_mesh_grid_power",
                        "sensor.combined_mesh_solar_power",
                        "sensor.combined_mesh_battery_power",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Frequency",
                    "entities": [
                        "sensor.combined_mesh_avg_frequency",
                        "sensor.combined_mesh_min_frequency",
                        "sensor.combined_mesh_max_frequency",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Voltage L1",
                    "entities": [
                        "sensor.combined_mesh_max_voltage_l1",
                        "sensor.combined_mesh_min_voltage_l1",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Voltage L2 / L3",
                    "entities": [
                        "sensor.combined_mesh_max_voltage_l2",
                        "sensor.combined_mesh_min_voltage_l2",
                        "sensor.combined_mesh_max_voltage_l3",
                        "sensor.combined_mesh_min_voltage_l3",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Phase Currents & Power Factor",
                    "entities": [
                        "sensor.combined_mesh_total_current_l1",
                        "sensor.combined_mesh_total_current_l2",
                        "sensor.combined_mesh_total_current_l3",
                        "sensor.combined_mesh_avg_power_factor",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Reactive & Apparent Power",
                    "entities": [
                        "sensor.combined_mesh_reactive_power",
                        "sensor.combined_mesh_apparent_power",
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
                        "sensor.combined_mesh_grid_import",
                        "sensor.combined_mesh_grid_export",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Solar",
                    "entities": [
                        "sensor.combined_mesh_solar_energy",
                        "sensor.combined_mesh_solar_energy_clean",
                        "sensor.combined_mesh_solar_capacity",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Battery",
                    "entities": [
                        "sensor.combined_mesh_battery_energy_in",
                        "sensor.combined_mesh_battery_energy_out",
                        "sensor.combined_mesh_battery_capacity",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Neighborhood",
                    "entities": [
                        "sensor.average_neighbor_soc",
                        "sensor.weighted_average_soc",
                        "sensor.participating_neighbors",
                        "sensor.config_ready_nodes",
                    ],
                },
                {
                    "type": "entities",
                    "title": "Solar Forecast",
                    "entities": [
                        "sensor.solar_production_with_forecast",
                        "sensor.combined_mesh_solar_capacity",
                    ],
                },
            ],
        },
    ],
}


async def async_create_lovelace_dashboard(hass: HomeAssistant) -> None:
    if LOVELACE_DATA not in hass.data:
        _LOGGER.warning("Lovelace not available — skipping dashboard creation")
        return

    lovelace_data = hass.data[LOVELACE_DATA]
    dashboards = lovelace_data.dashboards

    # Remove any old-style dashboard entry with underscore (pre-v3.4.0 store format)
    old_key = "lotse_neighborhood"
    if old_key in dashboards:
        del dashboards[old_key]

    # Check if dashboard already exists with correct url_path
    if URL_PATH in dashboards:
        store = dashboards[URL_PATH]
        if hasattr(store, "async_save"):
            await store.async_save({"views": DASHBOARD_CONFIG["views"]})
        return

    # Register the frontend panel
    async_register_built_in_panel(
        hass, "lovelace",
        frontend_url_path=URL_PATH,
        require_admin=False,
        show_in_sidebar=True,
        sidebar_title=DASHBOARD_TITLE,
        sidebar_icon=DASHBOARD_ICON,
        config={"mode": MODE_STORAGE},
        update=False,
    )

    # Create LovelaceStorage and save the views config
    dashboard_item = {
        "id": URL_PATH,
        CONF_URL_PATH: URL_PATH,
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
    }
    store = LovelaceStorage(hass, dashboard_item)
    dashboards[URL_PATH] = store
    await store.async_save({"views": DASHBOARD_CONFIG["views"]})

    # Persist dashboard metadata so it survives restart
    dashboards_store = Store[dict](hass, DASHBOARDS_STORAGE_VERSION, DASHBOARDS_STORAGE_KEY)
    data = await dashboards_store.async_load()
    if data is None:
        data = {"items": []}
    for item in data["items"]:
        if item.get(CONF_URL_PATH) == URL_PATH:
            break
    else:
        data["items"].append(dashboard_item)
        await dashboards_store.async_save(data)

    _LOGGER.info("Created LOTSE Neighborhood dashboard")
