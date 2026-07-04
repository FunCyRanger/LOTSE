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


COMBINED_FNS: dict[str, Callable[[MeshData], float]] = {
    "combined_mesh_gp": lambda m: _sum(m, "gp"),
    "combined_mesh_gip": lambda m: _sum(m, "gip"),
    "combined_mesh_gep": lambda m: _sum(m, "gep"),
    "combined_mesh_gp1": lambda m: _sum(m, "gp1"),
    "combined_mesh_gp2": lambda m: _sum(m, "gp2"),
    "combined_mesh_gp3": lambda m: _sum(m, "gp3"),
    "combined_mesh_gv1": lambda m: _sum(m, "gv1"),
    "combined_mesh_gei": lambda m: _sum(m, "gei"),
    "combined_mesh_geo": lambda m: _sum(m, "geo"),
    "combined_mesh_sp": lambda m: _sum(m, "sp"),
    "combined_mesh_se": lambda m: _sum(m, "se"),
    "combined_mesh_bp": lambda m: _sum(m, "bp"),
    "combined_mesh_bs": lambda m: _avg(m, "bs"),
    "combined_mesh_battery_capacity": lambda m: _sum(m, "bc"),
    "combined_mesh_solar_capacity": lambda m: _sum(m, "sk"),
    "combined_mesh_participants": lambda m: float(sum(1 for v in m.get_all_values("gip") if v)),
    "combined_mesh_config_ready": lambda m: float(len(m.get_all_values("bc"))),
    "combined_mesh_total_solar_generation": lambda m: _sum(m, "sp"),
    "combined_solar_utilization": lambda m: (
        round(sp / sk * 100, 1)
        if (sk := sum(m.get_all_values("sk"))) > 0
        else 0.0
    ),
    "combined_mesh_self_consumption_rate": lambda m: (
        round((1 - gep / sp) * 100, 1)
        if (sp := sum(m.get_all_values("sp"))) > 0.1
        else 0.0
    ),
    "combined_mesh_soc_weighted": lambda m: _weighted_soc(m),
    "combined_mesh_gv1_max": lambda m: _max(m, "gv1"),
    "combined_mesh_export_ratio": lambda m: (
        round(max(gep / sp, 0), 2)
        if (sp := sum(m.get_all_values("sp"))) > 0.1
        else 0.0
    ),
    "combined_mesh_se_clean": lambda m: _se_clean(m),
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

    def _create_node_sensors(node_id: str) -> None:
        entities = [
            LOTSEPerNodeSensor(node_id, key, meta, mesh)
            for key, meta in NODE_KEY_META.items()
        ]
        async_add_entities(entities)

    mesh.set_node_sensor_callback(_create_node_sensors)

    for node_id in mesh.known_nodes():
        _create_node_sensors(node_id)
