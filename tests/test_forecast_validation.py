#!/usr/bin/env python3
"""Validate the weather-based PV forecast model against historical solarhistory.csv.

Compares the model's predictions against:
1. Actual solar production (combined_mesh_solar_energy)
2. The old api.forecast.solar values (solar_forecast_today)

Also performs parameter sweep to find optimal model coefficients.
"""

import csv
import math
import sys
import traceback
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "solarhistory.csv"


# ─── Model functions (duplicated to avoid HA dependency in tests) ───

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
                  efficiency=0.90, cloud_coeff=0.50, temp_coeff=-0.005):
    cloud_factor = max(0.05, 1 - cloud_coeff * cloud_cover / 100)
    orientation = max(
        0.25,
        min(1.1, (math.cos(math.radians(azimuth - 180)) * 0.65 + 0.35)
            * (math.cos(math.radians(tilt)) ** 0.75)),
    )
    wind_factor = 1.0 if wind < 10 else 0.95
    temp_factor = max(0.7, 1 + temp_coeff * (temp - 25))
    return kwp * ghi / 1000 * cloud_factor * orientation * wind_factor * efficiency * temp_factor


# ─── Constants ───

CLOUD_COVER_MAP = {
    "clear-night": 5, "sunny": 5, "partlycloudy": 40,
    "cloudy": 75, "rainy": 90, "fog": 85,
    "pouring": 95, "snowy": 85, "snowy-rainy": 85,
    "hail": 95, "lightning": 90, "lightning-rainy": 90,
}

# Corrected: CSV had wrong capacity values (12/10/19.2). Real install is 9.3 kWp constant.
CONSTANT_KWP = 9.3

# User's actual panel config
PANEL_ANGLE = 44
PANEL_AZIMUTH = 180

# Location
LAT = 51.0
TZ_OFFSET = 2  # UTC+2 (CEST)

# Default temp/wind when not available
DEFAULT_TEMP = 20
DEFAULT_WIND = 5

MAX_MAPE_PCT = 40


# ─── CSV parsing ───

def parse_csv():
    if not CSV_PATH.exists():
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
    return CLOUD_COVER_MAP.get(condition.lower().strip(), 50)


def compute_daily_actual(data):
    rows = data.get("sensor.combined_mesh_solar_energy", [])
    if not rows:
        return {}
    daily_cumulative = {}
    for r in rows:
        day_key = r["ts"].strftime("%Y-%m-%d")
        daily_cumulative[day_key] = float(r["state"])
    dated = sorted(daily_cumulative.items())
    daily_kwh = {}
    for i in range(1, len(dated)):
        prev_day, prev_val = dated[i - 1]
        curr_day, curr_val = dated[i]
        prod = curr_val - prev_val
        if 0 < prod < 200:
            daily_kwh[curr_day] = round(prod, 2)
    return daily_kwh


def get_hourly_cloud(data, day_str):
    """Build hourly cloud cover array from CSV weather events for a given day (local time)."""
    weather_rows = data.get("weather.forecast_home_2", [])
    hourly_cloud = {}
    for hour in range(24):
        local_dt = datetime.fromisoformat(day_str + f"T{hour:02d}:00:00")
        local_dt = local_dt.replace(tzinfo=timezone(timedelta(hours=TZ_OFFSET)))
        utc_ts = local_dt.astimezone(timezone.utc)
        condition = None
        for i, r in enumerate(weather_rows):
            if r["ts"] <= utc_ts:
                condition = r["state"]
            if r["ts"] > utc_ts:
                break
        hourly_cloud[hour] = weather_condition_to_cloud(condition) if condition else 50
    return hourly_cloud


def compute_daily_forecast(data, day_str, kwp=CONSTANT_KWP, **model_kw):
    """Run the PV model for a single day. model_kw passed to _panel_output."""
    hourly_cloud = get_hourly_cloud(data, day_str)
    dayofyear = datetime.strptime(day_str, "%Y-%m-%d").timetuple().tm_yday
    total_kwh = 0
    for hour in range(24):
        cloud = hourly_cloud.get(hour, 50)
        altitude = _solar_altitude(LAT, dayofyear, hour)
        ghi = _clear_sky_ghi(altitude)
        if ghi <= 0:
            continue
        kw = _panel_output(kwp, ghi, cloud, PANEL_AZIMUTH, PANEL_ANGLE,
                           DEFAULT_TEMP, DEFAULT_WIND, **model_kw)
        total_kwh += kw
    return round(total_kwh, 1)


