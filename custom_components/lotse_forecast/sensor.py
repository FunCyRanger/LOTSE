from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity

_EntityBases = [SensorEntity]
_HAS_RESTORE = False
try:
    from homeassistant.helpers.restore_state import RestoreEntity
    _EntityBases.append(RestoreEntity)
    _HAS_RESTORE = True
except ImportError:
    pass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
try:
    from homeassistant.helpers.entity import EntityCategory
except ImportError:
    from enum import Enum
    class EntityCategory(str, Enum):
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from . import MeshData
from .calibration import CalibrationModel
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
    total_weight = 0.0
    weighted_sum = 0.0
    for node_id in mesh.known_nodes():
        bs = mesh.get_value(node_id, "bs")
        bc = mesh.get_value(node_id, "bc")
        if bs is not None and bc is not None and bc > 0 and 0 <= bs <= 100:
            weighted_sum += bs * bc
            total_weight += bc
    if total_weight > 0:
        return round(weighted_sum / total_weight, 1)
    vals = mesh.get_all_values("bs")
    valid = [v for v in vals if 0 <= v <= 100]
    return round(sum(valid) / len(valid), 1) if valid else 0.0


_SE_CLEAN_CACHE: dict[str, float] = {}


def _se_clean(mesh: MeshData) -> float:
    raw = _sum(mesh, "se")
    prev = _SE_CLEAN_CACHE.get("val", raw)
    clean = raw if raw >= prev else prev
    _SE_CLEAN_CACHE["val"] = clean
    return clean


class LOTSEPerNodeSensor(*_EntityBases):
    _attr_should_poll = False
    _restored_value: float | None = None
    _known_value: float | None = None

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
        if _HAS_RESTORE:
            if last := await self.async_get_last_state():
                try:
                    self._restored_value = float(last.state)
                except (ValueError, TypeError):
                    if last.attributes and "restore_value" in last.attributes:
                        self._restored_value = last.attributes["restore_value"]
        self._mesh.register_per_node_sensor(self._node_id, self._on_data)
        self.async_on_remove(lambda: self._mesh.unregister_per_node_sensor(self._node_id, self._on_data))

    def _on_data(self) -> None:
        v = self._mesh.get_value(self._node_id, self._key)
        if v is not None:
            self._known_value = v
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        v = self._mesh.get_value(self._node_id, self._key)
        return v if v is not None else self._restored_value

    @property
    def extra_state_attributes(self) -> dict:
        if self._known_value is not None:
            return {"restore_value": self._known_value}
        if self._restored_value is not None:
            return {"restore_value": self._restored_value}
        return {}

    @property
    def available(self) -> bool:
        return self._mesh.get_value(self._node_id, self._key) is not None or self._restored_value is not None


class LOTSECombinedSensor(*_EntityBases):
    _attr_should_poll = False
    _restored_value: float | None = None

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
        if _HAS_RESTORE:
            if last := await self.async_get_last_state():
                try:
                    self._restored_value = float(last.state)
                except (ValueError, TypeError):
                    if last.attributes and "restore_value" in last.attributes:
                        self._restored_value = last.attributes["restore_value"]
                if self._uid == "combined_mesh_se_clean" and self._restored_value is not None:
                    _SE_CLEAN_CACHE["val"] = self._restored_value
        self._mesh.register_combined_sensor(self._on_data)
        self.async_on_remove(lambda: self._mesh.unregister_combined_sensor(self._on_data))

    def _on_data(self) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        if self._mesh.known_nodes():
            return {"restore_value": self._compute_fn(self._mesh)}
        if self._restored_value is not None:
            return {"restore_value": self._restored_value}
        return {}

    @property
    def available(self) -> bool:
        return bool(self._mesh.known_nodes()) or self._restored_value is not None

    @property
    def native_value(self) -> float:
        if self._mesh.known_nodes():
            return self._compute_fn(self._mesh)
        if self._restored_value is not None:
            return self._restored_value
        return 0.0


