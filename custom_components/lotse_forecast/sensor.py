from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MeshData
from .const import COMBINED_KEY_META, DOMAIN, NODE_KEY_META

_LOGGER = logging.getLogger(__name__)


def _sum(mesh: MeshData, key: str) -> float:
    return round(sum(mesh.get_all_values(key)), 2)


def _avg(mesh: MeshData, key: str) -> float:
    vals = mesh.get_all_values(key)
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def _max(mesh: MeshData, key: str) -> float:
    vals = mesh.get_all_values(key)
    return round(max(vals), 1) if vals else 0.0


def _min(mesh: MeshData, key: str) -> float:
    vals = mesh.get_all_values(key)
    return round(min(vals), 1) if vals else 0.0


COMBINED_FNS: dict[str, Callable[[MeshData], float]] = {
    # Power sums (useful for situational awareness despite async timing)
    "combined_mesh_gp": lambda m: _sum(m, "gp"),
    "combined_mesh_sp": lambda m: _sum(m, "sp"),
    "combined_mesh_bp": lambda m: _sum(m, "bp"),
    # Cumulative energy (valid — monotonically increasing)
    "combined_mesh_gei": lambda m: _sum(m, "gei"),
    "combined_mesh_geo": lambda m: _sum(m, "geo"),
    "combined_mesh_se": lambda m: _sum(m, "se"),
    "combined_mesh_se_clean": lambda m: _se_clean(m),
    "combined_mesh_bei": lambda m: _sum(m, "bei"),
    "combined_mesh_beo": lambda m: _sum(m, "beo"),
    # Static config (valid — doesn't change between reports)
    "combined_mesh_battery_capacity": lambda m: _sum(m, "bc"),
    "combined_mesh_solar_capacity": lambda m: _sum(m, "sk"),
    # Slow-changing averages (valid — SOC changes slowly)
    "combined_mesh_bs": lambda m: _avg(m, "bs"),
    "combined_mesh_soc_weighted": lambda m: _weighted_soc(m),
    # Counters (timeless)
    "combined_mesh_participants": lambda m: float(sum(1 for v in m.get_all_values("gip") if v)),
    "combined_mesh_config_ready": lambda m: float(len(m.get_all_values("bc"))),
    # Grid-coherent stats (valid — same physical grid, averages filter noise)
    "combined_mesh_gv1_max": lambda m: _max(m, "gv1"),
    "combined_mesh_gv1_min": lambda m: _min(m, "gv1"),
    "combined_mesh_gv2_max": lambda m: _max(m, "gv2"),
    "combined_mesh_gv2_min": lambda m: _min(m, "gv2"),
    "combined_mesh_gv3_max": lambda m: _max(m, "gv3"),
    "combined_mesh_gv3_min": lambda m: _min(m, "gv3"),
    "combined_mesh_gf_avg": lambda m: _avg(m, "gf"),
    "combined_mesh_gf_min": lambda m: _min(m, "gf"),
    "combined_mesh_gf_max": lambda m: _max(m, "gf"),
    "combined_mesh_gpf_avg": lambda m: _avg(m, "gpf"),
    # Phase current sums (approximate snapshot — useful for phase balance)
    "combined_mesh_ga1_sum": lambda m: _sum(m, "ga1"),
    "combined_mesh_ga2_sum": lambda m: _sum(m, "ga2"),
    "combined_mesh_ga3_sum": lambda m: _sum(m, "ga3"),
    # Reactive and apparent power (new protocol keys)
    "combined_mesh_gq_sum": lambda m: _sum(m, "gq"),
    "combined_mesh_gs_sum": lambda m: _sum(m, "gs"),
    # Forecast
    "solar_production_forecast": lambda m: _sum(m, "se"),
}


