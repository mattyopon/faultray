"""Tests for traffic pattern models."""

import math

from infrasim.simulator.traffic import (
    TrafficPattern,
    TrafficPatternType,
    create_ddos_volumetric,
    create_ddos_slowloris,
    create_diurnal,
    create_diurnal_weekly,
    create_flash_crowd,
    create_growth_trend,
    create_viral_event,
)


def test_constant_pattern():
    """CONSTANT pattern should always return peak_multiplier."""
    p = TrafficPattern(
        pattern_type=TrafficPatternType.CONSTANT,
        peak_multiplier=5.0,
        duration_seconds=300,
    )
    assert p.multiplier_at(0) == 5.0
    assert p.multiplier_at(150) == 5.0
    assert p.multiplier_at(299) == 5.0


def test_ramp_pattern():
    """RAMP pattern should linearly increase to peak."""
    p = TrafficPattern(
        pattern_type=TrafficPatternType.RAMP,
        peak_multiplier=3.0,
        duration_seconds=300,
        ramp_seconds=100,
        sustain_seconds=100,
        cooldown_seconds=100,
    )
    # At t=0, should be 1.0 (start of ramp)
    assert p.multiplier_at(0) == 1.0
    # At t=100, should be peak (3.0)
    assert abs(p.multiplier_at(100) - 3.0) < 0.01
    # At t=150, should still be peak (sustain phase)
    assert abs(p.multiplier_at(150) - 3.0) < 0.01
    # At t=299, should be near 1.0 (end of cooldown)
    assert abs(p.multiplier_at(299) - 1.0) < 0.1


def test_spike_pattern():
    """SPIKE pattern should jump to peak at ramp_seconds."""
    p = TrafficPattern(
        pattern_type=TrafficPatternType.SPIKE,
        peak_multiplier=10.0,
        duration_seconds=300,
        ramp_seconds=50,
        sustain_seconds=100,
    )
    assert p.multiplier_at(0) == 1.0  # Before spike
    assert p.multiplier_at(50) == 10.0  # During spike
    assert p.multiplier_at(149) == 10.0  # Still during spike
    assert p.multiplier_at(150) == 1.0  # After spike


def test_diurnal_weekly_weekday_peak():
    """DIURNAL_WEEKLY should peak around 12:30 on weekdays."""
    p = create_diurnal_weekly(peak=3.0, duration=604800, weekend_factor=0.6)
    # Monday 12:30 = 12.5 * 3600 = 45000 seconds
    weekday_peak = p.multiplier_at(45000)
    # Monday 03:00 = 3 * 3600 = 10800 seconds
    weekday_trough = p.multiplier_at(10800)
    assert weekday_peak > weekday_trough


def test_diurnal_weekly_weekend_reduction():
    """DIURNAL_WEEKLY should reduce traffic on weekends."""
    p = create_diurnal_weekly(peak=3.0, duration=604800, weekend_factor=0.6)
    # Monday 12:30 = 45000s
    weekday = p.multiplier_at(45000)
    # Saturday 12:30 = 5 * 86400 + 45000 = 477000s
    weekend = p.multiplier_at(477000)
    assert weekend < weekday


def test_growth_trend():
    """GROWTH_TREND should show exponential growth."""
    p = create_growth_trend(monthly_rate=0.1, duration=2592000)
    # At t=0, multiplier should be ~1.0
    assert abs(p.multiplier_at(0) - 1.0) < 0.01
    # At t=30 days (2592000s), should be ~1.1 (10% growth)
    assert abs(p.multiplier_at(2592000 - 1) - 1.1) < 0.02


def test_ddos_volumetric_ramp():
    """DDoS volumetric should ramp to peak in 10 seconds."""
    p = create_ddos_volumetric(peak=10.0, duration=300)
    # At t=0, should be ~1.0
    assert p.multiplier_at(0) == 1.0
    # At t=10, should be at peak
    mult_at_10 = p.multiplier_at(10)
    assert mult_at_10 >= 7.0  # Near peak with possible jitter


def test_flash_crowd_exponential_ramp():
    """FLASH_CROWD should have exponential ramp then decay."""
    p = create_flash_crowd(peak=8.0, ramp=30, duration=300)
    # During ramp (exponential)
    early = p.multiplier_at(5)
    mid = p.multiplier_at(15)
    late_ramp = p.multiplier_at(29)
    assert early < mid < late_ramp  # Exponential growth
    # After ramp, linear decay
    decay_start = p.multiplier_at(30)
    decay_end = p.multiplier_at(299)
    assert decay_start > decay_end


def test_base_multiplier_scaling():
    """base_multiplier should scale the final output."""
    p = TrafficPattern(
        pattern_type=TrafficPatternType.CONSTANT,
        peak_multiplier=2.0,
        duration_seconds=300,
        base_multiplier=1.5,
    )
    assert abs(p.multiplier_at(0) - 3.0) < 0.01  # 2.0 * 1.5


def test_out_of_range_returns_baseline():
    """Time outside [0, duration) should return baseline * base_multiplier."""
    p = TrafficPattern(
        pattern_type=TrafficPatternType.CONSTANT,
        peak_multiplier=5.0,
        duration_seconds=300,
        base_multiplier=2.0,
    )
    assert p.multiplier_at(-1) == 2.0  # 1.0 * 2.0
    assert p.multiplier_at(300) == 2.0  # 1.0 * 2.0
    assert p.multiplier_at(1000) == 2.0  # 1.0 * 2.0


def test_ddos_deterministic():
    """DDoS jitter should be deterministic (same t = same jitter)."""
    p = create_ddos_volumetric(peak=10.0, duration=300)
    # Same t should produce same result (deterministic jitter)
    result1 = p.multiplier_at(50)
    result2 = p.multiplier_at(50)
    assert result1 == result2
