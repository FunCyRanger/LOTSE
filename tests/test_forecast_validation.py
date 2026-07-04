#!/usr/bin/env python3
"""Validate the weather-based PV forecast model against historical solarhistory.csv.

Compares the model's predictions against:
1. Actual solar production (combined_mesh_solar_energy)
2. The old api.forecast.solar values (solar_forecast_today)

This ensures the model is not grossly over/under-estimating.
"""

import csv
import math
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "solarhistory.csv"

# Import model functions — duplicate here to avoid HA dependency in tests
import math as _math

def _solar_altitude(lat, dayofyear, hour):
    hour_angle = (hour - 12) * 15
    decl = _math.radians(23.45 * _math.sin(_math.radians(360 / 365 * (dayofyear - 81))))
    lat_r = _math.radians(lat)
    ha_r = _math.radians(hour_angle)
    cos_zenith = (
        _math.sin(lat_r) * _math.sin(decl)
        + _math.cos(lat_r) * _math.cos(decl) * _math.cos(ha_r)
    )
    cos_zenith = max(-1, min(1, cos_zenith))
    zenith = _math.acos(cos_zenith)
    return max(0, 90 - _math.degrees(zenith))

def _clear_sky_ghi(altitude):
    return max(0, 1000 * _math.sin(_math.radians(altitude)))

