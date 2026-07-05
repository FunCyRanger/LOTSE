import logging
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

DOMAIN = "lotse_forecast"

_LOGGER = logging.getLogger(__name__)


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float | int]] | None:
    _LOGGER.debug("Forecast: called for entry %s", config_entry_id)

    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None:
        _LOGGER.debug("Forecast: entry %s not found in registry", config_entry_id)
        return None
    if entry.domain != DOMAIN:
        _LOGGER.debug(
            "Forecast: entry %s domain is %s, not %s",
            config_entry_id, entry.domain, DOMAIN,
        )
        return None

    weather_entity = entry.options.get("weather_entity") or entry.data.get("weather_entity")
    if not weather_entity:
        _LOGGER.debug(
            "Forecast: no weather_entity in options=%s or data=%s for entry %s",
            entry.options.get("weather_entity"),
            entry.data.get("weather_entity"),
            config_entry_id,
        )
        return None

    forecast = await _get_weather_forecast(hass, weather_entity)
    if not forecast:
        _LOGGER.debug("Forecast: no forecast data from weather_entity %s", weather_entity)
        return None

    panels = _get_panels(hass, entry)
    if not panels:
        _LOGGER.debug("Forecast: no panels available for entry %s", config_entry_id)
        return None

    lat = hass.config.latitude
    tz = ZoneInfo(hass.config.time_zone)

    wh_hours = _compute_forecast(forecast, panels, lat, tz)
    _LOGGER.debug(
        "Forecast: returning %d wh_hours for entry %s (%d panels, weather=%s)",
        len(wh_hours), config_entry_id, len(panels), weather_entity,
    )
    return {"wh_hours": wh_hours}


async def _get_weather_forecast(hass, weather_entity):
    try:
        result = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": weather_entity, "type": "hourly"},
            blocking=True,
            return_response=True,
        )
    except Exception as exc:
        _LOGGER.debug("Forecast: weather service call failed: %s", exc)
        return None

    if not result or weather_entity not in result:
        return None

    raw = result[weather_entity]
    if isinstance(raw, dict):
        return raw.get("forecast") or raw.get("Forecast")
    if hasattr(raw, "forecast"):
        return raw.forecast
    return None


def _get_panels(hass, entry):
    panels = []

    def _sensor_or_default(sensor, default):
        if sensor is None:
            return default
        raw = sensor.state
        if raw in ("unknown", "unavailable", "none"):
            return default
        val = float(raw)
        return val if val > 0 else default

    # Auto-discover mesh node panels — prefer sensor entities, fallback to MeshData
    seen_nodes = set()
    for state in hass.states.async_all():
        m = re.match(r"^sensor\.node_(\d+)_sk$", state.entity_id)
        if not m:
            continue
        kwp = _sensor_or_default(state, 0)
        if kwp <= 0:
            continue
        nid = m.group(1)
        seen_nodes.add(nid)
        sa = hass.states.get(f"sensor.node_{nid}_sa")
        sz = hass.states.get(f"sensor.node_{nid}_sz")

        panels.append({
            "name": f"Node {nid}",
            "kwp": kwp,
            "angle": _sensor_or_default(sa, 35),
            "azimuth": _sensor_or_default(sz, 180),
        })

    # Fallback: read from MeshData for nodes without sensor entities yet
    mesh = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if mesh:
        for node_id in mesh.known_nodes():
            if node_id in seen_nodes:
                continue
            sk = mesh.get_value(node_id, "sk")
            if sk is None or sk <= 0:
                continue
            sa = mesh.get_value(node_id, "sa") or 35
            sz = mesh.get_value(node_id, "sz") or 180
            panels.append({
                "name": f"Node {node_id}",
                "kwp": float(sk),
                "angle": int(sa),
                "azimuth": int(sz),
            })

    # Manual panels from config options
    manual = entry.options.get("panels", [])
    for p in manual:
        kwp = float(p.get("kwp", 0))
        if kwp <= 0:
            continue
        panels.append({
            "name": p.get("name", "Manual"),
            "kwp": kwp,
            "angle": int(p.get("angle", 35)),
            "azimuth": int(p.get("azimuth", 180)),
        })

    _LOGGER.debug("Forecast: _get_panels found %d panels (%d auto, %d manual)",
                   len(panels), len(seen_nodes), len(manual))
    return panels


def _compute_forecast(forecast, panels, lat, tz):
    wh_hours = {}

    for entry in forecast:
        dt_raw = entry.get("datetime") or entry.get("DateTime")
        if not dt_raw:
            continue

        try:
            if isinstance(dt_raw, str):
                dt = datetime.fromisoformat(dt_raw).replace(tzinfo=tz)
            elif isinstance(dt_raw, datetime):
                dt = dt_raw.replace(tzinfo=tz) if dt_raw.tzinfo is None else dt_raw
            else:
                continue
        except (ValueError, TypeError):
            continue

        cloud = _float_or(entry.get("cloud_cover") or entry.get("CloudCover"), 50)
        temp = _float_or(entry.get("temperature") or entry.get("Temperature"), 20)
        wind = _float_or(entry.get("wind_speed") or entry.get("WindSpeed"), 5)

        dayofyear = dt.timetuple().tm_yday
        hour = dt.hour
        altitude = _solar_altitude(lat, dayofyear, hour)
        ghi = _clear_sky_ghi(altitude)

        total_wh = 0
        for panel in panels:
            kw = _panel_output(
                panel["kwp"], ghi, cloud,
                panel["azimuth"], panel["angle"],
                temp, wind,
            )
            total_wh += kw * 1000

        if total_wh > 0:
            wh_hours[dt.isoformat()] = int(round(total_wh))

    return wh_hours


def _solar_altitude(lat, dayofyear, hour):
    hour_angle = (hour - 12) * 15
    decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (dayofyear - 81))))
    lat_r = math.radians(lat)
    ha_r = math.radians(hour_angle)

    cos_zenith = (
        math.sin(lat_r) * math.sin(decl)
        + math.cos(lat_r) * math.cos(decl) * math.cos(ha_r)
    )
    cos_zenith = max(-1, min(1, cos_zenith))
    zenith = math.acos(cos_zenith)
    return max(0, 90 - math.degrees(zenith))


def _clear_sky_ghi(altitude):
    return max(0, 1000 * math.sin(math.radians(altitude)))


def _panel_output(kwp, ghi, cloud_cover, azimuth, tilt, temp, wind):
    efficiency = 0.90
    temp_coeff = -0.005

    cloud_factor = max(0.05, 1 - 0.50 * cloud_cover / 100)
    orientation = max(
        0.25,
        min(1.1, (math.cos(math.radians(azimuth - 180)) * 0.65 + 0.35)
            * (math.cos(math.radians(tilt)) ** 0.75)),
    )
    wind_factor = 1.0 if wind < 10 else 0.95
    temp_factor = max(0.7, 1 + temp_coeff * (temp - 25))

    return kwp * ghi / 1000 * cloud_factor * orientation * wind_factor * efficiency * temp_factor


def _float_or(val, default):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
