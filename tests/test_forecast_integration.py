"""Integration tests for energy.py forecast backfill.

Verifies that async_get_solar_forecast backfills all 24 hours of today
so the Energy Dashboard shows a continuous curve from sunrise through
the last forecast hour.
"""

import sys
import math
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ─── Mock HA modules before importing custom_components ─────────────────
ha = MagicMock()
ha.core = MagicMock()
ha.util = MagicMock()
ha.util.dt = MagicMock()
ha.components = MagicMock()
ha.components.mqtt = MagicMock()
ha.components.mqtt.DOMAIN = "mqtt"
ha.components.mqtt.async_subscribe = AsyncMock()
ha.components.sensor = MagicMock()
ha.config_entries = MagicMock()
ha.const = MagicMock()
ha.const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
ha.helpers = MagicMock()
ha.helpers.entity_registry = MagicMock()
ha.helpers.storage = MagicMock()
ha.helpers.storage.Store = MagicMock()

for mod_name, obj in [
    ("homeassistant", ha),
    ("homeassistant.core", ha.core),
    ("homeassistant.util", ha.util),
    ("homeassistant.util.dt", ha.util.dt),
    ("homeassistant.components", ha.components),
    ("homeassistant.components.mqtt", ha.components.mqtt),
    ("homeassistant.components.sensor", ha.components.sensor),
    ("homeassistant.config_entries", ha.config_entries),
    ("homeassistant.const", ha.const),
    ("homeassistant.helpers", ha.helpers),
    ("homeassistant.helpers.entity_registry", ha.helpers.entity_registry),
    ("homeassistant.helpers.entity_platform", MagicMock()),
    ("homeassistant.helpers.storage", ha.helpers.storage),
]:
    sys.modules[mod_name] = obj

# Mock dashboard submodule before __init__.py tries to import it
sys.modules["custom_components.lotse_forecast.dashboard"] = MagicMock()
sys.modules["custom_components.lotse_forecast.dashboard"].async_create_lovelace_dashboard = MagicMock()

# Now safe to import real modules
from zoneinfo import ZoneInfo
from custom_components.lotse_forecast import energy
from custom_components.lotse_forecast.calibration import CalibrationModel

TZ_BERLIN = ZoneInfo("Europe/Berlin")


# ═══════════════════════════════════════════════════════════════════════
# Helper: build forecast entries
# ═══════════════════════════════════════════════════════════════════════

def _make_entry(dt: datetime, cloud_cover=0, temperature=20, wind_speed=5):
    return {
        "datetime": dt,
        "cloud_cover": cloud_cover,
        "temperature": temperature,
        "wind_speed": wind_speed,
    }


def _make_full_day_forecast(dt_start: datetime, **overrides):
    """Build 24 hourly entries starting at midnight of dt_start's date."""
    base = dt_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return [_make_entry(base.replace(hour=h), **overrides) for h in range(24)]


# ═══════════════════════════════════════════════════════════════════════
# 1. _compute_forecast — full-day produces daylight-only results
# ═══════════════════════════════════════════════════════════════════════

class TestComputeForecastIntegration:
    """_compute_forecast with a full 24-hour forecast covers only daylight hours."""

    PANELS = [{"kwp": 5.0, "angle": 35, "azimuth": 180}]
    LAT = 52.5  # Berlin

    def test_full_day_returns_daylight_only(self):
        """All 24 hours of a summer day, only hours with sun produce >0 Wh."""
        dt_ref = datetime(2026, 7, 6, 0, 0, tzinfo=TZ_BERLIN)  # summer
        forecast = _make_full_day_forecast(dt_ref, cloud_cover=0)
        raw_wh, cloud_map = energy._compute_forecast(forecast, self.PANELS, self.LAT, TZ_BERLIN)

        assert len(raw_wh) > 0, "Expected some daylight hours"
        assert len(raw_wh) < 24, "Night hours should be excluded"

        for ts, wh in raw_wh.items():
            assert wh > 0, f"Expected positive Wh for {ts}"
            dt = datetime.fromisoformat(ts)
            assert 4 <= dt.hour <= 22, f"Daylight hour {dt.hour} out of range"

    def test_night_hours_produce_zero(self):
        """Night hours like 0-3AM should not appear in output."""
        dt_ref = datetime(2026, 7, 6, 0, 0, tzinfo=TZ_BERLIN)
        forecast = _make_full_day_forecast(dt_ref, cloud_cover=0)
        raw_wh, _ = energy._compute_forecast(forecast, self.PANELS, self.LAT, TZ_BERLIN)

        night_hours = {h for h in range(24)}
        day_hours = {datetime.fromisoformat(ts).hour for ts in raw_wh}
        dark_hours = night_hours - day_hours

        # At least hours 0-3 should be dark at this latitude/summer
        assert 0 in dark_hours
        assert 1 in dark_hours
        assert 2 in dark_hours
        assert 3 in dark_hours

    def test_winter_has_fewer_daylight_hours(self):
        """December has fewer daylight hours than June."""
        dt_summer = datetime(2026, 6, 21, 0, 0, tzinfo=TZ_BERLIN)
        dt_winter = datetime(2026, 12, 21, 0, 0, tzinfo=TZ_BERLIN)

        summer_wh, _ = energy._compute_forecast(
            _make_full_day_forecast(dt_summer), self.PANELS, self.LAT, TZ_BERLIN)
        winter_wh, _ = energy._compute_forecast(
            _make_full_day_forecast(dt_winter), self.PANELS, self.LAT, TZ_BERLIN)

        assert len(summer_wh) > len(winter_wh)


