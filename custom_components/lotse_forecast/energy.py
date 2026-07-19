import logging
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

from .calibration import CalibrationModel

DOMAIN = "lotse_forecast"

_LOGGER = logging.getLogger(__name__)

_LOGGER.warning("lotse_forecast energy module loaded — ready for auto-discovery")


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float | int]] | None:
    _LOGGER.warning("Forecast: called for entry %s (debug for discovery verification)", config_entry_id)

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
        _LOGGER.debug("Forecast: no weather data, using clear-sky only")
        forecast = []

    panels = _get_panels(hass, entry)
    if not panels:
        _LOGGER.debug("Forecast: no panels available for entry %s", config_entry_id)
        return None

    lat = hass.config.latitude
    tz = ZoneInfo(hass.config.time_zone)
    local_now = datetime.now(tz)

    # Build set of timestamps the weather forecast already covers for today
    weather_ts: set[str] = set()
    for entry in forecast:
        dt_raw = entry.get("datetime") or entry.get("DateTime")
        if not dt_raw:
            continue
        try:
            if isinstance(dt_raw, str):
                dt = datetime.fromisoformat(dt_raw)
            elif isinstance(dt_raw, datetime):
                dt = dt_raw
            else:
                continue
            if dt.date() == local_now.date():
                weather_ts.add(dt.isoformat())
        except (ValueError, TypeError):
            continue

    _LOGGER.debug(
        "Forecast: weather_ts has %d entries from weather service for today",
        len(weather_ts),
    )

    # Backfill missing hours of today with clear-sky defaults
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    backfilled = 0
    for hour in range(24):
        dt = today_start.replace(hour=hour)
        ts = dt.isoformat()
        if ts not in weather_ts:
            forecast.append({
                "datetime": dt,
                "cloud_cover": 0,
                "temperature": 20,
                "wind_speed": 5,
            })
            backfilled += 1

    _LOGGER.debug(
        "Forecast: backfilled %d hours with clear-sky defaults, total forecast size=%d",
        backfilled, len(forecast),
    )

    raw_wh, cloud_map = _compute_forecast(forecast, panels, lat, tz)
    if not raw_wh:
        _LOGGER.debug("Forecast: no raw forecast values for entry %s", config_entry_id)
        return None

    # Apply calibration model if available
    model: CalibrationModel | None = hass.data.get(DOMAIN, {}).get("calibration")
    if model is not None:
        _LOGGER.debug(
            "Forecast: applying calibration model (global_scale=%.4f, cloud_factors=%s, samples=%d, mape=%s)",
            model.global_scale, model.cloud_factors, model.sample_count, model.mape,
        )
        calibrated = {}
        for ts, raw_val in raw_wh.items():
            cloud = cloud_map.get(ts) if ts in weather_ts else None
            cal_val = model.apply(raw_val, cloud_cover=cloud)
            if raw_val != cal_val:
                _LOGGER.debug(
                    "Forecast: calibration %s raw=%.1f calibrated=%.1f (cloud=%s)",
                    ts, raw_val, cal_val, cloud,
                )
            calibrated[ts] = cal_val
        model.store_forecast(calibrated, raw=raw_wh, now=local_now)
        wh_hours = dict(calibrated)
    else:
        _LOGGER.debug("Forecast: no calibration model available, using raw values")
        wh_hours = dict(raw_wh)

    # Log summary of returned wh_hours
    non_zero = sum(1 for v in wh_hours.values() if v > 0)
    if wh_hours:
        sample_keys = sorted(wh_hours.keys())[:5]
        sample_vals = {k: wh_hours[k] for k in sample_keys}
        _LOGGER.debug(
            "Forecast: returning %d wh_hours (non-zero=%d) for entry %s "
            "(%d panels, weather=%s, lat=%.2f, sample=%s)",
            len(wh_hours), non_zero, config_entry_id,
            len(panels), weather_entity, lat, sample_vals,
        )
    else:
        _LOGGER.debug(
            "Forecast: returning EMPTY wh_hours for entry %s (%d panels, weather=%s)",
            config_entry_id, len(panels), weather_entity,
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
    forecast = None
    if isinstance(raw, dict):
        forecast = raw.get("forecast") or raw.get("Forecast")
    elif hasattr(raw, "forecast"):
        forecast = raw.forecast
    if forecast is not None:
        _LOGGER.debug(
            "Forecast: _get_weather_forecast(%s) got %d entries; sample: %s",
            weather_entity, len(forecast),
            forecast[0] if forecast else "empty",
        )
    else:
        _LOGGER.debug("Forecast: _get_weather_forecast(%s) returned None", weather_entity)
    return forecast


def _get_panels(hass, entry):
    panels = []

    def _sensor_or_default(sensor, default):
        if sensor is None:
            return default
        raw = sensor.state
        if raw in ("unknown", "unavailable", "none"):
            return default
        try:
            val = float(raw.replace(",", "."))
        except (ValueError, TypeError):
            return default
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
            "angle": _sensor_or_default(sa, 44),
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
            sa = mesh.get_value(node_id, "sa") or 44
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
        try:
            kwp = float(str(p.get("kwp", 0)).replace(",", "."))
        except (ValueError, TypeError):
            continue
        if kwp <= 0:
            continue
        panels.append({
            "name": p.get("name", "Manual"),
            "kwp": kwp,
            "angle": int(p.get("angle", 44)),
            "azimuth": int(p.get("azimuth", 180)),
        })

    _LOGGER.debug("Forecast: _get_panels found %d panels (%d auto, %d manual)",
                   len(panels), len(seen_nodes), len(manual))
    for i, p in enumerate(panels):
        _LOGGER.debug(
            "Forecast: panel[%d] name=%s kwp=%.3f angle=%d azimuth=%d",
            i, p["name"], p["kwp"], p["angle"], p["azimuth"],
        )
    return panels


def _compute_forecast(forecast, panels, lat, tz):
    wh_hours = {}
    cloud_map = {}

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
        panel_details = []
        for panel in panels:
            kw = _panel_output(
                panel["kwp"], ghi, cloud,
                panel["azimuth"], panel["angle"],
                temp, wind,
            )
            wh = kw * 1000
            total_wh += wh
            panel_details.append(f"{panel.get('name', 'panel')}={wh:.1f}Wh")

        ts = dt.isoformat()
        cloud_map[ts] = cloud

        _LOGGER.debug(
            "Forecast: hour %s doy=%d h=%d lat=%.2f alt=%.1f ghi=%.1f "
            "cloud=%.0f%% temp=%.1f wind=%.1f panels=[%s] total=%.1fWh(%s)",
            ts, dayofyear, hour, lat, altitude, ghi,
            cloud, temp, wind,
            ", ".join(panel_details),
            total_wh,
            "%din" % int(round(total_wh)) if total_wh > 0 else "0",
        )

        if total_wh > 0:
            wh_hours[ts] = int(round(total_wh))

    return wh_hours, cloud_map


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


def _panel_output(kwp, ghi, cloud_cover, azimuth, tilt, temp, wind,
                  efficiency=0.94, cloud_coeff=0.45, temp_coeff=-0.010):
    cloud_factor = max(0.05, 1 - cloud_coeff * cloud_cover / 100)
    orientation = max(
        0.25,
        min(1.1, (math.cos(math.radians(azimuth - 180)) * 0.65 + 0.35)
            * (math.cos(math.radians(tilt)) ** 0.75)),
    )
    wind_factor = 1.0 if wind < 10 else 0.95
    temp_factor = max(0.7, 1 + temp_coeff * (temp - 25))

    raw_power = kwp * ghi / 1000
    result = raw_power * cloud_factor * orientation * wind_factor * efficiency * temp_factor

    _LOGGER.debug(
        "Forecast: _panel_output(kwp=%.3f ghi=%.1f cloud=%d azimuth=%d tilt=%d "
        "temp=%.1f wind=%.1f) → raw=%.4f cloud=%.4f orient=%.4f wind=%.4f "
        "effic=%.4f temp=%.4f = %.4f kW",
        kwp, ghi, cloud_cover, azimuth, tilt, temp, wind,
        raw_power, cloud_factor, orientation, wind_factor,
        efficiency, temp_factor, result,
    )
    return result


def _float_or(val, default):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