class LOTSEForecastScaleFactorSensor(*_EntityBases):
    """Diagnostic sensor showing the model's global scale factor.

    The full model state (coefficients, MAPE, today_predicted) is
    exposed in extra_state_attributes for persistence and debugging.

    Self-restores from RestoreEntity state on HA restart.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, model: CalibrationModel) -> None:
        self._model = model
        self._attr_unique_id = "lotse_forecast_scale_factor"
        self._attr_name = "LOTSE Forecast Scale Factor"

    async def async_added_to_hass(self) -> None:
        if _HAS_RESTORE:
            if last := await self.async_get_last_state():
                if last.attributes and last.attributes.get("global_scale"):
                    self._model = CalibrationModel.from_dict(dict(last.attributes))
                    _LOGGER.warning(
                        "Restored calibration model: scale=%.4f, samples=%d, MAPE=%s",
                        self._model.global_scale, self._model.sample_count,
                        f"{self._model.mape:.1f}%" if self._model.mape is not None else "N/A",
                    )

    @property
    def native_value(self) -> str:
        return f"{self._model.global_scale:.4f}"

    @property
    def extra_state_attributes(self) -> dict:
        return self._model.to_dict()

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, "forecast")},
            "name": "LOTSE Solar Forecast",
            "manufacturer": "LOTSE",
            "model": "Solar Forecast",
            "via_device": (DOMAIN, "coordinator"),
        }


class LOTSEForecastAccuracySensor(*_EntityBases):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "%"

    def __init__(self, model: CalibrationModel) -> None:
        self._model = model
        self._attr_unique_id = "lotse_forecast_accuracy"
        self._attr_name = "LOTSE Forecast Accuracy (MAPE)"

    async def async_added_to_hass(self) -> None:
        if _HAS_RESTORE:
            if last := await self.async_get_last_state():
                if last.attributes and "sample_count" in last.attributes:
                    self._model.sample_count = last.attributes["sample_count"]

    @property
    def native_value(self) -> str | None:
        return f"{self._model.mape:.1f}" if self._model.mape is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        return {"sample_count": self._model.sample_count}

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, "forecast")},
            "name": "LOTSE Solar Forecast",
            "manufacturer": "LOTSE",
            "model": "Solar Forecast",
            "via_device": (DOMAIN, "coordinator"),
        }


class LOTSEForecastSamplesSensor(*_EntityBases):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, model: CalibrationModel) -> None:
        self._model = model
        self._attr_unique_id = "lotse_forecast_samples"
        self._attr_name = "LOTSE Forecast Samples"

    async def async_added_to_hass(self) -> None:
        if _HAS_RESTORE:
            if last := await self.async_get_last_state():
                try:
                    self._model.sample_count = int(float(last.state))
                except (ValueError, TypeError):
                    pass

    @property
    def native_value(self) -> int:
        return self._model.sample_count

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, "forecast")},
            "name": "LOTSE Solar Forecast",
            "manufacturer": "LOTSE",
            "model": "Solar Forecast",
            "via_device": (DOMAIN, "coordinator"),
        }


class LOTSEWeatherSnapshotSensor(*_EntityBases):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:weather-partly-cloudy"

    def __init__(self, weather_entity_id: str) -> None:
        self._weather_entity_id = weather_entity_id
        self._attr_unique_id = "lotse_weather_snapshot"
        self._attr_name = "LOTSE Weather Snapshot"
        self._weather_condition: str | None = None
        self._weather_temperature: float | None = None
        self._weather_wind_speed: float | None = None

    async def async_update_forecast(self, hass: HomeAssistant) -> None:
        state = hass.states.get(self._weather_entity_id)
        if state is None:
            return
        self._weather_condition = state.state
        attrs = state.attributes
        self._weather_temperature = attrs.get("temperature")
        self._weather_wind_speed = attrs.get("wind_speed")

        forecast = attrs.get("forecast", [])
        if forecast and isinstance(forecast, list):
            cloud = forecast[0].get("cloud_cover") if isinstance(forecast[0], dict) else None
            if cloud is not None:
                self._attr_native_value = float(cloud)
            else:
                cond = forecast[0].get("condition", self._weather_condition) if isinstance(forecast[0], dict) else self._weather_condition
                self._attr_native_value = _condition_to_cloud(cond)
        else:
            self._attr_native_value = _condition_to_cloud(self._weather_condition)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        if self._weather_condition is not None:
            attrs["condition"] = self._weather_condition
        if self._weather_temperature is not None:
            attrs["temperature"] = self._weather_temperature
        if self._weather_wind_speed is not None:
            attrs["wind_speed"] = self._weather_wind_speed
        return attrs

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, "coordinator")},
            "name": "LOTSE Mesh Coordinator",
            "manufacturer": "LOTSE",
            "model": "Neighborhood Hub",
        }


CLOUD_COVER_MAP = {
    "clear-night": 5, "sunny": 5, "partlycloudy": 40,
    "cloudy": 75, "rainy": 90, "fog": 85,
    "pouring": 95, "snowy": 85, "snowy-rainy": 85,
    "hail": 95, "lightning": 90, "lightning-rainy": 90,
}


def _condition_to_cloud(condition: str | None) -> float:
    if condition is None:
        return 50.0
    return float(CLOUD_COVER_MAP.get(condition.lower().strip(), 50))


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    mesh: MeshData = hass.data[DOMAIN][config_entry.entry_id]
    model: CalibrationModel | None = hass.data[DOMAIN].get("calibration")

    combined = [
        LOTSECombinedSensor(uid, meta, COMBINED_FNS[uid], mesh)
        for uid, meta in COMBINED_KEY_META.items()
        if uid in COMBINED_FNS
    ]
    async_add_entities(combined)

    # Calibration sensors (independent of mesh data)
    cal_sensors = []
    if model:
        cal_sensors.append(LOTSEForecastScaleFactorSensor(model))
        cal_sensors.append(LOTSEForecastAccuracySensor(model))
        cal_sensors.append(LOTSEForecastSamplesSensor(model))
    async_add_entities(cal_sensors)

    # Weather snapshot sensor (for forecast validation history)
    weather_entity = (config_entry.options.get("weather_entity")
                      or config_entry.data.get("weather_entity"))
    if weather_entity:
        ws = LOTSEWeatherSnapshotSensor(weather_entity)
        hass.data.setdefault(DOMAIN, {}).setdefault(config_entry.entry_id, {})
        hass.data[DOMAIN][config_entry.entry_id]["weather_snapshot"] = ws
        async_add_entities([ws])

    def _create_node_sensors(node_id: str, keys: list[str]) -> None:
        entities = [
            LOTSEPerNodeSensor(node_id, key, NODE_KEY_META[key], mesh)
            for key in keys
            if key in NODE_KEY_META
        ]
        if entities:
            async_add_entities(entities)

    mesh.set_node_sensor_callback(_create_node_sensors)