def _weighted_soc(mesh: MeshData) -> float:
    bs_vals = mesh.get_all_values("bs")
    bc_vals = mesh.get_all_values("bc")
    if not bs_vals or not bc_vals:
        return 0.0
    n = min(len(bs_vals), len(bc_vals))
    total_weight = sum(bc_vals[:n])
    return round(sum(bs_vals[i] * bc_vals[i] for i in range(n)) / total_weight, 1) if total_weight > 0 else 0.0


_SE_CLEAN_CACHE: dict[str, float] = {}


def _se_clean(mesh: MeshData) -> float:
    raw = _sum(mesh, "se")
    prev = _SE_CLEAN_CACHE.get("val", raw)
    clean = raw if raw >= prev else prev
    _SE_CLEAN_CACHE["val"] = clean
    return clean


class LOTSEPerNodeSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, node_id: str, key: str, meta: dict, mesh: MeshData) -> None:
        self._node_id = node_id
        self._key = key
        self._mesh = mesh
        self._attr_unique_id = f"mesh_{node_id}_{key}"
        self._attr_name = f"Node {node_id} {meta['name']}"
        self._attr_native_unit_of_measurement = meta.get("unit")
        if meta.get("device_class"):
            self._attr_device_class = meta["device_class"]
        if meta.get("state_class"):
            self._attr_state_class = meta["state_class"]

    @property
    def device_info(self) -> dict | None:
        return {
            "identifiers": {(DOMAIN, f"node_{self._node_id}")},
            "name": f"LOTSE Node {self._node_id}",
            "manufacturer": "LOTSE",
            "model": "Meshtastic Node",
            "via_device": (DOMAIN, "coordinator"),
        }

    async def async_added_to_hass(self) -> None:
        self._mesh.register_per_node_sensor(self._node_id, self._on_data)
        self.async_on_remove(lambda: self._mesh.unregister_per_node_sensor(self._node_id, self._on_data))

    def _on_data(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self._mesh.get_value(self._node_id, self._key)

    @property
    def available(self) -> bool:
        return self._mesh.get_value(self._node_id, self._key) is not None


class LOTSECombinedSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, uid: str, meta: dict, compute_fn: Callable[[MeshData], float], mesh: MeshData) -> None:
        self._uid = uid
        self._meta = meta
        self._compute_fn = compute_fn
        self._mesh = mesh
        self._attr_unique_id = uid
        self._attr_name = meta["name"]
        self._attr_native_unit_of_measurement = meta.get("unit")
        if meta.get("device_class"):
            self._attr_device_class = meta["device_class"]
        if meta.get("state_class"):
            self._attr_state_class = meta["state_class"]

    @property
    def device_info(self) -> dict | None:
        if self._uid == "solar_production_forecast":
            return {
                "identifiers": {(DOMAIN, "forecast")},
                "name": "LOTSE Solar Forecast",
                "manufacturer": "LOTSE",
                "model": "Solar Forecast",
                "via_device": (DOMAIN, "coordinator"),
            }
        return {
            "identifiers": {(DOMAIN, "coordinator")},
            "name": "LOTSE Mesh Coordinator",
            "manufacturer": "LOTSE",
            "model": "Neighborhood Hub",
        }

    async def async_added_to_hass(self) -> None:
        self._mesh.register_combined_sensor(self._on_data)
        self.async_on_remove(lambda: self._mesh.unregister_combined_sensor(self._on_data))

    def _on_data(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._compute_fn(self._mesh)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    mesh: MeshData = hass.data[DOMAIN][config_entry.entry_id]

    combined = [
        LOTSECombinedSensor(uid, meta, COMBINED_FNS[uid], mesh)
        for uid, meta in COMBINED_KEY_META.items()
        if uid in COMBINED_FNS
    ]
    async_add_entities(combined)

    def _create_node_sensors(node_id: str, keys: list[str]) -> None:
        entities = [
            LOTSEPerNodeSensor(node_id, key, NODE_KEY_META[key], mesh)
            for key in keys
            if key in NODE_KEY_META
        ]
        if entities:
            async_add_entities(entities)

    mesh.set_node_sensor_callback(_create_node_sensors)