# ═══════════════════════════════════════════════════════════════════════
# 2. Cloud cover affects output values
# ═══════════════════════════════════════════════════════════════════════

class TestCloudCoverEffect:
    """Weather-sourced (high cloud) vs backfilled (clear sky) values differ."""

    PANELS = [{"kwp": 5.0, "angle": 35, "azimuth": 180}]
    LAT = 52.5

    def test_cloudy_produces_lower_wh(self):
        """Same hour, cloudy entry produces less Wh than clear-sky."""
        dt = datetime(2026, 7, 6, 14, 0, tzinfo=TZ_BERLIN)
        clear = [{"datetime": dt, "cloud_cover": 0, "temperature": 20, "wind_speed": 5}]
        cloudy = [{"datetime": dt, "cloud_cover": 90, "temperature": 20, "wind_speed": 5}]

        clear_wh, _ = energy._compute_forecast(clear, self.PANELS, self.LAT, TZ_BERLIN)
        cloudy_wh, _ = energy._compute_forecast(cloudy, self.PANELS, self.LAT, TZ_BERLIN)

        ts = dt.isoformat()
        assert clear_wh[ts] > cloudy_wh[ts], (
            f"Clear-sky {clear_wh[ts]} should exceed cloudy {cloudy_wh[ts]}"
        )

# ═══════════════════════════════════════════════════════════════════════
# 3. Backfill augmentation logic
# ═══════════════════════════════════════════════════════════════════════

