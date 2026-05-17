import os
import numpy as np
import pandas as pd
from typing import Optional
from pathlib import Path


PROFILES_DIR = Path(__file__).parent / "profiles"


def load_epex_spot(year: int = 2023, cache: bool = True) -> pd.Series:
    path = PROFILES_DIR / f"epex_{year}.csv"
    if cache and path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]

    url = (
        "https://www.smard.de/app/chart_data/",
        "410/410_{year}_202501010000_202512310000.json"
    )
    raise NotImplementedError(
        "EPEX auto-download not implemented. "
        f"Place hourly EPEX Spot CSV at {path} (columns: time, price_ct_per_kwh)"
    )


def generate_load_profile(
    annual_consumption_kwh: float = 4000.0,
    n_households: int = 1,
    year: int = 2023,
    timestep_min: int = 15,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_steps = int(365 * 24 * 60 / timestep_min)

    profile_factor = _bdew_h0_profile(year, timestep_min)
    scaling = annual_consumption_kwh / (profile_factor.sum() * (timestep_min / 60))

    base = profile_factor * scaling
    profiles = pd.DataFrame(index=base.index)

    for h in range(n_households):
        noise = rng.normal(1.0, 0.1, size=len(base))
        profiles[f"hh_{h}"] = (base.values * noise).clip(min=0)

    return profiles


def _bdew_h0_profile(year: int, timestep_min: int) -> pd.Series:
    n_steps = int(365 * 24 * 60 / timestep_min)
    steps_per_hour = 60 // timestep_min
    hours = 24
    seasons = {
        "winter": (0, 90),
        "spring": (90, 181),
        "summer": (181, 273),
        "fall": (273, 365),
    }

    daily_h0 = {
        "winter": [0.32,0.28,0.26,0.26,0.28,0.34,0.48,0.56,0.52,0.48,0.44,0.44,
                   0.44,0.44,0.44,0.46,0.52,0.60,0.68,0.72,0.70,0.64,0.52,0.38],
        "spring": [0.26,0.24,0.22,0.22,0.24,0.28,0.38,0.48,0.48,0.44,0.40,0.38,
                   0.38,0.38,0.38,0.40,0.48,0.54,0.58,0.60,0.58,0.52,0.42,0.30],
        "summer": [0.22,0.20,0.18,0.18,0.20,0.24,0.34,0.42,0.42,0.38,0.36,0.34,
                   0.34,0.34,0.34,0.36,0.44,0.50,0.54,0.56,0.54,0.48,0.38,0.26],
        "fall": [0.28,0.26,0.24,0.24,0.26,0.30,0.42,0.50,0.50,0.46,0.42,0.40,
                 0.40,0.40,0.40,0.42,0.50,0.56,0.62,0.66,0.64,0.58,0.46,0.34],
    }

    start = pd.Timestamp(f"{year}-01-01")
    idx = pd.date_range(start, periods=n_steps, freq=f"{timestep_min}min",
                        inclusive="left")
    series = pd.Series(0.0, index=idx)

    for season, (doy_start, doy_end) in seasons.items():
        mask = ((idx.dayofyear >= doy_start) & (idx.dayofyear < doy_end))
        day_hour = np.array(idx.hour)[mask]
        series.loc[mask] = np.array(daily_h0[season])[day_hour]

    return series


def generate_pv_profile(
    total_kwp: float,
    year: int = 2023,
    timestep_min: int = 15,
    seed: Optional[int] = None,
) -> pd.Series:
    rng = np.random.default_rng(seed)
    n_steps = int(365 * 24 * 60 / timestep_min)
    start = pd.Timestamp(f"{year}-01-01")
    idx = pd.date_range(start, periods=n_steps, freq=f"{timestep_min}min",
                        inclusive="left")

    hour_arr = idx.hour.to_numpy() + idx.minute.to_numpy() / 60
    doy_arr = idx.dayofyear.to_numpy()
    day_angle = 2 * np.pi * (doy_arr - 81) / 365
    declination = 23.45 * np.cos(day_angle)
    latitude = 51.0
    solar_time = hour_arr - 0.5
    cos_zenith = np.sin(np.radians(latitude)) * np.sin(np.radians(declination))
    cos_zenith += np.cos(np.radians(latitude)) * np.cos(np.radians(declination))
    cos_zenith *= np.cos(np.radians(15 * (solar_time - 12)))
    cos_zenith = np.clip(cos_zenith, 0, None)

    clear_sky = 1000 * cos_zenith ** 1.2
    clouds = rng.beta(2, 5, size=n_steps) * 0.6 + 0.4
    irradiance = clear_sky * clouds

    pv_w = irradiance / 1000 * total_kwp * 1000 * 0.85
    return pd.Series(np.clip(pv_w, 0, None), index=idx)
