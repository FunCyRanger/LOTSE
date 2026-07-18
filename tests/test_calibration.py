#!/usr/bin/env python3
"""Tests for the self-optimizing solar forecast calibration model.

These tests define the expected interface of the calibration module
BEFORE it is implemented (test-driven development). All pure-function
tests run without Home Assistant dependencies.
"""

import math
import json
import pytest
from datetime import datetime, timedelta, timezone

import importlib.util
from pathlib import Path

# Load calibration.py directly to avoid triggering __init__.py
# (which imports homeassistant not available in test context)
_calib_path = Path(__file__).resolve().parent.parent / "custom_components" / "lotse_forecast" / "calibration.py"
_spec = importlib.util.spec_from_file_location("calibration_module", _calib_path)
_calib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_calib)

CalibrationModel = _calib.CalibrationModel
merge_past_hours = _calib.merge_past_hours
compute_mape = _calib.compute_mape


# ════════════════════════════════════════════════════════════
# 1. EMA model — pure function tests
# ════════════════════════════════════════════════════════════

class TestCalibrationModel:
    """Tests for the CalibrationModel class (EMA-based scaling)."""

    def test_init_defaults(self):
        """Model starts with identity scale and no samples."""
        model = CalibrationModel()
        assert model.global_scale == pytest.approx(1.0)
        assert model.sample_count == 0
        assert model.mape is None
        assert model.cloud_factors == [1.0] * 5

    def test_init_custom_alpha(self):
        """Alpha parameter is configurable."""
        model = CalibrationModel(alpha=0.5)
        assert model.alpha == 0.5

    def test_init_custom_cloud_buckets(self):
        """Number of cloud cover buckets is configurable."""
        model = CalibrationModel(cloud_buckets=3)
        assert len(model.cloud_factors) == 3

    def test_update_moves_toward_ratio(self):
        """A single update with alpha=1 converges instantly."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=800, raw_wh=1000)
        assert model.global_scale == pytest.approx(0.8)
        assert model.sample_count == 1

    def test_update_partial_convergence(self):
        """Alpha=0.5 moves halfway toward the ratio."""
        model = CalibrationModel(alpha=0.5)
        model.update(actual_wh=600, raw_wh=1000)  # ratio = 0.6
        # new = 1.0 + 0.5 * (0.6 - 1.0) = 1.0 - 0.2 = 0.8
        assert model.global_scale == pytest.approx(0.8)

    def test_update_converges_after_multiple_steps(self):
        """Repeated updates approach the true ratio."""
        model = CalibrationModel(alpha=0.2)
        for _ in range(200):
            model.update(actual_wh=900, raw_wh=1000)
        # Should approach 0.9 within tolerance
        assert model.global_scale == pytest.approx(0.9, abs=0.03)
        assert model.sample_count == 200

    def test_update_without_cloud_arg(self):
        """Update leaves cloud factors unchanged when no cloud data."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=800, raw_wh=1000)
        assert model.cloud_factors == [1.0] * 5

    def test_update_cloud_factor_as_residual(self):
        """cloud_factors track residual deviation from global_scale.

        After training with interleaved clear days (ratio=0.8) and cloudy
        days (ratio=0.95), the clear bucket factor should be <1 (worse than
        average) and the cloudy bucket factor should be >1 (better).
        """
        model = CalibrationModel(alpha=0.3)
        for _ in range(30):
            model.update(actual_wh=800, raw_wh=1000, cloud_cover=10)   # clear
            model.update(actual_wh=950, raw_wh=1000, cloud_cover=50)   # cloudy

        # Global scale ~0.875 (average of 0.8 and 0.95)
        assert 0.84 < model.global_scale < 0.92
        # Clear bucket < 1.0 (clear days produce less than global average)
        assert model.cloud_factors[0] < 0.97
        # Cloudy bucket > 1.0 (cloudy days produce more than global average)
        assert model.cloud_factors[2] > 1.03

    def test_update_specializes_buckets(self):
        """Different cloud ranges evolve independent factors."""
        model = CalibrationModel(alpha=0.3)
        for _ in range(50):
            model.update(actual_wh=950, raw_wh=1000, cloud_cover=10)   # bucket 0 (clear)
            model.update(actual_wh=600, raw_wh=1000, cloud_cover=70)   # bucket 3 (cloudy)
        # Clear bucket higher than cloudy bucket (clear days track closer to 1)
        assert model.cloud_factors[0] > model.cloud_factors[3]

    def test_update_clamps_ratio(self):
        """Extreme ratios are clamped to [0.1, 3.0] to prevent runaway."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=5000, raw_wh=1000)  # ratio = 5.0 → clamped 3.0
        assert model.global_scale == pytest.approx(3.0)
        model.update(actual_wh=10, raw_wh=1000)    # ratio = 0.01 → clamped 0.1
        assert model.global_scale == pytest.approx(0.1)

    def test_update_ignores_nighttime(self):
        """Samples with raw_wh <= 0 are skipped — no model update."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=0, raw_wh=0)
        assert model.sample_count == 0
        assert model.global_scale == pytest.approx(1.0)

    def test_update_ignores_zero_raw(self):
        """Division by zero does not crash and sample is skipped."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=100, raw_wh=0)
        assert model.sample_count == 0
        assert model.global_scale == pytest.approx(1.0)

    def test_apply_default(self):
        """apply with no arguments returns raw * global_scale."""
        model = CalibrationModel(alpha=1.0)
        model.update(actual_wh=800, raw_wh=1000)
        assert model.apply(500) == pytest.approx(400.0)

    def test_apply_with_cloud_factor(self):
        """apply with cloud_cover multiplies by bucket factor."""
        model = CalibrationModel(alpha=1.0)
        model.cloud_factors[2] = 0.7  # bucket 2 (40-60%)
        # raw=1000 * global_scale=1.0 * cloud_factor=0.7 = 700
        assert model.apply(1000, cloud_cover=50) == pytest.approx(700.0)

    def test_apply_cloud_cover_clamps_low(self):
        """cloud_cover < 0 uses bucket 0."""
        model = CalibrationModel(alpha=1.0)
        model.cloud_factors[0] = 0.5
        assert model.apply(1000, cloud_cover=-5) == pytest.approx(500.0)

    def test_apply_cloud_cover_clamps_high(self):
        """cloud_cover >= 100 uses last bucket."""
        model = CalibrationModel(alpha=1.0)
        assert model.apply(1000, cloud_cover=100) > 0

    def test_apply_never_negative(self):
        """Output is clamped to >= 0, even with extreme factors."""
        model = CalibrationModel(alpha=1.0)
        model.global_scale = 0.0
        assert model.apply(1000) == 0

    def test_apply_without_cloud(self):
        """apply without cloud_cover uses only global_scale."""
        model = CalibrationModel(alpha=1.0)
        model.global_scale = 0.85
        model.cloud_factors[0] = 0.5  # should NOT be applied
        assert model.apply(1000) == pytest.approx(850.0)

    def test_reset_clears_all(self):
        """reset() returns model to initial state."""
        model = CalibrationModel(alpha=0.5)
        model.update(actual_wh=800, raw_wh=1000)
        model.cloud_factors[2] = 0.3
        model.reset()
        assert model.global_scale == pytest.approx(1.0)
        assert model.cloud_factors == [1.0] * 5
        assert model.sample_count == 0
        assert model.mape is None

    def test_mape_tracking(self):
        """MAPE is correctly computed after updates."""
        model = CalibrationModel(alpha=1.0)
        # actual=800, raw=1000 → 20% error
        model.update(actual_wh=800, raw_wh=1000)
        assert model.mape == pytest.approx(20.0)

    def test_mape_averaging(self):
        """MAPE averages across multiple samples."""
        model = CalibrationModel(alpha=1.0)
        # 20% error
        model.update(actual_wh=800, raw_wh=1000)
        # 10% error
        model.update(actual_wh=900, raw_wh=1000)
        # average = 15%
        assert model.mape == pytest.approx(15.0)


class TestCalibrationModelPersistence:
    """Tests for serialization/deserialization (RestoreEntity support).

    The model must be serializable to a flat dict for storage in
    entity attributes. This dict is what gets restored on startup.
    """

    def test_to_dict(self):
        """Model state can be serialized to a dict."""
        model = CalibrationModel(alpha=0.3)
        model.update(actual_wh=800, raw_wh=1000, cloud_cover=30)
        d = model.to_dict()
        # alpha=0.3, ratio=0.8 → global_scale = 1.0 + 0.3*(0.8-1.0) = 0.94
        assert d["global_scale"] == pytest.approx(0.94)
        # cloud_factors track residual from global_scale
        assert d["cloud_factors"][1] == pytest.approx(0.955, abs=0.005)
        assert d["sample_count"] == 1
        assert d["mape"] == pytest.approx(20.0)
        assert d["alpha"] == 0.3

    def test_from_dict(self):
        """Model can be reconstructed from serialized dict."""
        data = {
            "global_scale": 0.85,
            "cloud_factors": [1.0, 0.9, 0.7, 0.8, 1.0],
            "sample_count": 42,
            "mape": 15.3,
            "alpha": 0.2,
        }
        model = CalibrationModel.from_dict(data)
        assert model.global_scale == pytest.approx(0.85)
        assert model.cloud_factors == [1.0, 0.9, 0.7, 0.8, 1.0]
        assert model.sample_count == 42
        assert model.mape == pytest.approx(15.3)
        assert model.alpha == 0.2

    def test_from_dict_defaults(self):
        """Missing keys fall back to defaults."""
        model = CalibrationModel.from_dict({})
        assert model.global_scale == pytest.approx(1.0)
        assert model.cloud_factors == [1.0] * 5
        assert model.sample_count == 0
        assert model.mape is None
        assert model.alpha == 0.2

    def test_roundtrip(self):
        """to_dict → from_dict preserves all state."""
        original = CalibrationModel(alpha=0.5)
        original.update(actual_wh=750, raw_wh=1000, cloud_cover=50)
        original.cloud_factors[3] = 0.6
        d = original.to_dict()
        restored = CalibrationModel.from_dict(d)
        assert restored.global_scale == original.global_scale
        assert restored.cloud_factors == original.cloud_factors
        assert restored.sample_count == original.sample_count
        assert restored.mape == original.mape

    def test_today_predicted_persists(self):
        """today_predicted cache is included in serialization."""
        model = CalibrationModel()
        model.today_predicted = {"2026-07-06T10:00:00+00:00": 800}
        d = model.to_dict()
        assert "today_predicted" in d
        restored = CalibrationModel.from_dict(d)
        assert restored.today_predicted == model.today_predicted


# ════════════════════════════════════════════════════════════
# 2. Cloud bucket logic
# ════════════════════════════════════════════════════════════

class TestCloudBuckets:
    """Verifies the cloud_cover → bucket index mapping."""

    @pytest.mark.parametrize("cloud_cover,expected_bucket", [
        (0,   0),
        (10,  0),
        (19,  0),
        (20,  1),
        (35,  1),
        (39,  1),
        (40,  2),
        (55,  2),
        (60,  3),
        (79,  3),
        (80,  4),
        (95,  4),
        (100, 4),
    ])
    def test_bucket_mapping(self, cloud_cover, expected_bucket):
        model = CalibrationModel(cloud_buckets=5)
        assert model._cloud_bucket(cloud_cover) == expected_bucket

    def test_bucket_clamps_negative(self):
        model = CalibrationModel(cloud_buckets=5)
        assert model._cloud_bucket(-10) == 0

    def test_bucket_clamps_above_100(self):
        model = CalibrationModel(cloud_buckets=5)
        assert model._cloud_bucket(150) == 4

    def test_custom_bucket_count(self):
        """With 3 buckets each covers ~33%."""
        model = CalibrationModel(cloud_buckets=3)
        assert model._cloud_bucket(0) == 0
        assert model._cloud_bucket(33) == 0  # 33 < 33.33
        assert model._cloud_bucket(34) == 1  # 34 >= 33.33
        assert model._cloud_bucket(66) == 1  # 66 < 66.67
        assert model._cloud_bucket(67) == 2  # 67 >= 66.67
        assert model._cloud_bucket(100) == 2


# ════════════════════════════════════════════════════════════
# 3. Past-hours merge logic
# ════════════════════════════════════════════════════════════

class TestMergePastHours:
    """Tests for merge_past_hours() — the full-day curve fix."""

    def test_past_hours_use_cache(self):
        """Past hours in cache override raw values."""
        now = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        cache = {"2026-07-06T10:00:00+00:00": 800}
        raw = {"2026-07-06T10:00:00+00:00": 1000,
               "2026-07-06T15:00:00+00:00": 1200}
        merged = merge_past_hours(cache, raw, now=now)
        assert merged["2026-07-06T10:00:00+00:00"] == 800  # from cache
        assert merged["2026-07-06T15:00:00+00:00"] == 1200  # from raw

    def test_future_hours_use_raw(self):
        """Future hours (not in cache) use raw values."""
        now = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        cache = {}
        raw = {"2026-07-06T15:00:00+00:00": 1200,
               "2026-07-06T16:00:00+00:00": 1100}
        merged = merge_past_hours(cache, raw, now=now)
        assert merged == raw

    def test_current_hour_uses_raw(self):
        """The current (ongoing) hour uses raw, not cache."""
        now = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        cache = {"2026-07-06T14:00:00+00:00": 500}  # cached earlier
        raw = {"2026-07-06T14:00:00+00:00": 600}    # fresh forecast
        merged = merge_past_hours(cache, raw, now=now)
        # Current hour is NOT past, so use raw
        assert merged["2026-07-06T14:00:00+00:00"] == 600

    def test_missing_cache_falls_through(self):
        """Past hour with no cache entry falls back to raw."""
        now = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        cache = {"2026-07-06T08:00:00+00:00": 300}  # cached, but different hour
        raw = {"2026-07-06T09:00:00+00:00": 400}
        merged = merge_past_hours(cache, raw, now=now)
        assert merged["2026-07-06T09:00:00+00:00"] == 400

    def test_multiple_days_raw_only(self):
        """Only today's hours are checked against cache; other days pass through."""
        now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
        cache = {}
        raw = {"2026-07-07T10:00:00+00:00": 1000}  # tomorrow
        merged = merge_past_hours(cache, raw, now=now)
        assert "2026-07-07T10:00:00+00:00" in merged

    def test_empty_cache(self):
        """Empty cache returns raw unchanged."""
        now = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        merged = merge_past_hours({}, {"2026-07-06T15:00:00+00:00": 1000}, now=now)
        assert merged == {"2026-07-06T15:00:00+00:00": 1000}

    def test_empty_raw(self):
        """Empty raw returns empty."""
        now = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)
        assert merge_past_hours({"2026-07-06T10:00:00+00:00": 800}, {}, now=now) == {}

    def test_default_now_is_utc(self):
        """When now=None, uses current UTC time (smoke test)."""
        cache = {}
        raw = {"2026-07-06T15:00:00+00:00": 1000}
        # Should not crash
        merged = merge_past_hours(cache, raw)
        assert merged == raw

    def test_cache_reset_at_midnight(self):
        """Cache for previous day is ignored after midnight."""
        now = datetime(2026, 7, 7, 1, 0, tzinfo=timezone.utc)  # next day
        cache = {"2026-07-06T23:00:00+00:00": 500}  # yesterday
        raw = {"2026-07-07T01:00:00+00:00": 100}
        merged = merge_past_hours(cache, raw, now=now)
        assert merged["2026-07-07T01:00:00+00:00"] == 100  # not from cache