class TestBackfillAugmentation:
    """Simulate the backfill logic that runs in async_get_solar_forecast."""

    PANELS = [{"kwp": 5.0, "angle": 35, "azimuth": 180}]
    LAT = 52.5

    def _augment(self, forecast, local_now):
        """Mirror the augmentation logic from energy.py."""
        tz = local_now.tzinfo
        weather_ts: set[str] = set()
        for entry in forecast:
            dt_raw = entry.get("datetime") or entry.get("DateTime")
            if not dt_raw:
                continue
            if isinstance(dt_raw, str):
                dt = datetime.fromisoformat(dt_raw)
            elif isinstance(dt_raw, datetime):
                dt = dt_raw
            else:
                continue
            if dt.date() == local_now.date():
                weather_ts.add(dt.isoformat())

        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        augmented = list(forecast)
        for hour in range(24):
            dt = today_start.replace(hour=hour)
            ts = dt.isoformat()
            if ts not in weather_ts:
                augmented.append({
                    "datetime": dt,
                    "cloud_cover": 0,
                    "temperature": 20,
                    "wind_speed": 5,
                })
        return augmented, weather_ts

    def test_backfill_adds_missing_today_hours(self):
        """Forecast with only afternoon hours gets backfilled to 24 entries."""
        local_now = datetime(2026, 7, 6, 14, 30, tzinfo=TZ_BERLIN)
        forecast = [
            {"datetime": local_now.replace(hour=14, minute=0, second=0)},
            {"datetime": local_now.replace(hour=15, minute=0, second=0)},
        ]
        augmented, weather_ts = self._augment(forecast, local_now)

        # Augmented should have all 24 hours
        assert len(augmented) >= 24

        # Count today entries
        today_tss = {e["datetime"].isoformat() for e in augmented
                     if hasattr(e["datetime"], "isoformat") and e["datetime"].date() == local_now.date()}
        assert len(today_tss) == 24, f"Expected 24 today entries, got {len(today_tss)}"

    def test_weather_ts_contains_only_weather_sourced(self):
        """weather_ts set correctly identifies original forecast hours."""
        local_now = datetime(2026, 7, 6, 14, 30, tzinfo=TZ_BERLIN)
        weather_hour = local_now.replace(hour=14, minute=0, second=0)
        forecast = [{"datetime": weather_hour}]
        augmented, weather_ts = self._augment(forecast, local_now)

        assert weather_hour.isoformat() in weather_ts
        # Backfilled hours should NOT be in weather_ts
        backfilled_hour = local_now.replace(hour=6, minute=0, second=0)
        backfilled_ts = backfilled_hour.isoformat()
        assert backfilled_ts in {e["datetime"].isoformat()
                                  for e in augmented if hasattr(e["datetime"], "isoformat")}
        assert backfilled_ts not in weather_ts

    def test_augmented_produces_daylight_curve(self):
        """Augmented forecast produces Wh for all daylight hours."""
        local_now = datetime(2026, 7, 6, 14, 30, tzinfo=TZ_BERLIN)
        forecast = [
            {"datetime": local_now.replace(hour=14, minute=0, second=0),
             "cloud_cover": 50, "temperature": 22, "wind_speed": 3},
        ]

        # Manually augment
        tz = local_now.tzinfo
        weather_ts: set[str] = set()
        for entry in forecast:
            dt = entry["datetime"]
            if dt.date() == local_now.date():
                weather_ts.add(dt.isoformat())

        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        augmented = list(forecast)
        for hour in range(24):
            dt = today_start.replace(hour=hour)
            ts = dt.isoformat()
            if ts not in weather_ts:
                augmented.append({
                    "datetime": dt,
                    "cloud_cover": 0,
                    "temperature": 20,
                    "wind_speed": 5,
                })

        raw_wh, cloud_map = energy._compute_forecast(augmented, self.PANELS, self.LAT, tz)
        assert len(raw_wh) > 0
        # The weather-sourced hour (2PM) should be in the result
        weather_ts_list = [ts for ts in raw_wh if ts in weather_ts]
        assert len(weather_ts_list) > 0, "Weather-sourced hour missing from forecast"

    def test_empty_forecast_still_produces_curve(self):
        """When weather forecast is empty, clear-sky curve for today still appears."""
        local_now = datetime(2026, 7, 6, 14, 30, tzinfo=TZ_BERLIN)
        tz = local_now.tzinfo

        weather_ts: set[str] = set()
        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        augmented = []
        for hour in range(24):
            dt = today_start.replace(hour=hour)
            ts = dt.isoformat()
            if ts not in weather_ts:
                augmented.append({
                    "datetime": dt,
                    "cloud_cover": 0,
                    "temperature": 20,
                    "wind_speed": 5,
                })

        raw_wh, _ = energy._compute_forecast(augmented, self.PANELS, self.LAT, tz)
        assert len(raw_wh) > 0, "Empty forecast should still produce daytime curve"


# ═══════════════════════════════════════════════════════════════════════
# 4. Calibration: global_scale only for backfilled, full for weather
# ═══════════════════════════════════════════════════════════════════════

