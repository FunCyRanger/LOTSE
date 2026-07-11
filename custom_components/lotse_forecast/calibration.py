from __future__ import annotations

import logging
from datetime import datetime, timezone

_LOGGER = logging.getLogger(__name__)


class CalibrationModel:
    """EMA-based calibration model for solar forecast correction.

    Maintains a global scale factor (EMA of actual/raw ratio) and
    per-cloud-cover-bucket factors that track residual deviations
    from the global scale. Cloud factors model the *difference* from
    the global average — they do not compound with global_scale.

    The model state can be serialized via to_dict/from_dict for
    persistence across restarts (e.g. via RestoreEntity attributes).
    """

    def __init__(self, alpha: float = 0.2, cloud_buckets: int = 5) -> None:
        self.alpha = alpha
        self.cloud_buckets = cloud_buckets
        self.global_scale = 1.0
        self.cloud_factors: list[float] = [1.0] * cloud_buckets
        self.sample_count = 0
        self.mape: float | None = None
        self.today_predicted: dict[str, float] = {}
        self._raw_predicted: dict[str, float] = {}
        self._ape_sum = 0.0

    def update(
        self,
        actual_wh: float,
        raw_wh: float,
        cloud_cover: float | None = None,
    ) -> None:
        """Learn from one hour of actual vs raw forecast.

        Skips night-time or zero-raw samples. Updates the global scale
        EMA, then updates the cloud-cover bucket factor as a residual
        from the global scale (so they don't compound).
        """
        if raw_wh <= 0:
            return
        ratio = actual_wh / raw_wh
        ratio = max(0.1, min(3.0, ratio))

        self.global_scale += self.alpha * (ratio - self.global_scale)

        if cloud_cover is not None:
            bucket = self._cloud_bucket(cloud_cover)
            residual = ratio / self.global_scale if self.global_scale > 0 else 1.0
            residual = max(0.1, min(3.0, residual))
            self.cloud_factors[bucket] += self.alpha * (
                residual - self.cloud_factors[bucket]
            )

        self.sample_count += 1
        pct_error = abs(actual_wh - raw_wh) / raw_wh * 100
        self._ape_sum += pct_error
        self.mape = self._ape_sum / self.sample_count

    def apply(self, raw_wh: float, cloud_cover: float | None = None) -> float:
        """Calibrate a raw forecast value.

        Applies global_scale * cloud_factor (if cloud data available).
        Cloud factors model residual from global scale, so the product
        represents the total correction.
        """
        adjusted = raw_wh * self.global_scale
        if cloud_cover is not None:
            bucket = self._cloud_bucket(cloud_cover)
            adjusted *= self.cloud_factors[bucket]
        return max(0, adjusted)

    def store_forecast(self, calibrated: dict[str, float],
                       raw: dict[str, float] | None = None,
                       now: datetime | None = None) -> None:
        """Cache today's forecast (calibrated + raw) for past-hour merge + training."""
        if now is None:
            now = datetime.now(timezone.utc)
        today = now.date()
        self.today_predicted = {
            ts: wh for ts, wh in calibrated.items()
            if (dt := _parse_dt(ts)) is not None and dt.date() == today
        }
        if raw is not None:
            self._raw_predicted = {
                ts: wh for ts, wh in raw.items()
                if (dt := _parse_dt(ts)) is not None and dt.date() == today
            }

    def train_from_actual(self, hour_iso: str, actual_wh: float,
                          cloud_cover: float | None = None) -> None:
        """Train the model using actual production for a completed hour.

        Looks up the raw forecast for that hour from the cache.
        Silently skips if the raw forecast isn't available.
        """
        raw_wh = self._raw_predicted.get(hour_iso)
        if raw_wh is not None and raw_wh > 0:
            self.update(actual_wh, raw_wh, cloud_cover)

    def reset(self) -> None:
        """Return model to initial (identity) state."""
        self.global_scale = 1.0
        self.cloud_factors = [1.0] * self.cloud_buckets
        self.sample_count = 0
        self.mape = None
        self.today_predicted = {}
        self._raw_predicted = {}
        self._ape_sum = 0.0

    def to_dict(self) -> dict:
        return {
            "global_scale": self.global_scale,
            "cloud_factors": list(self.cloud_factors),
            "sample_count": self.sample_count,
            "mape": self.mape,
            "alpha": self.alpha,
            "cloud_buckets": self.cloud_buckets,
            "today_predicted": dict(self.today_predicted),
            "_raw_predicted": dict(self._raw_predicted),
        }

    @classmethod
    def from_dict(cls, data: dict) -> CalibrationModel:
        alpha = data.get("alpha", 0.2)
        cloud_buckets = data.get("cloud_buckets", 5)
        model = cls(alpha=alpha, cloud_buckets=cloud_buckets)
        model.global_scale = data.get("global_scale", 1.0)
        raw_factors = data.get("cloud_factors", [1.0] * cloud_buckets)
        model.cloud_factors = (
            list(raw_factors) + [1.0] * max(0, cloud_buckets - len(raw_factors))
        )[:cloud_buckets]
        model.sample_count = data.get("sample_count", 0)
        model.mape = data.get("mape")
        model.today_predicted = data.get("today_predicted", {})
        model._raw_predicted = data.get("_raw_predicted", {})
        return model

    def _cloud_bucket(self, cloud_cover: float) -> int:
        if cloud_cover < 0:
            return 0
        if cloud_cover >= 100:
            return self.cloud_buckets - 1
        width = 100.0 / self.cloud_buckets
        return int(cloud_cover / width)


def merge_past_hours(
    predicted_cache: dict[str, float],
    raw_wh_hours: dict[str, float],
    now: datetime | None = None,
) -> dict[str, float]:
    """Merge cached past predictions with fresh future predictions.

    Past hours (strictly before *now*) use the cached predicted value
    when available. Current and future hours always use raw_wh_hours.
    This restores the 'full-day curve' that was present in forecast.solar.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    result = {}
    for ts, raw_wh in raw_wh_hours.items():
        dt = _parse_dt(ts)
        if dt is not None and dt < now and ts in predicted_cache:
            result[ts] = predicted_cache[ts]
        else:
            result[ts] = raw_wh
    return result


def compute_mape(actuals: list[float], predictions: list[float]) -> float | None:
    """Mean Absolute Percentage Error.

    Returns None for empty input. Raises ValueError on length mismatch.
    Uses max(0.001, actual) as denominator to avoid division by zero.
    """
    if not actuals and not predictions:
        return None
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )
    total_pct = 0.0
    for a, p in zip(actuals, predictions):
        denom = max(0.001, abs(a))
        total_pct += abs(p - a) / denom * 100
    return total_pct / len(actuals)


def _parse_dt(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