# ════════════════════════════════════════════════════════════
# 4. Statistics helpers
# ════════════════════════════════════════════════════════════

class TestComputeMAPE:
    """Tests for the MAPE computation helper."""

    def test_perfect_forecast(self):
        mape = compute_mape([100, 200, 300], [100, 200, 300])
        assert mape == pytest.approx(0.0)

    def test_single_error(self):
        mape = compute_mape([80], [100])
        # |80-100|/80*100 = 25%
        assert mape == pytest.approx(25.0)

    def test_average_error(self):
        mape = compute_mape([80, 90], [100, 100])
        # (|80-100|/80 + |90-100|/90) / 2 * 100 = (25% + 11.111%) / 2 = 18.056%
        assert mape == pytest.approx(18.0556, abs=0.001)

    def test_empty_lists(self):
        mape = compute_mape([], [])
        assert mape is None

    def test_mismatched_lengths(self):
        with pytest.raises(ValueError):
            compute_mape([100], [100, 200])

    def test_handles_zero_actual(self):
        """Zero actual values are handled without division by zero."""
        mape = compute_mape([0, 100], [50, 100])
        # For actual=0, error = |50 - 0| / max(0.001, 0) → handled
        assert mape is not None
        assert mape >= 0


# ════════════════════════════════════════════════════════════
# 5. Full roundtrip (slow — uses CSV historical data)
# ════════════════════════════════════════════════════════════

