from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.components.mqtt import DOMAIN as MQTT_DOMAIN
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import BAD_STATES, DOMAIN, MSH_TOPIC, NODE_KEY_META, PLATFORMS
from .dashboard import async_create_lovelace_dashboard

_LOGGER = logging.getLogger(__name__)

STALE_UNIQUE_IDS = {
    "combined_solar_panel_angle",
    "combined_solar_panel_azimuth",
    "combined_solar_panel_angle_forecast",
    "combined_solar_panel_azimuth_forecast",
    "combined_solar_capacity_forecast",
    "forecast_correction_factor",
    "solar_roughness_index",
    "solar_forecast_today",
    "solar_forecast_tomorrow",
    "solar_forecast_hourly_raw",
    "combined_mesh_export_ratio_forecast",
}

OLD_AUTOMATION_ALIAS = "Mesh: Auto-discover neighbors"


class MeshData:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._node_data: dict[str, dict[str, Any]] = {}
        self._node_callbacks: dict[str, set[Callable]] = {}
        self._combined_callbacks: set[Callable] = set()
        self._node_sensor_callbacks: Callable[[str], None] | None = None
        self._unsub_mqtt: Callable | None = None
        self._seen_config_nodes: set[str] = set()

    def register_per_node_sensor(self, node_id: str, callback: Callable) -> None:
        self._node_callbacks.setdefault(node_id, set()).add(callback)

    def unregister_per_node_sensor(self, node_id: str, callback: Callable) -> None:
        self._node_callbacks.get(node_id, set()).discard(callback)

    def register_combined_sensor(self, callback: Callable) -> None:
        self._combined_callbacks.add(callback)

    def unregister_combined_sensor(self, callback: Callable) -> None:
        self._combined_callbacks.discard(callback)

    def set_node_sensor_callback(self, cb: Callable[[str], None]) -> None:
        self._node_sensor_callbacks = cb

    def known_nodes(self) -> list[str]:
        return list(self._node_data.keys())

    def get_value(self, node_id: str, key: str) -> Any:
        return self._node_data.get(node_id, {}).get(key)

    def get_all_values(self, key: str) -> list[float]:
        vals = []
        for nd in self._node_data.values():
            v = nd.get(key)
            if v is not None:
                vals.append(float(v))
        return vals

    async def start(self) -> None:
        self._init_from_existing()
        await self._clean_stale_entities()
        await self._disable_old_automation()
        await self._subscribe_mqtt()

    async def stop(self) -> None:
        if self._unsub_mqtt:
            self._unsub_mqtt()
            self._unsub_mqtt = None

    def _init_from_existing(self) -> None:
        for state in self._hass.states.async_all():
            m = re.match(r"^sensor\.node_(\d+)_([a-z0-9]+)$", state.entity_id)
            if m:
                nid, key = m.group(1), m.group(2)
                if key in NODE_KEY_META:
                    v = _safe_float(state.state)
                    if v is not None:
                        self._node_data.setdefault(nid, {})[key] = v

    async def _clean_stale_entities(self) -> None:
        reg = er.async_get(self._hass)
        for unique_id in STALE_UNIQUE_IDS:
            entity_id = reg.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id:
                _LOGGER.info("Removing stale entity %s (%s)", entity_id, unique_id)
                reg.async_remove(entity_id)

    async def _disable_old_automation(self) -> None:
        from homeassistant.components.automation import DOMAIN as AUTO_DOMAIN

        reg = er.async_get(self._hass)
        for state in self._hass.states.async_all():
            if state.entity_id.startswith("automation.") and (
                state.attributes.get("alias") == OLD_AUTOMATION_ALIAS
                or state.attributes.get("friendly_name") == OLD_AUTOMATION_ALIAS
            ):
                _LOGGER.info("Disabling old automation %s", state.entity_id)
                try:
                    await self._hass.services.async_call(
                        AUTO_DOMAIN, "turn_off", {"entity_id": state.entity_id}, blocking=True
                    )
                except Exception:
                    _LOGGER.warning("Could not disable %s", state.entity_id)

    async def _subscribe_mqtt(self) -> None:
        if MQTT_DOMAIN not in self._hass.config.components:
            _LOGGER.warning("MQTT not available — mesh data not subscribed")
            return
        try:
            self._unsub_mqtt = await self._hass.components.mqtt.async_subscribe(
                MSH_TOPIC, self._handle_mqtt_msg, qos=0
            )
            _LOGGER.info("Subscribed to %s", MSH_TOPIC)
        except Exception as exc:
            _LOGGER.warning("MQTT subscribe failed: %s", exc)

    async def _handle_mqtt_msg(self, msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except (ValueError, TypeError):
            return

        from_node = payload.get("from")
        if from_node is None:
            return
        node_id = str(from_node)

        inner = payload.get("payload", {})
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except (ValueError, TypeError):
                inner = {}
        if not isinstance(inner, dict):
            return

        parsed = {}
        for k, v in inner.items():
            if k in NODE_KEY_META or k.lower() in NODE_KEY_META:
                sk = k.lower()
                fv = _safe_float(v)
                if fv is not None:
                    parsed[sk] = fv

        if not parsed:
            return

        is_config = bool({"bc", "sk", "sa", "sz"} & parsed.keys())
        was_new = node_id not in self._node_data

        self._node_data.setdefault(node_id, {}).update(parsed)

        for cb in self._node_callbacks.get(node_id, set()):
            cb()
        for cb in self._combined_callbacks:
            cb()

        if is_config and node_id not in self._seen_config_nodes:
            self._seen_config_nodes.add(node_id)

        if was_new and self._node_sensor_callbacks:
            self._node_sensor_callbacks(node_id)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    if str(f) in BAD_STATES or f != f:
        return None
    return f


async def async_setup_entry(hass: HomeAssistant, config_entry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    mesh = MeshData(hass)
    hass.data[DOMAIN][config_entry.entry_id] = mesh

    async def _start_later(_event=None) -> None:
        await mesh.start()
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
        await async_create_lovelace_dashboard(hass)

    if hass.is_running:
        await _start_later()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start_later)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry) -> bool:
    mesh: MeshData | None = hass.data.get(DOMAIN, {}).pop(config_entry.entry_id, None)
    if mesh:
        await mesh.stop()
    unloaded = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, config_entry) -> bool:
    if config_entry.version == 1:
        _LOGGER.info("Migrating config entry from version 1 to 2")
        new_data = {**config_entry.data}
        new_options = {**config_entry.options}
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options=new_options, version=2
        )
    return True
