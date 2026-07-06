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