@pytest.mark.slow
class TestCalibrationRoundtrip:
    """End-to-end test using the historical solar CSV.

    Verifies that the calibration model actually improves forecast
    accuracy on real data. Marked 'slow' — excluded from default run.
    """

    CSV_PATH = None  # Will be set by conftest.py or CI

    def _load_csv_data(self):
        """Yield (raw_wh, actual_wh, cloud_cover) per hour from CSV."""
        from pathlib import Path
        import csv
        path = self.CSV_PATH or Path(__file__).resolve().parent.parent / "solarhistory.csv"
        if not path.exists():
            pytest.skip(f"solarhistory.csv not found at {path}")
        rows = []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get("raw_wh") or not row.get("actual_wh"):
                    continue
                rows.append({
                    "raw": float(row["raw_wh"]),
                    "actual": float(row["actual_wh"]),
                    "cloud": float(row.get("cloud_cover", 50)),
                })
        return rows

    def test_calibration_reduces_mape(self, csv_path=None):
        """After training on historical data, MAPE improves."""
        rows = self._load_csv_data()
        if len(rows) < 10:
            pytest.skip("Insufficient data")

        # Pre-training MAPE (raw forecast vs actual)
        raw_mape = compute_mape(
            [r["actual"] for r in rows],
            [r["raw"] for r in rows],
        )

        # Train model on sequential data
        model = CalibrationModel(alpha=0.3)
        for r in rows:
            model.update(r["actual"], r["raw"], r["cloud"])

        # Post-training adjusted forecast MAPE
        adjusted = [model.apply(r["raw"], r["cloud"]) for r in rows]
        adjusted_mape = compute_mape(
            [r["actual"] for r in rows],
            adjusted,
        )

        assert adjusted_mape < raw_mape, (
            f"Calibration did not improve MAPE: "
            f"{raw_mape:.1f}% → {adjusted_mape:.1f}%"
        )
        assert adjusted_mape < 20.0, (
            f"Calibration MAPE {adjusted_mape:.1f}% exceeds 20% target"
        )

    def test_calibration_stable_on_repeated_data(self):
        """Repeated training on same data converges smoothly (no oscillations)."""
        rows = self._load_csv_data()
        if len(rows) < 10:
            pytest.skip("Insufficient data")

        model = CalibrationModel(alpha=0.3)
        mape_history = []

        # Train incrementally
        for i, r in enumerate(rows):
            model.update(r["actual"], r["raw"], r["cloud"])
            if (i + 1) % 10 == 0:
                adjusted = [model.apply(r["raw"], r["cloud"]) for r in rows[:i+1]]
                mape = compute_mape(
                    [r["actual"] for r in rows[:i+1]],
                    adjusted,
                )
                mape_history.append(mape)

        # MAPE should decrease (or at least not oscillate wildly)
        if len(mape_history) > 5:
            # Final MAPE should be better than initial
            assert mape_history[-1] <= mape_history[0] * 1.1

    def test_reset_restores_initial_accuracy(self):
        """After reset, accuracy returns to raw (uncalibrated) level."""
        rows = self._load_csv_data()
        if len(rows) < 10:
            pytest.skip("Insufficient data")

        raw_mape = compute_mape(
            [r["actual"] for r in rows],
            [r["raw"] for r in rows],
        )

        model = CalibrationModel(alpha=0.3)
        for r in rows[:50]:
            model.update(r["actual"], r["raw"], r["cloud"])
        model.reset()

        adjusted = [model.apply(r["raw"], r["cloud"]) for r in rows[:50]]
        reset_mape = compute_mape(
            [r["actual"] for r in rows[:50]],
            adjusted,
        )
        # After reset, model applies identity → same as raw
        assert reset_mape == pytest.approx(raw_mape, abs=0.1)


