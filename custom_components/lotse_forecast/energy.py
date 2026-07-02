from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

DOMAIN = "lotse_forecast"
SENSOR_ENTITY = "sensor.solar_forecast_hourly_raw"


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float | int]] | None:
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        return None

    state = hass.states.get(SENSOR_ENTITY)
    if state is None:
        return None

    wh_dict = state.attributes.get("result")
    if not wh_dict or not isinstance(wh_dict, dict):
        return None

    tz = ZoneInfo(hass.config.time_zone)
    result: dict[str, float | int] = {}
    prev = 0

    for ts_str in sorted(wh_dict.keys()):
        val = wh_dict[ts_str]
        if not isinstance(val, (int, float)):
            continue
        wh = int(val)
        if wh < prev:
            prev = 0
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        except (ValueError, TypeError):
            continue
        period_wh = wh - prev
        if 0 < period_wh < 50000:
            result[dt.isoformat()] = period_wh
        prev = wh

    return {"wh_hours": result}
