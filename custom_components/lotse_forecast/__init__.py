from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.mqtt import DOMAIN as MQTT_DOMAIN
from homeassistant.components.mqtt import async_subscribe as mqtt_async_subscribe
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .calibration import CalibrationModel
from .const import BAD_STATES, DOMAIN, MSH_TOPIC, NODE_KEY_META, PLATFORMS
from .dashboard import async_create_lovelace_dashboard

_LOGGER = logging.getLogger(__name__)

STALE_UNIQUE_IDS = {
    # Removed in v2 (solar forecast model refactor)
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
    # Removed in v3.2 (async power sums are misleading)
    "combined_mesh_gip",
    "combined_mesh_gep",
    "combined_mesh_gp1",
    "combined_mesh_gp2",
    "combined_mesh_gp3",
    "combined_mesh_total_solar_generation",
    "combined_solar_utilization",
    "combined_mesh_self_consumption_rate",
    "combined_mesh_export_ratio",
    "combined_mesh_export_ratio_forecast",
}

OLD_AUTOMATION_ALIAS = "Mesh: Auto-discover neighbors"


class MeshData:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._node_data: dict[str, dict[str, Any]] = {}
        self._node_callbacks: dict[str, set[Callable]] = {}
        self._combined_callbacks: set[Callable] = set()
        self._node_sensor_callback: Callable[[str, list[str]], None] | None = None
        self._unsub_mqtt: Callable | None = None
        self._seen_config_nodes: set[str] = set()
        self._node_known_keys: dict[str, set[str]] = {}

    def register_per_node_sensor(self, node_id: str, callback: Callable) -> None:
        self._node_callbacks.setdefault(node_id, set()).add(callback)

    def unregister_per_node_sensor(self, node_id: str, callback: Callable) -> None:
        self._node_callbacks.get(node_id, set()).discard(callback)

    def register_combined_sensor(self, callback: Callable) -> None:
        self._combined_callbacks.add(callback)

    def unregister_combined_sensor(self, callback: Callable) -> None:
        self._combined_callbacks.discard(callback)

    def set_node_sensor_callback(self, cb: Callable[[str, list[str]], None]) -> None:
        self._node_sensor_callback = cb

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
        await self._clean_stale_entities()
        await self._disable_old_automation()
        await self._subscribe_mqtt()

    async def stop(self) -> None:
        if self._unsub_mqtt:
            self._unsub_mqtt()
            self._unsub_mqtt = None

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
            self._unsub_mqtt = await mqtt_async_subscribe(
                self._hass, MSH_TOPIC, self._handle_mqtt_msg, qos=0
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

        prev_keys = self._node_known_keys.get(node_id, set())
        new_keys = set(parsed.keys()) - prev_keys

        self._node_data.setdefault(node_id, {}).update(parsed)
        self._node_known_keys.setdefault(node_id, set()).update(parsed.keys())

        is_config = bool({"bc", "sk", "sa", "sz"} & parsed.keys())

        for cb in self._node_callbacks.get(node_id, set()):
            cb()
        for cb in self._combined_callbacks:
            cb()

        if is_config and node_id not in self._seen_config_nodes:
            self._seen_config_nodes.add(node_id)

        if new_keys and self._node_sensor_callback:
            self._node_sensor_callback(node_id, list(new_keys))


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


async def _ensure_energy_platform(hass: HomeAssistant, entry_id: str) -> None:
    """Pre-warm the energy platform singleton so auto-discovery happens now."""
    try:
        from homeassistant.components.energy import async_get_manager  # type: ignore[import-untyped]
        from homeassistant.components.energy.websocket_api import (  # type: ignore[import-untyped]
            async_get_energy_platforms,
        )
        platforms = await async_get_energy_platforms(hass)
        if DOMAIN in platforms:
            _LOGGER.warning(
                "Energy platform pre-warm: lotse_forecast registered (domains: %s)",
                list(platforms),
            )
            manager = await async_get_manager(hass)
            if manager.data:
                sources = list(manager.data.get("energy_sources", []))
                changed = False
                reg = er.async_get(hass)
                for source in sources:
                    if source["type"] != "solar":
                        continue
                    if source.get("config_entry_solar_forecast"):
                        continue
                    stat_energy = source.get("stat_energy_from")
                    if stat_energy:
                        entry = reg.async_get(stat_energy)
                        if entry and entry.platform == DOMAIN:
                            source["config_entry_solar_forecast"] = [entry_id]
                            changed = True
                            _LOGGER.warning(
                                "Auto-linked solar source %s to config_entry %s",
                                stat_energy, entry_id,
                            )
                if changed:
                    await manager.async_update({"energy_sources": sources})
        else:
            _LOGGER.warning(
                "Energy platform pre-warm: lotse_forecast NOT found in %s",
                list(platforms),
            )
    except Exception as exc:
        _LOGGER.warning("Energy platform pre-warm: %s", exc)


async def async_setup_entry(hass: HomeAssistant, config_entry) -> bool:
    hass.config.top_level_components.add(DOMAIN)
    hass.data.setdefault(DOMAIN, {})
    mesh = MeshData(hass)
    hass.data[DOMAIN][config_entry.entry_id] = mesh

    # Create calibration model (seeded from entity state below)
    model = CalibrationModel()
    hass.data[DOMAIN]["calibration"] = model

    async def _hourly_tick(now) -> None:
        """Capture actual production for the completed hour, train model, log weather."""
        # Update weather snapshot sensor (for forecast validation history)
        ws = hass.data.get(DOMAIN, {}).get(f"weather_snapshot_{config_entry.entry_id}")
        if ws is not None:
            await ws.async_update_forecast(hass)

        # Capture actual production for calibration
        reg = er.async_get(hass)
        se_entity_id = reg.async_get_entity_id("sensor", DOMAIN, "combined_mesh_se")
        if not se_entity_id:
            return
        state = hass.states.get(se_entity_id)
        if state is None:
            return
        try:
            current_kwh = float(state.state)
        except (ValueError, TypeError):
            return
        last_kwh = model.last_se_snapshot
        model.last_se_snapshot = current_kwh
        if last_kwh is None or current_kwh < last_kwh:
            return  # first tick or reset

        actual_wh = (current_kwh - last_kwh) * 1000
        if actual_wh <= 0:
            return

        # Convert UTC tick to local timezone to match forecast dict keys
        local_tz = ZoneInfo(hass.config.time_zone)
        hour_end_utc = now - timedelta(hours=1)
        hour_end_local = hour_end_utc.astimezone(local_tz)
        hour_iso = hour_end_local.replace(minute=0, second=0, microsecond=0).isoformat()

        model.train_from_actual(hour_iso, actual_wh)

    async def _start_later(_event=None) -> None:
        await mesh.start()
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
        await async_create_lovelace_dashboard(hass)
        # Schedule hourly training at the top of each hour so hour_iso aligns with forecast keys
        from homeassistant.helpers.event import async_track_utc_time_change
        hass.data[DOMAIN]["_unsub_hourly"] = async_track_utc_time_change(
            hass, _hourly_tick, minute=0, second=0
        )
        hass.async_create_task(_ensure_energy_platform(hass, config_entry.entry_id))

    if hass.is_running:
        await _start_later()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start_later)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry) -> bool:
    mesh: MeshData | None = hass.data.get(DOMAIN, {}).pop(config_entry.entry_id, None)
    if mesh:
        await mesh.stop()
    unsub = hass.data.get(DOMAIN, {}).pop("_unsub_hourly", None)
    if unsub:
        unsub()
    hass.data.get(DOMAIN, {}).pop("calibration", None)
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