# ════════════════════════════════════════════════════════════
# 6. Mock actual-source abstraction
# ════════════════════════════════════════════════════════════

class MockActualSource:
    """Test double for HourlyActualSource — returns pre-canned values."""

    def __init__(self, values: list[float | None]):
        self._values = iter(values)
        self.calls = 0

    def get_last_hour_actual(self) -> float | None:
        self.calls += 1
        return next(self._values, None)


# ════════════════════════════════════════════════════════════
# 7. Integration with forecast pipeline
# ════════════════════════════════════════════════════════════

class TestForecastPipelineIntegration:
    """End-to-end: actual source → model update → forecast apply → merge."""

    def test_hourly_cycle(self):
        """Simulates one full hourly cycle."""
        model = CalibrationModel(alpha=0.5)
        source = MockActualSource([None, 900])  # first call: baseline, second: actual

        # First tick: establish baseline
        actual_1 = source.get_last_hour_actual()
        assert actual_1 is None

        # Raw forecast for the hour that just completed
        raw_forecast = 1000
        actual_2 = source.get_last_hour_actual()
        assert actual_2 == 900

        # Update model: alpha=0.5, ratio=0.9
        # new global_scale = 1.0 + 0.5*(0.9-1.0) = 0.95
        model.update(actual_2, raw_forecast, cloud_cover=40)
        assert model.global_scale == pytest.approx(0.95)
        assert model.sample_count == 1

    def test_full_day_cycle(self):
        """Simulates a full day of hourly updates and forecast merges."""
        model = CalibrationModel(alpha=0.3)
        now = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)

        # Seed some training data: persistent 15% overestimate
        for hour in range(8, 20):
            raw = 800 + hour * 20  # ~ 960-1180 range
            actual = raw * 0.85    # 15% overestimate
            model.update(actual, raw, cloud_cover=30)

        assert 0.80 < model.global_scale < 0.90
        assert model.sample_count == 12

        # Generate forecast for next day
        raw_next = {
            f"2026-07-07T{h:02d}:00:00+00:00": 900 + h * 30
            for h in range(6, 20)
        }
        adjusted_next = {
            ts: model.apply(raw, cloud_cover=30)
            for ts, raw in raw_next.items()
        }
        model.store_forecast(adjusted_next, raw=raw_next, now=now + timedelta(days=1))

        # Later in the day, merge with raw
        later_now = datetime(2026, 7, 7, 14, 0, tzinfo=timezone.utc)
        merged = merge_past_hours(model.today_predicted, raw_next, now=later_now)

        # Past hours (before 14:00) should use adjusted values (lower than raw)
        for ts, wh in merged.items():
            dt = datetime.fromisoformat(ts)
            if dt.hour < 14:
                assert wh < raw_next[ts]  # adjusted down
            else:
                assert wh == raw_next[ts]  # raw (future)

    def test_model_improves_on_repeated_hours(self):
        """Quality gate: after training, model reduces forecast error."""
        model = CalibrationModel(alpha=0.2)

        # Simulate a persistent 15% overestimate
        for _ in range(50):
            model.update(actual_wh=850, raw_wh=1000, cloud_cover=50)

        # global_scale converges toward 0.85
        assert model.global_scale == pytest.approx(0.85, abs=0.05)
        # cloud_factors track residual = ratio/global_scale → ≈1.0
        # So apply(1000, 50) ≈ 1000 * 0.85 * 1.0 = 850
        adjusted = model.apply(1000, 50)
        adjusted_error = abs(adjusted - 850) / 850 * 100
        assert adjusted_error < 5.0, (
            f"Adjusted error {adjusted_error:.1f}% exceeds 5% after 50 samples"
        )