def get_old_forecast(data, day_str):
    """Get the old api.forecast.solar value for a given day."""
    rows = data.get("sensor.solar_forecast_today", [])
    if not rows:
        return None
    day_date = datetime.fromisoformat(day_str).date()
    day_end = datetime.fromisoformat(day_str + "T23:59:59+00:00")
    best = None
    for r in rows:
        if r["ts"].date() == day_date and r["ts"] <= day_end:
            best = r
    return float(best["state"]) if best else None


# ─── Validation ───

def validate(kwp=CONSTANT_KWP, **model_kw):
    """Run validation with given model parameters. Returns (mape, match_count, per_day)."""
    data = parse_csv()
    if data is None:
        return None, 0, {}

    actual_daily = compute_daily_actual(data)
    if not actual_daily:
        return None, 0, {}

    errors = []
    per_day = {}
    for day_str in sorted(actual_daily.keys()):
        actual = actual_daily[day_str]
        forecast = compute_daily_forecast(data, day_str, kwp=kwp, **model_kw)
        err_pct = abs(forecast - actual) / actual * 100 if actual > 0 else 0
        errors.append(err_pct)
        per_day[day_str] = {"actual": actual, "forecast": forecast, "error_pct": err_pct}

    return sum(errors) / len(errors), len(errors), per_day


# ─── Parameter sweep ───

def sweep():
    """Find optimal model parameters by grid search."""
    data = parse_csv()
    if data is None:
        return

    actual_daily = compute_daily_actual(data)
    if not actual_daily:
        return

    efficiency_vals = [0.70, 0.75, 0.80, 0.85, 0.86, 0.90]
    cloud_coeff_vals = [0.50, 0.60, 0.70, 0.75, 0.80, 0.90]
    temp_coeff_vals = [-0.003, -0.004, -0.005]

    print(f"\n  Parameter sweep ({len(efficiency_vals)}×{len(cloud_coeff_vals)}×{len(temp_coeff_vals)}"
          f" = {len(efficiency_vals)*len(cloud_coeff_vals)*len(temp_coeff_vals)} combinations)")
    print(f"  Constant kWp: {CONSTANT_KWP}")
    print(f"  Panel: {PANEL_ANGLE}° tilt, {PANEL_AZIMUTH}° azimuth")
    print(f"  Location: {LAT}°N, UTC+{TZ_OFFSET}")
    print()

    results = []
    for eff, cc, tc in product(efficiency_vals, cloud_coeff_vals, temp_coeff_vals):
        errors = []
        for day_str in sorted(actual_daily.keys()):
            actual = actual_daily[day_str]
            forecast = compute_daily_forecast(
                data, day_str, kwp=CONSTANT_KWP,
                efficiency=eff, cloud_coeff=cc, temp_coeff=tc)
            err_pct = abs(forecast - actual) / actual * 100 if actual > 0 else 0
            errors.append(err_pct)
        mape = sum(errors) / len(errors)
        results.append((mape, eff, cc, tc))

    results.sort()
    best = results[:10]

    print(f"  Top 10 parameter combinations:")
    print(f"  {'MAPE':>7} {'Efficiency':>10} {'CloudCoeff':>10} {'TempCoeff':>9}")
    print(f"  {'-'*40}")
    for mape, eff, cc, tc in best:
        print(f"  {mape:>6.1f}%  {eff:>8.2f}  {cc:>8.2f}  {tc:>8.3f}")

    # Compare to current defaults
    baseline_errors = []
    for day_str in sorted(actual_daily.keys()):
        actual = actual_daily[day_str]
        forecast = compute_daily_forecast(data, day_str, kwp=CONSTANT_KWP)
        err_pct = abs(forecast - actual) / actual * 100 if actual > 0 else 0
        baseline_errors.append(err_pct)
    baseline_mape = sum(baseline_errors) / len(baseline_errors)

    best_mape, best_eff, best_cc, best_tc = best[0]
    print(f"\n  {'─'*40}")
    print(f"  Baseline MAPE (eff={_panel_output.__defaults__[0]}, cc={_panel_output.__defaults__[1]}, tc={_panel_output.__defaults__[2]}): {baseline_mape:.1f}%")
    print(f"  Best MAPE:     {best_mape:.1f}% (eff={best_eff}, cc={best_cc}, tc={best_tc})")
    print(f"  Improvement:   {baseline_mape - best_mape:+.1f}pp")

    return best[0], baseline_mape, actual_daily, data


# ─── Tests ───