def _panel_output(kwp, ghi, cloud_cover, azimuth, tilt, temp, wind):
    efficiency = 0.86
    temp_coeff = -0.004
    cloud_factor = max(0.05, 1 - 0.75 * cloud_cover / 100)
    orientation = max(
        0.25,
        min(1.1, (_math.cos(_math.radians(azimuth - 180)) * 0.65 + 0.35)
            * (_math.cos(_math.radians(tilt)) ** 0.75)),
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

# Weather condition → approximate cloud cover (%)
CLOUD_COVER_MAP = {
    "clear-night": 5,
    "sunny": 5,
    "partlycloudy": 40,
    "cloudy": 75,
    "rainy": 90,
    "fog": 85,
    "pouring": 95,
    "snowy": 85,
    "snowy-rainy": 85,
    "hail": 95,
    "lightning": 90,
    "lightning-rainy": 90,
}

# Default timezone offset (Central European Summer = UTC+2). 
# Override with TZ_OFFSET env var in hours.
TZ_OFFSET = int(sys.argv[1]) if len(sys.argv) > 1 else 2

# Default latitude (central DE). Override with LAT env var.
LAT = float(sys.argv[2]) if len(sys.argv) > 2 else 51.0

# Default panel config (user's own node: 12 kWp, 42°, 180°)
# Override with PANEL_KWP, PANEL_ANGLE, PANEL_AZIMUTH env vars.
PANEL_KWP = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0
PANEL_ANGLE = int(sys.argv[4]) if len(sys.argv) > 4 else 42
PANEL_AZIMUTH = int(sys.argv[5]) if len(sys.argv) > 5 else 180

# Model efficiency (from blueprint)
EFFICIENCY = 0.86
TEMP_COEFF = -0.004

# Default temp/wind when not available
DEFAULT_TEMP = 20
DEFAULT_WIND = 5

# Accuracy thresholds
MAX_MAPE_PCT = 40  # fail if MAPE > 40%


def parse_csv():
    """Parse solarhistory.csv into dicts by entity_id."""
    if not CSV_PATH.exists():
        print(f"  SKIP  {CSV_PATH} not found — skipping validation")
        return None
    
    data = {}
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            eid = row["entity_id"]
            data.setdefault(eid, []).append({
                "state": row["state"],
                "ts": datetime.fromisoformat(row["last_changed"].replace("Z", "+00:00")),
            })
    
    for rows in data.values():
        rows.sort(key=lambda r: r["ts"])
    
    return data


def weather_condition_to_cloud(condition):
    """Map weather.forecast_home_2 condition string to cloud cover %."""
    return CLOUD_COVER_MAP.get(condition.lower().strip(), 50)


def compute_daily_actual(data):
    """Extract daily actual energy production from cumulative sensor."""
    rows = data.get("sensor.combined_mesh_solar_energy", [])
    if not rows:
        return {}
    
    # Group by UTC date, take the last value per day as the daily cumulative
    daily_cumulative = {}
    for r in rows:
        day_key = r["ts"].strftime("%Y-%m-%d")
        daily_cumulative[day_key] = float(r["state"])
    
    # Convert to daily production by differencing consecutive days
    dated = sorted(daily_cumulative.items())
    daily_kwh = {}
    for i in range(1, len(dated)):
        prev_day, prev_val = dated[i - 1]
        curr_day, curr_val = dated[i]
        prod = curr_val - prev_val
        if 0 < prod < 200:
            daily_kwh[curr_day] = round(prod, 2)
    
    return daily_kwh


def compute_daily_forecast(data, day_str):
    """Run the PV model for a single day using weather data from the CSV."""
    weather_rows = data.get("weather.forecast_home_2", [])
    
    # Build hourly cloud cover for the given day (local time)
    day_start_utc = datetime.fromisoformat(day_str + "T00:00:00+00:00")
    day_end_utc = day_start_utc + timedelta(days=1)
    
    # Determine what weather condition was active for each local hour
    hourly_cloud = {}
    for hour in range(24):
        # Local hour → UTC timestamp
        local_dt = datetime.fromisoformat(day_str + f"T{hour:02d}:00:00")
        local_dt = local_dt.replace(tzinfo=timezone(timedelta(hours=TZ_OFFSET)))
        utc_ts = local_dt.astimezone(timezone.utc)
        
        # Find the weather condition active at this UTC time
        condition = None
        for i, r in enumerate(weather_rows):
            if r["ts"] <= utc_ts:
                condition = r["state"]
            if r["ts"] > utc_ts:
                break
        
        if condition:
            hourly_cloud[hour] = weather_condition_to_cloud(condition)
        else:
            hourly_cloud[hour] = 50
    
    # Get capacity from CSV (use most recent value before this day)
    cap_rows = data.get("sensor.combined_mesh_solar_capacity", [])
    capacity = PANEL_KWP
    for r in cap_rows:
        if r["ts"].date() <= datetime.fromisoformat(day_str).date():
            capacity = float(r["state"])
    
    # Compute hourly production
    dayofyear = datetime.strptime(day_str, "%Y-%m-%d").timetuple().tm_yday
    total_kwh = 0
    
    for hour in range(24):
        cloud = hourly_cloud.get(hour, 50)
        temp = DEFAULT_TEMP
        wind = DEFAULT_WIND
        
        altitude = _solar_altitude(LAT, dayofyear, hour)
        ghi = _clear_sky_ghi(altitude)
        if ghi <= 0:
            continue
        
        kw = _panel_output(capacity, ghi, cloud, PANEL_AZIMUTH, PANEL_ANGLE, temp, wind)
        total_kwh += kw
    
    return round(total_kwh, 1)


def get_old_forecast(data, day_str):
    """Get the old api.forecast.solar value for a given day (closest before midnight)."""
    rows = data.get("sensor.solar_forecast_today", [])
    if not rows:
        return None
    
    day_date = datetime.fromisoformat(day_str).date()
    day_end = datetime.fromisoformat(day_str + "T23:59:59+00:00")
    
    # Find the forecast closest to the end of this day
    best = None
    for r in rows:
        if r["ts"].date() == day_date and r["ts"] <= day_end:
            best = r
    
    return float(best["state"]) if best else None


def validate():
    """Main validation: compare model forecast vs actual vs old forecast."""
    data = parse_csv()
    if data is None:
        return 0, 0  # no data, skip
    
    actual_daily = compute_daily_actual(data)
    if not actual_daily:
        print("  FAIL  No actual production data found in CSV")
        return 1, 0
    
    print(f"\n  Historical data: {len(actual_daily)} days with production data")
    print(f"  Location: {LAT}°N, UTC+{TZ_OFFSET}")
    print(f"  Panel: {PANEL_KWP} kWp, {PANEL_ANGLE}° tilt, {PANEL_AZIMUTH}° azimuth")
    print(f"  Efficiency: {EFFICIENCY}")
    print(f"\n  {'Day':<12} {'Actual':>8} {'Model':>8} {'OldFC':>8} {'ModelErr':>8} {'OldFCErr':>8}")
    print(f"  {'-'*56}")
    
    errors_model = []
    errors_old = []
    match_count = 0
    
    for day_str in sorted(actual_daily.keys()):
        actual = actual_daily[day_str]
        forecast = compute_daily_forecast(data, day_str)
        old_fc = get_old_forecast(data, day_str)
        
        model_err_pct = abs(forecast - actual) / actual * 100 if actual > 0 else 0
        old_err_pct = abs(old_fc - actual) / actual * 100 if old_fc and actual > 0 else None
        
        errors_model.append(model_err_pct)
        if old_err_pct is not None:
            errors_old.append(old_err_pct)
        
        old_str = f"{old_fc:>7.1f}" if old_fc is not None else "   N/A"
        old_err_str = f"{old_err_pct:>6.1f}%" if old_err_pct is not None else "    N/A"
        
        print(f"  {day_str:<12} {actual:>7.1f} {forecast:>7.1f} {old_str}  "
              f"{model_err_pct:>6.1f}%  {old_err_str}")
        match_count += 1
    
    # Summary stats
    mape_model = sum(errors_model) / len(errors_model) if errors_model else 0
    mape_old = sum(errors_old) / len(errors_old) if errors_old else None
    rmse_model = math.sqrt(sum(e**2 for e in errors_model) / len(errors_model)) if errors_model else 0
    
    print(f"\n  ───── Summary ─────")
    print(f"  Model MAPE: {mape_model:.1f}%  (threshold: {MAX_MAPE_PCT}%)")
    print(f"  Model RMSE: {rmse_model:.1f}%")
    if mape_old is not None:
        print(f"  Old API forecast MAPE: {mape_old:.1f}%")
        delta = mape_model - mape_old
        if delta < -5:
            print(f"  → New model is significantly BETTER than old API ({delta:+.0f}pp)")
        elif delta > 5:
            print(f"  → New model is significantly WORSE than old API ({delta:+.0f}pp)")
        else:
            print(f"  → New model is comparable to old API ({delta:+.0f}pp)")
    
    failed = 0
    if mape_model > MAX_MAPE_PCT:
        print(f"\n  FAIL  Model MAPE {mape_model:.1f}% exceeds threshold {MAX_MAPE_PCT}%")
        failed = 1
    elif mape_model > 30:
        print(f"\n  WARN  Model MAPE {mape_model:.1f}% — consider tuning parameters")
    
    return failed, match_count


# ─── Also test the model formula directly with fixed inputs ───

def test_solar_geometry():
    """Verify solar geometry produces reasonable values."""
    # Summer solstice at 51°N, solar noon → altitude ~62.5°
    alt = _solar_altitude(51, 172, 12)  # June 21, noon
    assert 60 < alt < 65, f"Summer noon altitude {alt} not in [60,65]"
    
    # Winter solstice at 51°N, solar noon → altitude ~15.5°
    alt = _solar_altitude(51, 355, 12)  # Dec 21, noon
    assert 14 < alt < 17, f"Winter noon altitude {alt} not in [14,17]"
    
    # Night → altitude 0
    alt = _solar_altitude(51, 172, 0)  # midnight
    assert alt == 0, f"Midnight altitude {alt} != 0"
    
    print(f"  PASS  Solar geometry: summer={_solar_altitude(51,172,12):.1f}°, "
          f"winter={_solar_altitude(51,355,12):.1f}°")


def test_clear_sky_ghi():
    """GHI at zenith = 1000 W/m², at horizon = 0."""
    assert abs(_clear_sky_ghi(90) - 1000) < 1
    assert _clear_sky_ghi(0) == 0
    print(f"  PASS  Clear-sky GHI: zenith={_clear_sky_ghi(90):.0f}, horizon={_clear_sky_ghi(0):.0f}")


def test_panel_output_ranges():
    """Panel output should be within reasonable bounds."""
    kwp, ghi, cloud, az, tilt, temp, wind = 5.0, 800, 10, 180, 35, 25, 5
    out = _panel_output(kwp, ghi, cloud, az, tilt, temp, wind)
    assert 2.0 < out < 5.0, f"Panel output {out:.2f} kW out of range for 5 kWp at 800 W/m²"
    print(f"  PASS  Panel output: {out:.2f} kW for 5 kWp at 800 W/m², 10% cloud")
    
    # Full cloud cover → very low output
    out_cloudy = _panel_output(5.0, 800, 95, 180, 35, 25, 5)
    assert out_cloudy < out * 0.4, f"Cloudy output {out_cloudy:.2f} too high"
    print(f"  PASS  Cloud reduction: {out:.2f}→{out_cloudy:.2f} kW (clear→95% cloud)")
    
    # North-facing → lower than south-facing
    out_north = _panel_output(5.0, 800, 10, 0, 35, 25, 5)
    assert out_north < out, f"North-facing {out_north:.2f} > south-facing {out:.2f}"
    print(f"  PASS  Orientation: south={out:.2f}, north={out_north:.2f} kW")


# ─── Runner ─────────────────────────────────────────────────────

TEST_FUNCTIONS = [
    name for name, val in globals().items()
    if name.startswith("test_") and callable(val)
]


def run_all():
    print(f"\n{'='*60}")
    print(f"  LOTSE Forecast Validation")
    print(f"{'='*60}")
    
    passed = 0
    failed = 0
    
    # Run formula tests
    for name in sorted(TEST_FUNCTIONS):
        func = globals()[name]
        try:
            func()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            traceback.print_exc()
            failed += 1
    
    # Run CSV-based validation
    try:
        v_fail, v_count = validate()
        if v_count > 0:
            passed += v_count
            if v_fail:
                failed += v_fail
        else:
            print(f"  SKIP  CSV validation (no solarhistory.csv)")
    except Exception as e:
        print(f"  FAIL  validate: {e}")
        traceback.print_exc()
        failed += 1
    
    total = passed + failed
    print(f"\n{'='*50}")
    print(f"  {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
        sys.exit(1)
    else:
        print()
        sys.exit(0)


if __name__ == "__main__":
    run_all()