# ════════════════════════════════════════════════════════════
# 5. Integration import verification
# ════════════════════════════════════════════════════════════

_REQUIRED_CONST_SYMBOLS = ["BAD_STATES", "DOMAIN", "MSH_TOPIC", "NODE_KEY_META", "PLATFORMS"]


class TestIntegrationImports:
    """Verify that __init__.py has all required imports.

    These tests check the source code of __init__.py directly to
    catch missing import regressions.
    """

    def _const_import_line(self) -> str | None:
        src = self._source().split("\n")
        for line in src:
            if line.startswith("from .const import "):
                return line
        return None

    def _source(self) -> str:
        init_path = Path(__file__).resolve().parent.parent / "custom_components" / "lotse_forecast" / "__init__.py"
        return init_path.read_text()

    def test_calibration_model_imported(self):
        """__init__.py must import CalibrationModel from .calibration."""
        assert "from .calibration import CalibrationModel" in self._source(), (
            "Missing 'from .calibration import CalibrationModel' in __init__.py"
        )

    def test_calibration_model_accessible(self):
        """CalibrationModel can be imported from calibration module."""
        assert CalibrationModel is not None
        model = CalibrationModel()
        assert model.global_scale == 1.0

    def test_dashboard_imported(self):
        """__init__.py must import async_create_lovelace_dashboard from .dashboard."""
        assert "from .dashboard import async_create_lovelace_dashboard" in self._source(), (
            "Missing 'from .dashboard import async_create_lovelace_dashboard' in __init__.py"
        )

    def test_each_const_symbol_imported(self):
        """Each const.py symbol used in __init__.py must be in from .const import."""
        line = self._const_import_line()
        assert line is not None, "Missing 'from .const import ...' in __init__.py"
        for symbol in _REQUIRED_CONST_SYMBOLS:
            assert symbol in line, (
                f"Missing '{symbol}' in from .const import in __init__.py"
            )

    def test_all_const_symbols_imported_together(self):
        """All required const symbols imported in a single line."""
        line = self._const_import_line()
        assert line is not None, "Missing 'from .const import ...' in __init__.py"
        for symbol in _REQUIRED_CONST_SYMBOLS:
            assert symbol in line

    def test_manifest_integration_type_is_hub(self):
        """manifest.json must have integration_type 'hub' (for integration tab visibility)."""
        manifest_path = Path(__file__).resolve().parent.parent / "custom_components" / "lotse_forecast" / "manifest.json"
        import json
        manifest = json.loads(manifest_path.read_text())
        assert manifest.get("integration_type") == "hub", (
            f"integration_type is '{manifest.get('integration_type')}', expected 'hub'"
        )
