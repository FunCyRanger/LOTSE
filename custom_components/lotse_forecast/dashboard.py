"""LOTSE Neighborhood dashboard — auto-created on integration setup."""

import logging

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.const import (
    LOVELACE_DATA,
    CONF_URL_PATH,
    MODE_STORAGE,
)
from homeassistant.components.lovelace.dashboard import (
    DASHBOARDS_STORAGE_KEY,
    DASHBOARDS_STORAGE_VERSION,
    LovelaceStorage,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import COMBINED_KEY_META, DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_PATH = "lotse-neighborhood"
DASHBOARD_TITLE = "LOTSE Neighborhood"
DASHBOARD_ICON = "mdi:transmission-tower"

# Card definitions by unique_id — resolved to entity_ids at runtime
_VIEWS = [
    {
        "title": "Grid Stability",
        "path": "grid-stability",
        "badges": [],
        "cards": [
            {"type": "entities", "title": "Power Snapshot", "unique_ids": ["combined_mesh_gp", "combined_mesh_sp", "combined_mesh_bp"]},
            {"type": "entities", "title": "Frequency", "unique_ids": ["combined_mesh_gf_avg", "combined_mesh_gf_min", "combined_mesh_gf_max"]},
            {"type": "entities", "title": "Voltage L1", "unique_ids": ["combined_mesh_gv1_max", "combined_mesh_gv1_min"]},
            {"type": "entities", "title": "Voltage L2 / L3", "unique_ids": ["combined_mesh_gv2_max", "combined_mesh_gv2_min", "combined_mesh_gv3_max", "combined_mesh_gv3_min"]},
            {"type": "entities", "title": "Phase Currents & Power Factor", "unique_ids": ["combined_mesh_ga1_sum", "combined_mesh_ga2_sum", "combined_mesh_ga3_sum", "combined_mesh_gpf_avg"]},
            {"type": "entities", "title": "Reactive & Apparent Power", "unique_ids": ["combined_mesh_gq_sum", "combined_mesh_gs_sum"]},
        ],
    },
    {
        "title": "Cumulative Energy",
        "path": "cumulative-energy",
        "badges": [],
        "cards": [
            {"type": "entities", "title": "Grid (add to Energy Dashboard)", "unique_ids": ["combined_mesh_gei", "combined_mesh_geo"]},
            {"type": "entities", "title": "Solar", "unique_ids": ["combined_mesh_se", "combined_mesh_se_clean", "combined_mesh_solar_capacity"]},
            {"type": "entities", "title": "Battery", "unique_ids": ["combined_mesh_bei", "combined_mesh_beo", "combined_mesh_battery_capacity"]},
            {"type": "entities", "title": "Neighborhood", "unique_ids": ["combined_mesh_bs", "combined_mesh_soc_weighted", "combined_mesh_participants", "combined_mesh_config_ready"]},
            {"type": "entities", "title": "Solar Forecast", "unique_ids": ["solar_production_forecast", "combined_mesh_solar_capacity"]},
        ],
    },
]


def _resolve_entities(hass: HomeAssistant, unique_ids: list[str]) -> list[str]:
    reg = er.async_get(hass)
    resolved = []
    for uid in unique_ids:
        entity_id = reg.async_get_entity_id("sensor", DOMAIN, uid)
        resolved.append(entity_id or f"sensor.{uid}")
    return resolved


def _build_dashboard_config(hass: HomeAssistant) -> dict:
    views = []
    for view_def in _VIEWS:
        cards = []
        for card_def in view_def["cards"]:
            entities = _resolve_entities(hass, card_def["unique_ids"])
            cards.append({
                "type": card_def["type"],
                "title": card_def["title"],
                "entities": entities,
            })
        views.append({
            "title": view_def["title"],
            "path": view_def["path"],
            "badges": view_def.get("badges", []),
            "cards": cards,
        })
    return {"title": DASHBOARD_TITLE, "views": views}


async def async_create_lovelace_dashboard(hass: HomeAssistant) -> None:
    if LOVELACE_DATA not in hass.data:
        _LOGGER.warning("Lovelace not available — skipping dashboard creation")
        return

    lovelace_data = hass.data[LOVELACE_DATA]
    dashboards = lovelace_data.dashboards

    old_key = "lotse_neighborhood"
    if old_key in dashboards:
        del dashboards[old_key]

    config = _build_dashboard_config(hass)

    if URL_PATH in dashboards:
        store = dashboards[URL_PATH]
        if hasattr(store, "async_save"):
            await store.async_save({"views": config["views"]})
        return

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
    await store.async_save({"views": config["views"]})

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