def test_solar_geometry():
    alt = _solar_altitude(51, 172, 12)
    assert 60 < alt < 65, f"Summer noon altitude {alt} not in [60,65]"
    alt = _solar_altitude(51, 355, 12)
    assert 14 < alt < 17, f"Winter noon altitude {alt} not in [14,17]"
    alt = _solar_altitude(51, 172, 0)
    assert alt == 0, f"Midnight altitude {alt} != 0"
    print(f"  PASS  Solar geometry: summer={_solar_altitude(51,172,12):.1f}°, "
          f"winter={_solar_altitude(51,355,12):.1f}°")


def test_clear_sky_ghi():
    assert abs(_clear_sky_ghi(90) - 1000) < 1
    assert _clear_sky_ghi(0) == 0
    print(f"  PASS  Clear-sky GHI: zenith={_clear_sky_ghi(90):.0f}, horizon={_clear_sky_ghi(0):.0f}")


def test_panel_output_ranges():
    kwp, ghi, cloud, az, tilt, temp, wind = 5.0, 800, 10, 180, 35, 25, 5
    out = _panel_output(kwp, ghi, cloud, az, tilt, temp, wind)
    assert 2.0 < out < 5.0, f"Panel output {out:.2f} kW out of range"
    print(f"  PASS  Panel output: {out:.2f} kW for 5 kWp at 800 W/m², 10% cloud")

    out_cloudy = _panel_output(5.0, 800, 95, 180, 35, 25, 5)
    assert out_cloudy < out * 0.6, f"Cloudy output {out_cloudy:.2f} too high"
    print(f"  PASS  Cloud reduction: {out:.2f}→{out_cloudy:.2f} kW (clear→95% cloud)")

    out_north = _panel_output(5.0, 800, 10, 0, 35, 25, 5)
    assert out_north < out, f"North-facing {out_north:.2f} > south-facing {out:.2f}"
    print(f"  PASS  Orientation: south={out:.2f}, north={out_north:.2f} kW")


def test_model_vs_historical():
    """Validate model against solarhistory.csv with corrected constant 9.3 kWp."""
    mape, count, per_day = validate()
    if mape is None:
        print(f"  SKIP  model_vs_historical: no solarhistory.csv")
        return

    assert mape <= MAX_MAPE_PCT, \
        f"Model MAPE {mape:.1f}% exceeds threshold {MAX_MAPE_PCT}%"

    print(f"\n  Historical data: {count} days with production data")
    print(f"  Constant kWp: {CONSTANT_KWP} (CSV capacity data ignored — was wrong)")
    eff, cc, tc = _panel_output.__defaults__
    print(f"  Model: efficiency={eff}, cloud_coeff={cc}, temp_coeff={tc}")
    print(f"\n  {'Day':<12} {'Actual':>8} {'Model':>8} {'Err':>7}")
    print(f"  {'-'*37}")

    old_errors = []
    data = parse_csv()
    for day_str in sorted(per_day.keys()):
        p = per_day[day_str]
        old_fc = get_old_forecast(data, day_str)
        old_err = abs(old_fc - p["actual"]) / p["actual"] * 100 if old_fc and p["actual"] > 0 else None
        if old_err is not None:
            old_errors.append(old_err)
        old_str = f"{old_fc:>7.1f}" if old_fc is not None else "   N/A"
        print(f"  {day_str:<12} {p['actual']:>7.1f} {p['forecast']:>7.1f} "
              f"{p['error_pct']:>6.1f}%  (oldFC={old_str})")

    old_mape = sum(old_errors) / len(old_errors) if old_errors else None

    print(f"\n  ───── Summary ─────")
    print(f"  Model MAPE: {mape:.1f}%  (threshold: {MAX_MAPE_PCT}%)")
    if old_mape is not None:
        print(f"  Old API forecast MAPE: {old_mape:.1f}% "
              f"(note: old API used fluctuating wrong capacity)")
        delta = mape - old_mape
        print(f"  Δ vs old API: {delta:+.1f}pp")
    print(f"  → PASS (MAPE {mape:.1f}% ≤ {MAX_MAPE_PCT}%)")


# ─── Runner ───

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

    # Formula tests
    for name in sorted(TEST_FUNCTIONS):
        func = globals()[name]
        try:
            func()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            traceback.print_exc()
            failed += 1

    # Parameter sweep
    print(f"\n{'='*60}")
    print(f"  Parameter Sweep")
    print(f"{'='*60}")
    try:
        sweep()
    except Exception as e:
        print(f"  FAIL  sweep: {e}")
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