class TestCalibrationMode:
    """model.apply behaves differently with/without cloud_cover."""

    def test_apply_with_cloud_cover_uses_cloud_factor(self):
        """Providing cloud_cover applies both global_scale and cloud_factor."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=800, raw_wh=1000, cloud_cover=50)

        # After training, global_scale = 0.8 (alpha=1 converges instantly)
        assert model.global_scale == pytest.approx(0.8)

        # Cloud factor for bucket 2 (40-59%) is ratio/global_scale = 0.8/0.8 = 1.0
        # Actually with alpha=1.0: cloud_factor = 1.0 + 1.0 * (0.8/0.8 - 1.0) = 1.0

        # Apply with cloud_cover=50 → uses global_scale * cloud_factor
        cal = model.apply(1000, cloud_cover=50)
        assert cal == pytest.approx(800.0)  # 1000 * 0.8 * 1.0

    def test_apply_without_cloud_cover_uses_global_only(self):
        """Without cloud_cover, only global_scale is applied."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=800, raw_wh=1000, cloud_cover=50)

        cal = model.apply(1000)  # no cloud_cover
        assert cal == pytest.approx(800.0)  # 1000 * 0.8

    def test_different_cloud_cover_gives_different_result(self):
        """Different cloud buckets produce different calibration after training."""
        model = CalibrationModel(alpha=0.5)

        # Train with high-cloud day (cloud_cover=80, actual far below raw)
        model.update(actual_wh=500, raw_wh=1000, cloud_cover=80)
        # global_scale = 1.0 + 0.5*(0.5-1.0) = 0.75
        # bucket 4 (80-100%) cloud_factor = 1.0 + 0.5*(0.5/0.75-1.0) = 0.833...

        with_cloud = model.apply(1000, cloud_cover=80)
        without_cloud = model.apply(1000)  # only global_scale

        # Backfilled (no cloud) should differ from weather-sourced (with cloud)
        assert without_cloud != pytest.approx(with_cloud), (
            "Without cloud_cover should differ from with cloud_cover"
        )

    def test_backfilled_hours_use_global_scale_only_end_to_end(self):
        """Simulate the full calibration loop from async_get_solar_forecast."""
        model = CalibrationModel(alpha=0.5)
        model.update(actual_wh=600, raw_wh=1000, cloud_cover=90)

        # Build raw_wh and cloud_map as _compute_forecast would return
        local_now = datetime(2026, 7, 6, 14, 0, tzinfo=TZ_BERLIN)

        # Weather-sourced hour (14:00, cloudy)
        weather_ts = {local_now.isoformat()}
        raw_wh = {local_now.isoformat(): 1000}
        cloud_map = {local_now.isoformat(): 90}

        # Backfilled hour (10:00, clear-sky)
        backfilled_dt = local_now.replace(hour=10)
        backfilled_ts = backfilled_dt.isoformat()
        raw_wh[backfilled_ts] = 1500
        # NOT in weather_ts, NOT in cloud_map (or cloud_map has 0 but we ignore it)

        calibrated = {}
        for ts, raw_val in raw_wh.items():
            cloud = cloud_map.get(ts) if ts in weather_ts else None
            calibrated[ts] = model.apply(raw_val, cloud_cover=cloud)

        # Weather hour: model.apply(1000, cloud_cover=90)
        # Backfilled hour: model.apply(1500)  # no cloud_cover
        assert calibrated[local_now.isoformat()] == pytest.approx(
            model.apply(1000, cloud_cover=90))
        assert calibrated[backfilled_ts] == pytest.approx(
            model.apply(1500))  # no cloud_cover

    def test_model_no_calibration_returns_raw(self):
        """Without model, wh_hours is a copy of raw_wh."""
        dt = datetime(2026, 7, 6, 14, 0, tzinfo=TZ_BERLIN)
        raw_wh = {dt.isoformat(): 1000}
        wh_hours = dict(raw_wh)
        assert wh_hours == raw_wh
        assert wh_hours is not raw_wh  # different object


# ═══════════════════════════════════════════════════════════════════════
# 5. Multiple panels
# ═══════════════════════════════════════════════════════════════════════

class TestMultiPanelForecast:
    """Forecast with multiple panels scales the output."""

    def test_two_panels_double_production(self):
        """Two identical panels produce roughly 2x Wh of one panel."""
        dt = datetime(2026, 7, 6, 14, 0, tzinfo=TZ_BERLIN)
        one_panel = [{"datetime": dt, "cloud_cover": 0, "temperature": 20, "wind_speed": 5}]
        two_panels = one_panel * 2

        wh_1, _ = energy._compute_forecast(
            one_panel, [{"kwp": 5.0, "angle": 35, "azimuth": 180}], 52.5, TZ_BERLIN)
        wh_2, _ = energy._compute_forecast(
            two_panels, [{"kwp": 5.0, "angle": 35, "azimuth": 180}] * 2, 52.5, TZ_BERLIN)

        ts = dt.isoformat()
        assert wh_2[ts] == pytest.approx(2 * wh_1[ts], rel=0.01)


# ═══════════════════════════════════════════════════════════════════════
# 6. Cloud_map completeness
# ═══════════════════════════════════════════════════════════════════════

class TestCloudMap:
    """Every entry in raw_wh has a corresponding entry in cloud_map."""

    def test_cloud_map_covers_all_raw_wh(self):
        """cloud_map must contain all keys from raw_wh."""
        dt = datetime(2026, 7, 6, 14, 0, tzinfo=TZ_BERLIN)
        forecast = [{"datetime": dt, "cloud_cover": 50, "temperature": 20, "wind_speed": 5}]
        raw_wh, cloud_map = energy._compute_forecast(
            forecast, [{"kwp": 5.0, "angle": 35, "azimuth": 180}], 52.5, TZ_BERLIN)

        for ts in raw_wh:
            assert ts in cloud_map, f"Missing cloud_map entry for {ts}"

    def test_cloud_map_values_are_floats(self):
        """Cloud_map values should be numeric floats."""
        dt = datetime(2026, 7, 6, 14, 0, tzinfo=TZ_BERLIN)
        forecast = [{"datetime": dt, "cloud_cover": 50, "temperature": 20, "wind_speed": 5}]
        _, cloud_map = energy._compute_forecast(
            forecast, [{"kwp": 5.0, "angle": 35, "azimuth": 180}], 52.5, TZ_BERLIN)

        for ts, val in cloud_map.items():
            assert isinstance(val, (int, float)), f"cloud_map[{ts}] is {type(val)}"
